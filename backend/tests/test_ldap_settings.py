def test_get_ldap_settings_returns_defaults(client):
    r = client.get("/api/settings/ldap")
    assert r.status_code == 200
    data = r.json()
    assert data["ldap_enabled"] is False
    assert data["ldap_port"] == 389
    assert data["ldap_default_role"] == "readonly"

def test_update_ldap_settings(client):
    r = client.put("/api/settings/ldap", json={
        "ldap_enabled": True,
        "ldap_host": "ldap.example.com",
        "ldap_port": 636,
        "ldap_use_ssl": True,
        "ldap_bind_dn": "cn=svc,dc=example,dc=com",
        "ldap_bind_password": "secret",
        "ldap_base_dn": "dc=example,dc=com",
        "ldap_user_filter": "(sAMAccountName={username})",
        "ldap_group_admin": "CN=Admins,dc=example,dc=com",
        "ldap_group_operator": "CN=Ops,dc=example,dc=com",
        "ldap_group_readonly": "",
        "ldap_default_role": "readonly",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["ldap_enabled"] is True
    assert data["ldap_host"] == "ldap.example.com"
    assert data["ldap_port"] == 636

def test_ldap_password_not_returned(client):
    client.put("/api/settings/ldap", json={"ldap_bind_password": "secret"})
    r = client.get("/api/settings/ldap")
    assert r.status_code == 200
    data = r.json()
    assert "ldap_bind_password" not in data or data["ldap_bind_password"] == ""
