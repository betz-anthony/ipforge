from app.models.subnet import Subnet
from app.models.subnet_range import SubnetRange
from tests.conftest import TestingSessionLocal


def test_list_ranges_includes_source(client, db):
    s = Subnet(name="lan", cidr="10.10.0.0/24", ip_version=4)
    db.add(s)
    db.commit()
    db.add(SubnetRange(subnet_id=s.id, start_ip="10.10.0.1", end_ip="10.10.0.1",
                        kind="gateway", source="msdhcp01"))
    db.add(SubnetRange(subnet_id=s.id, start_ip="10.10.0.250", end_ip="10.10.0.250",
                        kind="static", label="printer"))
    db.commit()

    r = client.get(f"/api/v1/subnets/{s.id}/ranges")
    assert r.status_code == 200
    rows = {row["start_ip"]: row["source"] for row in r.json()}
    assert rows["10.10.0.1"] == "msdhcp01"
    assert rows["10.10.0.250"] is None
