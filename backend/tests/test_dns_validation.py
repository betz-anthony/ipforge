BASE = {
    "name": "web01", "record_type": "A", "value": "10.0.0.1",
    "zone": "example.com", "ttl": 3600, "source": "bind01",
}


def _post(client, **overrides):
    body = {**BASE, **overrides}
    return client.post("/api/dns/zones/example.com/records", json=body)


def test_create_record_rejects_injection_in_name(client):
    r = _post(client, name="x'; Remove-Item C:\\ ; '")
    assert r.status_code == 422


def test_create_record_rejects_space_in_name(client):
    r = _post(client, name="web 01")
    assert r.status_code == 422


def test_create_record_rejects_unknown_record_type(client):
    r = _post(client, record_type="EVIL")
    assert r.status_code == 422


def test_create_record_rejects_control_char_in_value(client):
    r = _post(client, record_type="TXT", value="bad\nvalue")
    assert r.status_code == 422


def test_create_record_rejects_empty_value(client):
    r = _post(client, value="   ")
    assert r.status_code == 422
