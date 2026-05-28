import json

from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.custom_field import CustomFieldDef


def _field(db, entity_type, name):
    db.add(CustomFieldDef(entity_type=entity_type, name=name, label=name, field_type="text"))
    db.commit()


def test_subnet_tag_filter(client, db):
    a = Subnet(name="A", cidr="10.0.0.0/24", ip_version=4)
    b = Subnet(name="B", cidr="10.0.1.0/24", ip_version=4)
    db.add_all([a, b])
    db.commit()
    client.put(f"/api/subnets/{a.id}", json={"tags": ["prod"]})

    rows = client.get("/api/subnets", params={"tag": "prod"}).json()
    ids = {r["id"] for r in rows}
    assert ids == {a.id}


def test_subnet_custom_field_filter(client, db):
    a = Subnet(name="A", cidr="10.0.2.0/24", ip_version=4)
    b = Subnet(name="B", cidr="10.0.3.0/24", ip_version=4)
    db.add_all([a, b])
    db.commit()
    _field(db, "subnet", "env")
    client.put(f"/api/subnets/{a.id}", json={"custom_fields": {"env": "prod"}})
    client.put(f"/api/subnets/{b.id}", json={"custom_fields": {"env": "dev"}})

    rows = client.get("/api/subnets", params={"cf_env": "prod"}).json()
    assert {r["id"] for r in rows} == {a.id}


def test_subnet_combined_tag_and_field_filter(client, db):
    a = Subnet(name="A", cidr="10.0.4.0/24", ip_version=4)
    b = Subnet(name="B", cidr="10.0.5.0/24", ip_version=4)
    db.add_all([a, b])
    db.commit()
    _field(db, "subnet", "env")
    client.put(f"/api/subnets/{a.id}", json={"custom_fields": {"env": "prod"}, "tags": ["x"]})
    client.put(f"/api/subnets/{b.id}", json={"custom_fields": {"env": "prod"}})

    rows = client.get("/api/subnets", params={"tag": "x", "cf_env": "prod"}).json()
    assert {r["id"] for r in rows} == {a.id}


def test_address_tag_filter(client, db):
    s = Subnet(name="S", cidr="10.0.6.0/24", ip_version=4)
    db.add(s)
    db.flush()
    a1 = IPAddress(address="10.0.6.1", subnet_id=s.id, status=AddressStatus.assigned)
    a2 = IPAddress(address="10.0.6.2", subnet_id=s.id, status=AddressStatus.assigned)
    db.add_all([a1, a2])
    db.commit()
    client.put(f"/api/addresses/{a1.id}", json={"tags": ["managed"]})

    rows = client.get("/api/addresses", params={"tag": "managed"}).json()
    assert {r["id"] for r in rows} == {a1.id}


def test_subnet_csv_includes_custom_fields_and_tags(client, db):
    s = Subnet(name="A", cidr="10.0.7.0/24", ip_version=4)
    db.add(s)
    db.commit()
    _field(db, "subnet", "owner")
    client.put(f"/api/subnets/{s.id}", json={"custom_fields": {"owner": "alice"}, "tags": ["critical"]})

    r = client.get("/api/importexport/subnets.csv")
    assert r.status_code == 200
    text = r.text
    assert "cf_owner" in text.splitlines()[0]
    assert "tags" in text.splitlines()[0]
    assert "alice" in text
    assert "critical" in text
