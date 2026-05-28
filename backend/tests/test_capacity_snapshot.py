from datetime import date

from app.scan import _snapshot_utilization
from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.scan import SubnetUtilizationDay
from app.core.time import utcnow


def test_snapshot_records_used_and_total(db):
    s = Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.flush()
    db.add(IPAddress(address="10.0.0.1", subnet_id=s.id, status=AddressStatus.assigned))
    db.add(IPAddress(address="10.0.0.2", subnet_id=s.id, status=AddressStatus.reserved))
    db.add(IPAddress(address="10.0.0.3", subnet_id=s.id, status=AddressStatus.available))
    db.commit()

    now = utcnow()
    _snapshot_utilization(db, now)
    db.commit()

    rows = db.query(SubnetUtilizationDay).all()
    assert len(rows) == 1
    assert rows[0].subnet_id == s.id
    assert rows[0].date == now.date()
    assert rows[0].used_count == 2
    assert rows[0].total_count == 254


def test_snapshot_idempotent_updates_same_day(db):
    s = Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.flush()
    db.add(IPAddress(address="10.0.0.1", subnet_id=s.id, status=AddressStatus.assigned))
    db.commit()

    now = utcnow()
    _snapshot_utilization(db, now)
    db.commit()

    db.add(IPAddress(address="10.0.0.2", subnet_id=s.id, status=AddressStatus.assigned))
    db.commit()
    _snapshot_utilization(db, now)
    db.commit()

    rows = db.query(SubnetUtilizationDay).filter_by(subnet_id=s.id, date=now.date()).all()
    assert len(rows) == 1
    assert rows[0].used_count == 2
