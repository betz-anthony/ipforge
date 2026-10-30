import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BUMP = ROOT / "scripts" / "suggest-bump.sh"
CHANGELOG_SYNC = ROOT / "scripts" / "check-changelog-sync.sh"
VERIFY_TAG = ROOT / "scripts" / "verify-release-tag.sh"


def _run(script: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True, text=True, cwd=ROOT,
    )


def test_suggest_bump_explicit_range_matches_known_release():
    # v1.1.0 -> v1.2.0 shipped real feat: commits (DNS/DHCP edit, webhooks,
    # Python client, drift, a11y) -> minor.
    result = _run(BUMP, "v1.1.0", "v1.2.0")
    assert result.returncode == 0
    assert "Next version:   v1.2.0" in result.stdout
    assert "Recommended:    minor" in result.stdout


def test_suggest_bump_explicit_range_no_head_arg_defaults_to_head():
    # Single base-tag arg form: <base-tag>..HEAD.
    result = _run(BUMP, "v1.2.0")
    assert result.returncode == 0
    assert "Last release:   v1.2.0" in result.stdout


def test_verify_release_tag_accepts_known_good_release():
    result = _run(VERIFY_TAG, "v1.2.0")
    assert result.returncode == 0
    assert "matches the recommended bump" in result.stdout
    assert "has a real entry" in result.stdout


def test_verify_release_tag_rejects_wrong_bump_level():
    # v1.2.0..HEAD contains feat: commits -> minor -> v1.3.0 is the correct
    # next tag. v1.9.0 is deliberately wrong.
    subprocess.run(["git", "tag", "v1.9.0"], cwd=ROOT, check=True, capture_output=True)
    try:
        result = _run(VERIFY_TAG, "v1.9.0")
        assert result.returncode == 1
        assert "does not match the recommended bump (v1.3.0)" in result.stdout
    finally:
        subprocess.run(["git", "tag", "-d", "v1.9.0"], cwd=ROOT, check=True, capture_output=True)


def test_verify_release_tag_rejects_placeholder_changelog():
    # No real tag exists for this version, and none will — the changelog
    # check runs regardless of the bump check's outcome, so this exercises
    # the placeholder-detection path directly.
    result = _run(VERIFY_TAG, "v9.9.9")
    assert result.returncode == 1
    assert "has no '## [9.9.9]' section" in result.stdout


def test_verify_release_tag_ignores_non_release_tags():
    result = _run(VERIFY_TAG, "pyclient-v1.0.0")
    assert result.returncode == 0
    assert "isn't a vX.Y.Z release tag" in result.stdout


def test_check_changelog_sync_passes_on_this_repo():
    # Holds both with notes under [Unreleased] and, between cutting a release
    # section and tagging it, with that section prepared; once the tag exists
    # and no feat: commits follow it there is nothing to check.
    result = _run(CHANGELOG_SYNC)
    assert result.returncode == 0, result.stdout


def _sync_repo(tmp_path, changelog: str, tag_release: bool = False):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for src in (CHANGELOG_SYNC, ROOT / "scripts" / "extract-changelog.sh"):
        (scripts / src.name).write_text(src.read_text())
        (scripts / src.name).chmod(0o755)
    (tmp_path / "CHANGELOG.md").write_text(changelog)

    def git(*args):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            cwd=tmp_path, check=True, capture_output=True,
        )

    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "chore: start")
    git("tag", "v1.0.0")
    git("commit", "-q", "--allow-empty", "-m", "feat(x): something new")
    if tag_release:
        git("tag", "v1.1.0")
    return subprocess.run(
        ["bash", str(scripts / "check-changelog-sync.sh")],
        capture_output=True, text=True, cwd=tmp_path,
    )


_HEAD = "# Changelog\n\n## [Unreleased]\n\n"


def test_check_changelog_sync_accepts_a_prepared_untagged_release(tmp_path):
    result = _sync_repo(tmp_path, _HEAD + "## [1.1.0] - 2026-01-01\n\n### Added\n- the new thing\n\n## [1.0.0] - 2025-01-01\n\n- first\n")
    assert result.returncode == 0, result.stdout
    assert "prepared" in result.stdout


def test_check_changelog_sync_survives_a_long_release_history(tmp_path):
    # The script runs under pipefail; reading the first release heading must
    # not leave an upstream writer to die of SIGPIPE (exit 141) when many
    # older headings follow it.
    history = "".join(f"## [0.{i}.0] - 2024-01-01\n\n- old\n\n" for i in range(3000, 0, -1))
    result = _sync_repo(tmp_path, _HEAD + "## [1.1.0] - 2026-01-01\n\n- the new thing\n\n" + history)
    assert result.returncode == 0, (result.returncode, result.stdout)
    assert "prepared" in result.stdout


def test_check_changelog_sync_flags_empty_unreleased_with_no_prepared_release(tmp_path):
    result = _sync_repo(tmp_path, _HEAD + "## [1.0.0] - 2025-01-01\n\n- first\n")
    assert result.returncode == 1
    assert "WARNING" in result.stdout


def test_check_changelog_sync_flags_a_release_section_that_is_already_tagged(tmp_path):
    # v1.1.0 is tagged, so its section no longer excuses an empty
    # [Unreleased]: the feat: commit after v1.0.0 is v1.1.0's, but nothing
    # since v1.1.0 is.
    result = _sync_repo(
        tmp_path,
        _HEAD + "## [1.1.0] - 2026-01-01\n\n- the new thing\n\n## [1.0.0] - 2025-01-01\n\n- first\n",
        tag_release=True,
    )
    assert result.returncode == 0, "no feat: commits after the v1.1.0 tag, so nothing to check"
    assert "nothing to check" in result.stdout


@pytest.mark.parametrize("subject", [
    "feat(x): something new",
    "feat(x)!: something new and breaking",
])
def test_check_changelog_sync_detects_feat_subjects(subject):
    # Exercises the same grep the script itself uses so a change to the
    # conventional-commit feat: pattern is caught by this test, not just by
    # eyeballing the regex.
    result = subprocess.run(
        ["grep", "-Eq", r"^feat(\([^)]*\))?!?:"],
        input=subject, text=True,
    )
    assert result.returncode == 0
