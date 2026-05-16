import pytest
from unittest.mock import patch, MagicMock
from app.core.ldap import authenticate_ldap
from app.config import settings

_LDAP_KEYS = [
    "ldap_enabled", "ldap_host", "ldap_port", "ldap_use_ssl",
    "ldap_bind_dn", "ldap_bind_password", "ldap_base_dn", "ldap_user_filter",
    "ldap_group_admin", "ldap_group_operator", "ldap_group_readonly", "ldap_default_role",
]


@pytest.fixture(autouse=True)
def restore_ldap_settings():
    snapshot = {k: getattr(settings, k) for k in _LDAP_KEYS}
    yield
    for k, v in snapshot.items():
        setattr(settings, k, v)


def _ldap_settings():
    settings.ldap_enabled = True
    settings.ldap_host = "ldap.example.com"
    settings.ldap_port = 389
    settings.ldap_use_ssl = False
    settings.ldap_bind_dn = "cn=svc,dc=example,dc=com"
    settings.ldap_bind_password = "svcpass"
    settings.ldap_base_dn = "dc=example,dc=com"
    settings.ldap_user_filter = "(sAMAccountName={username})"
    settings.ldap_group_admin = "CN=Admins,dc=example,dc=com"
    settings.ldap_group_operator = ""
    settings.ldap_group_readonly = ""
    settings.ldap_default_role = "readonly"


def test_ldap_disabled_returns_none():
    settings.ldap_enabled = False
    result = authenticate_ldap("alice", "pass")
    assert result is None


def test_ldap_wrong_password_returns_none():
    _ldap_settings()
    with patch("app.core.ldap.ldap3.Connection") as MockConn:
        service_conn = MagicMock()
        service_conn.bind.return_value = True
        service_conn.search.return_value = True
        service_conn.entries = [MagicMock(entry_dn="cn=alice,dc=example,dc=com")]

        user_conn = MagicMock()
        user_conn.bind.return_value = False

        MockConn.side_effect = [service_conn, user_conn]
        result = authenticate_ldap("alice", "wrongpass")
    assert result is None


def test_ldap_user_not_found_returns_none():
    _ldap_settings()
    with patch("app.core.ldap.ldap3.Connection") as MockConn:
        conn = MagicMock()
        conn.bind.return_value = True
        conn.search.return_value = True
        conn.entries = []
        MockConn.return_value = conn
        result = authenticate_ldap("nobody", "pass")
    assert result is None


def test_ldap_service_bind_failure_returns_none():
    _ldap_settings()
    with patch("app.core.ldap.ldap3.Connection") as MockConn:
        svc = MagicMock()
        svc.bind.return_value = False
        MockConn.return_value = svc
        result = authenticate_ldap("alice", "pass")
    assert result is None


def test_ldap_admin_group_returns_admin_role():
    _ldap_settings()
    user_dn = "cn=alice,dc=example,dc=com"

    with patch("app.core.ldap.ldap3.Connection") as MockConn:
        svc = MagicMock()
        svc.bind.return_value = True
        svc.search.return_value = True
        svc.entries = [MagicMock(entry_dn=user_dn)]

        usr = MagicMock()
        usr.bind.return_value = True

        grp = MagicMock()
        grp.bind.return_value = True
        grp.search.return_value = True
        grp.entries = [MagicMock()]

        MockConn.side_effect = [svc, usr, grp]
        result = authenticate_ldap("alice", "pass")
    assert result == "admin"


def test_ldap_no_groups_uses_default_role():
    _ldap_settings()
    settings.ldap_group_admin = ""
    user_dn = "cn=alice,dc=example,dc=com"

    with patch("app.core.ldap.ldap3.Connection") as MockConn:
        svc = MagicMock()
        svc.bind.return_value = True
        svc.search.return_value = True
        svc.entries = [MagicMock(entry_dn=user_dn)]

        usr = MagicMock()
        usr.bind.return_value = True

        MockConn.side_effect = [svc, usr]
        result = authenticate_ldap("alice", "pass")
    assert result == "readonly"
