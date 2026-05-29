from app.security import detect_security, emit_security_event
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.network_device import DiscoveredEndpoint, NetworkDevice
from app.models.security import SecurityEvent, MacLastSeen
from app.core.time import utcnow


def _device(db):
    d = NetworkDevice(name="sw", host="10.0.0.1", snmp_version="2c", community="x")
    db.add(d)
    db.commit()
    return d


def _ep(db, device_id, mac, ip=None, port="Gi0/1"):
    db.add(DiscoveredEndpoint(device_id=device_id, mac=mac, ip=ip, port_name=port,
                              last_seen=utcnow(), source="sw"))
    db.commit()


def _events(db, et=None):
    q = db.query(SecurityEvent)
    if et:
        q = q.filter_by(event_type=et)
    return q.all()


def test_new_mac(db):
    d = _device(db)
    _ep(db, d.id, "aa:bb:cc:dd:ee:ff", ip="10.0.0.5")
    # subnet so the ip isn't rogue
    s = Subnet(name="N", cidr="10.0.0.0/24", ip_version=4)
    db.add(s); db.flush()
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned))
    db.commit()
    detect_security(db)
    assert len(_events(db, "new_mac")) == 1


def test_mac_move(db):
    d = _device(db)
    db.add(MacLastSeen(mac="aa:bb:cc:dd:ee:ff", device_id=d.id, port_name="Gi0/1", last_seen=utcnow()))
    db.commit()
    _ep(db, d.id, "aa:bb:cc:dd:ee:ff", ip="10.0.0.5", port="Gi0/9")  # moved port
    detect_security(db)
    moves = _events(db, "mac_move")
    assert len(moves) == 1


def test_ip_conflict(db):
    d = _device(db)
    _ep(db, d.id, "aa:aa:aa:aa:aa:aa", ip="10.0.0.5", port="Gi0/1")
    _ep(db, d.id, "bb:bb:bb:bb:bb:bb", ip="10.0.0.5", port="Gi0/2")
    detect_security(db)
    assert len(_events(db, "ip_conflict")) == 1


def test_rogue_device(db):
    d = _device(db)
    _ep(db, d.id, "aa:bb:cc:dd:ee:ff", ip="10.0.0.99")  # ip not in IPAM
    detect_security(db)
    assert len(_events(db, "rogue_device")) == 1


def test_dedupe(db):
    d = _device(db)
    _ep(db, d.id, "aa:bb:cc:dd:ee:ff", ip="10.0.0.99")
    detect_security(db)
    detect_security(db)
    assert len(_events(db, "rogue_device")) == 1  # refreshed, not duplicated


def test_emit_event_helper_dedupes(db):
    emit_security_event(db, "rogue_device", mac="m", ip="10.0.0.1", severity="warning", details={})
    emit_security_event(db, "rogue_device", mac="m", ip="10.0.0.1", severity="warning", details={})
    assert db.query(SecurityEvent).count() == 1
