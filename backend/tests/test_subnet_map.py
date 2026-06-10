from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.subnet_range import SubnetRange
from app.models.scan import DriftItem, DriftCategory
from app.core.time import utcnow


def _subnet(db, cidr="10.0.5.0/24"):
    s = Subnet(name="N", cidr=cidr, ip_version=4)
    db.add(s)
    db.commit()
    return s


def test_map_too_large(client, db):
    s = _subnet(db, cidr="10.0.0.0/16")
    body = client.get(f"/api/v1/subnets/{s.id}/map").json()
    assert body["too_large"] is True
    assert body["host_count"] > 1024


def test_map_status_precedence(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.5.10", subnet_id=s.id, status=AddressStatus.assigned))
    db.add(SubnetRange(subnet_id=s.id, start_ip="10.0.5.20", end_ip="10.0.5.22", kind="reserved"))
    db.commit()
    body = client.get(f"/api/v1/subnets/{s.id}/map").json()
    assert body["too_large"] is False
    cells = {c["ip"]: c for c in body["cells"]}
    assert cells["10.0.5.10"]["status"] == "assigned"
    assert cells["10.0.5.20"]["status"] == "reserved"
    assert cells["10.0.5.99"]["status"] == "free"


def test_map_collision_overlay(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.5.10", subnet_id=s.id, status=AddressStatus.assigned))
    db.add(DriftItem(ip_address="10.0.5.10", category=DriftCategory.hostname_mismatch.value,
                     detected_at=utcnow(), resolved=False))
    db.commit()
    body = client.get(f"/api/v1/subnets/{s.id}/map").json()
    cells = {c["ip"]: c for c in body["cells"]}
    assert cells["10.0.5.10"]["collision"] is True
    assert cells["10.0.5.11"]["collision"] is False


def test_map_excludes_resolved_collision(client, db):
    s = _subnet(db)
    db.add(IPAddress(address="10.0.5.10", subnet_id=s.id, status=AddressStatus.assigned))
    db.add(DriftItem(ip_address="10.0.5.10", category=DriftCategory.hostname_mismatch.value,
                     detected_at=utcnow(), resolved=True))
    db.commit()
    body = client.get(f"/api/v1/subnets/{s.id}/map").json()
    cells = {c["ip"]: c for c in body["cells"]}
    assert cells["10.0.5.10"]["collision"] is False
