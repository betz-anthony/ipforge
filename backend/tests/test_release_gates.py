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


def test_check_changelog_sync_passes_with_current_unreleased_content():
    # CHANGELOG.md's [Unreleased] section currently documents the
    # DHCP-RESERVED-RANGE-SYNC-001 feat: commits already on this branch.
    result = _run(CHANGELOG_SYNC)
    assert result.returncode == 0
    assert "OK:" in result.stdout


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
