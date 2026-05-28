from unittest.mock import patch

from app.discovery.base import Endpoint
from app.discovery.runner import poll_device
from app.models.network_device import NetworkDevice, DiscoveredEndpoint
from app.models.cache import SyncStatus


def _device(db):
    d = NetworkDevice(name="sw1", host="10.0.0.1", snmp_version="2c", community="x", enabled=True)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def test_poll_device_writes_endpoints(db):
    d = _device(db)
    fake = [Endpoint(ip="10.0.0.20", mac="aa:bb:cc:dd:ee:ff", ifindex=7, port_name="Gi0/3", vlan=100)]
    with patch("app.discovery.runner.build_source") as bs:
        bs.return_value.poll.return_value = fake
        poll_device(d.id, _db=db)
    rows = db.query(DiscoveredEndpoint).filter_by(device_id=d.id).all()
    assert len(rows) == 1
    assert rows[0].ip == "10.0.0.20" and rows[0].port_name == "Gi0/3" and rows[0].vlan == 100
    assert db.get(SyncStatus, f"discovery:{d.id}").status == "ok"


def test_poll_device_replaces_prior(db):
    d = _device(db)
    with patch("app.discovery.runner.build_source") as bs:
        bs.return_value.poll.return_value = [Endpoint(mac="11:11:11:11:11:11")]
        poll_device(d.id, _db=db)
        bs.return_value.poll.return_value = [Endpoint(mac="22:22:22:22:22:22")]
        poll_device(d.id, _db=db)
    macs = {r.mac for r in db.query(DiscoveredEndpoint).filter_by(device_id=d.id).all()}
    assert macs == {"22:22:22:22:22:22"}


def test_poll_device_error_sets_status(db):
    d = _device(db)
    with patch("app.discovery.runner.build_source", side_effect=RuntimeError("unreachable")):
        poll_device(d.id, _db=db)
    st = db.get(SyncStatus, f"discovery:{d.id}")
    assert st.status == "error"
    assert "unreachable" in st.error
