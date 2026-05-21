import pytest

from app.core.mac import normalize_mac

CANONICAL = "aa:bb:cc:dd:ee:ff"


@pytest.mark.parametrize("raw", [
    "aa:bb:cc:dd:ee:ff",
    "AA:BB:CC:DD:EE:FF",
    "aa-bb-cc-dd-ee-ff",
    "AA-BB-CC-DD-EE-FF",
    "aabb.ccdd.eeff",
    "aabbccddeeff",
    "AABBCCDDEEFF",
    "aa bb cc dd ee ff",
    " aa:bb:cc:dd:ee:ff ",
])
def test_normalize_accepts_any_delimiter(raw):
    assert normalize_mac(raw) == CANONICAL


@pytest.mark.parametrize("raw", [
    "",
    "aa:bb:cc:dd:ee",          # too short
    "aa:bb:cc:dd:ee:ff:00",    # too long
    "gg:bb:cc:dd:ee:ff",       # non-hex
    "zzzzzzzzzzzz",            # non-hex bare
    "aabbccddeeffaa",          # 14 hex digits
])
def test_normalize_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_mac(raw)


def test_normalize_is_idempotent():
    assert normalize_mac(normalize_mac("AABB.CCDD.EEFF")) == CANONICAL
