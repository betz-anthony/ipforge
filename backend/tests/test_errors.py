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


import pytest
from types import SimpleNamespace
from fastapi import HTTPException
from app.core.errors import raise_provider_error, provider_unconfigured


def _raise(exc, **kw):
    try:
        raise_provider_error(exc, step="dns", **kw)
    except HTTPException as e:
        return e


def test_envelope_shape_and_status():
    e = _raise(Exception("401 Unauthorized"), user=SimpleNamespace(role="admin"))
    assert e.status_code == 502
    assert e.detail["code"] == "provider_auth_failed"
    assert e.detail["message"] and e.detail["hint"]
    assert e.detail["step"] == "dns"


def test_detail_included_for_operator_admin():
    for role in ("admin", "operator"):
        e = _raise(Exception("boom secret host dc01"), user=SimpleNamespace(role=role))
        assert e.detail["detail"] == "boom secret host dc01"


def test_detail_hidden_for_low_roles_and_none():
    for user in (SimpleNamespace(role="read-only"), SimpleNamespace(role="requester"), None):
        e = _raise(Exception("boom secret host dc01"), user=user)
        assert "detail" not in e.detail


def test_provider_unconfigured():
    with pytest.raises(HTTPException) as ei:
        provider_unconfigured("dhcp")
    assert ei.value.detail["code"] == "provider_not_configured"
    assert "DHCP" in ei.value.detail["message"]
