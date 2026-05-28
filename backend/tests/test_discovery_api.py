from datetime import datetime, timezone
from unittest.mock import patch

from app.models.network_device import NetworkDevice, DiscoveredEndpoint
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.core.crypto import decrypt_secret


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_create_device_hides_and_encrypts_creds(client, db):
    r = client.post("/api/discovery/devices", json={
        "name": "sw1", "host": "10.0.0.1", "snmp_version": "2c", "community": "secret123",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert "community" not in body or body.get("community") in (None, "")
    assert body["has_community"] is True
    # Secret is stored (encrypted when SECRET_KEY is set) and round-trips; never returned.
    row = db.get(NetworkDevice, body["id"])
    assert decrypt_secret(row.community) == "secret123"


def test_list_devices_no_secrets(client, db):
    db.add(NetworkDevice(name="sw1", host="10.0.0.1", snmp_version="2c", community="x", enabled=True))
    db.commit()
    data = client.get("/api/discovery/devices").json()
    assert all("community" not in d or d.get("community") in (None, "") for d in data)


def test_delete_device_cascades_endpoints(client, db):
    d = NetworkDevice(name="sw1", host="10.0.0.1", snmp_version="2c", community="x")
    db.add(d)
    db.flush()
    db.add(DiscoveredEndpoint(device_id=d.id, ip="10.0.0.5", mac="aa:bb:cc:dd:ee:ff", last_seen=_now(), source="sw1"))
    db.commit()
    did = d.id
    assert client.delete(f"/api/discovery/devices/{did}").status_code == 204
    assert db.query(DiscoveredEndpoint).filter_by(device_id=did).count() == 0


def test_non_admin_cannot_create_device(client_operator, db):
    r = client_operator.post("/api/discovery/devices", json={
        "name": "sw1", "host": "10.0.0.1", "snmp_version": "2c", "community": "x",
    })
    assert r.status_code == 403


def test_poll_endpoint_invokes_poll(client, db):
    d = NetworkDevice(name="sw1", host="10.0.0.1", snmp_version="2c", community="x")
    db.add(d)
    db.commit()
    class _Fake:
        def __init__(self, target=None, args=(), **kw):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)
    with patch("app.api.discovery.poll_device") as pd, \
         patch("app.api.discovery.threading.Thread", _Fake):
        r = client.post(f"/api/discovery/devices/{d.id}/poll")
    assert r.status_code == 200
    pd.assert_called_once()


def test_endpoints_filter(client, db):
    d = NetworkDevice(name="sw1", host="10.0.0.1", snmp_version="2c", community="x")
    db.add(d)
    db.flush()
    db.add(DiscoveredEndpoint(device_id=d.id, ip="10.0.0.5", mac="aa:aa:aa:aa:aa:aa", last_seen=_now(), source="sw1"))
    db.add(DiscoveredEndpoint(device_id=d.id, ip="10.0.0.6", mac="bb:bb:bb:bb:bb:bb", last_seen=_now(), source="sw1"))
    db.commit()
    data = client.get("/api/discovery/endpoints", params={"ip": "10.0.0.5"}).json()
    assert [e["mac"] for e in data] == ["aa:aa:aa:aa:aa:aa"]


def test_address_enrichment_matches_by_ip_and_mac(client, db):
    s = Subnet(name="N", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.flush()
    a = IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned, mac_address="aa:bb:cc:dd:ee:ff")
    db.add(a)
    d = NetworkDevice(name="sw1", host="10.0.0.1", snmp_version="2c", community="x")
    db.add(d)
    db.flush()
    # one matches by ip, one by mac
    db.add(DiscoveredEndpoint(device_id=d.id, ip="10.0.0.5", mac="zz", port_name="Gi0/1", last_seen=_now(), source="sw1"))
    db.add(DiscoveredEndpoint(device_id=d.id, ip=None, mac="aa:bb:cc:dd:ee:ff", port_name="Gi0/2", last_seen=_now(), source="sw1"))
    db.commit()
    data = client.get(f"/api/addresses/{a.id}/discovery").json()
    ports = {e["port_name"] for e in data}
    assert ports == {"Gi0/1", "Gi0/2"}
