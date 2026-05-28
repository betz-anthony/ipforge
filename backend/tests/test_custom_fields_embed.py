from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus
from app.models.custom_field import CustomFieldDef


def _mkfield(db, entity_type, name, ftype="text", options=None):
    import json
    f = CustomFieldDef(
        entity_type=entity_type, name=name, label=name.title(), field_type=ftype,
        options=json.dumps(options) if options else None,
    )
    db.add(f)
    db.commit()
    return f


def test_subnet_put_and_read_custom_fields_and_tags(client, db):
    s = Subnet(name="Net", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.commit()
    _mkfield(db, "subnet", "owner")

    r = client.put(f"/api/subnets/{s.id}", json={
        "custom_fields": {"owner": "alice"}, "tags": ["critical", "prod"],
    })
    assert r.status_code == 200, r.text

    row = next(x for x in client.get("/api/subnets").json() if x["id"] == s.id)
    assert row["custom_fields"]["owner"] == "alice"
    assert sorted(row["tags"]) == ["critical", "prod"]


def test_subnet_unknown_field_rejected(client, db):
    s = Subnet(name="Net", cidr="10.0.1.0/24", ip_version=4)
    db.add(s)
    db.commit()
    r = client.put(f"/api/subnets/{s.id}", json={"custom_fields": {"nope": "x"}})
    assert r.status_code == 400


def test_subnet_select_validation(client, db):
    s = Subnet(name="Net", cidr="10.0.2.0/24", ip_version=4)
    db.add(s)
    db.commit()
    _mkfield(db, "subnet", "env", ftype="select", options=["prod", "dev"])
    assert client.put(f"/api/subnets/{s.id}", json={"custom_fields": {"env": "stage"}}).status_code == 400
    assert client.put(f"/api/subnets/{s.id}", json={"custom_fields": {"env": "prod"}}).status_code == 200


def test_subnet_clear_field_with_empty(client, db):
    s = Subnet(name="Net", cidr="10.0.3.0/24", ip_version=4)
    db.add(s)
    db.commit()
    _mkfield(db, "subnet", "owner")
    client.put(f"/api/subnets/{s.id}", json={"custom_fields": {"owner": "bob"}})
    client.put(f"/api/subnets/{s.id}", json={"custom_fields": {"owner": ""}})
    row = next(x for x in client.get("/api/subnets").json() if x["id"] == s.id)
    assert "owner" not in row["custom_fields"]


def test_address_put_and_read_custom_fields_and_tags(client, db):
    s = Subnet(name="Net", cidr="10.0.4.0/24", ip_version=4)
    db.add(s)
    db.flush()
    a = IPAddress(address="10.0.4.5", subnet_id=s.id, status=AddressStatus.assigned)
    db.add(a)
    db.commit()
    _mkfield(db, "address", "role")

    r = client.put(f"/api/addresses/{a.id}", json={
        "custom_fields": {"role": "db"}, "tags": ["managed"],
    })
    assert r.status_code == 200, r.text

    row = next(x for x in client.get("/api/addresses").json() if x["id"] == a.id)
    assert row["custom_fields"]["role"] == "db"
    assert row["tags"] == ["managed"]
