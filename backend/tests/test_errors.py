from app.core.errors import classify_provider_error


def test_classify_auth():
    info = classify_provider_error(Exception("WinRMTransportError: 401 Unauthorized"), "dns")
    assert info.code == "provider_auth_failed"
    assert "DNS" in info.message
    assert info.hint


def test_classify_unreachable():
    info = classify_provider_error(Exception("Connection timed out to dc01"), "dhcp")
    assert info.code == "provider_unreachable"
    assert "DHCP" in info.message


def test_classify_not_found():
    info = classify_provider_error(
        Exception("Remove-DnsServerResourceRecord: WIN32 9714 ObjectNotFound"), "dns")
    assert info.code == "record_not_found"


def test_classify_forbidden():
    info = classify_provider_error(Exception("403 Forbidden: token lacks permission"), "dns")
    assert info.code == "provider_forbidden"


def test_classify_generic_fallback():
    info = classify_provider_error(Exception("something weird happened"), "dns")
    assert info.code == "provider_error"
    assert info.message  # non-empty friendly text
