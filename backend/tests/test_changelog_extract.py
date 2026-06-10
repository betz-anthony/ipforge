import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "extract-changelog.sh"


def _extract(version: str) -> str:
    return subprocess.run(
        ["bash", str(SCRIPT), version],
        capture_output=True, text=True, check=True,
    ).stdout


def test_extract_known_version_returns_body():
    out = _extract("1.0.0")
    assert out.strip()
    assert "First public release." in out


def test_extract_missing_version_returns_fallback():
    out = _extract("9.9.9")
    assert out.strip() == "Release v9.9.9."
