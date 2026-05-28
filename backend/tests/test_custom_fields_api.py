from app.models.custom_field import CustomFieldDef, CustomFieldValue, Tag


def test_create_and_list_field_def(client, db):
    r = client.post("/api/custom-fields", json={
        "entity_type": "subnet", "name": "owner", "label": "Owner", "field_type": "text",
    })
    assert r.status_code == 201, r.text
    fid = r.json()["id"]

    r = client.get("/api/custom-fields", params={"entity_type": "subnet"})
    assert r.status_code == 200
    names = [f["name"] for f in r.json()]
    assert "owner" in names

    # filtered out for other entity type
    r = client.get("/api/custom-fields", params={"entity_type": "address"})
    assert all(f["id"] != fid for f in r.json())


def test_select_field_requires_options(client, db):
    r = client.post("/api/custom-fields", json={
        "entity_type": "subnet", "name": "env", "label": "Env", "field_type": "select",
    })
    assert r.status_code == 400

    r = client.post("/api/custom-fields", json={
        "entity_type": "subnet", "name": "env", "label": "Env",
        "field_type": "select", "options": ["prod", "dev"],
    })
    assert r.status_code == 201
    assert r.json()["options"] == ["prod", "dev"]


def test_invalid_field_type_rejected(client, db):
    r = client.post("/api/custom-fields", json={
        "entity_type": "subnet", "name": "x", "label": "X", "field_type": "bogus",
    })
    assert r.status_code == 422


def test_duplicate_name_same_entity_conflict(client, db):
    body = {"entity_type": "subnet", "name": "owner", "label": "Owner", "field_type": "text"}
    assert client.post("/api/custom-fields", json=body).status_code == 201
    assert client.post("/api/custom-fields", json=body).status_code == 409


def test_delete_field_cascades_values(client, db):
    f = CustomFieldDef(entity_type="subnet", name="owner", label="Owner", field_type="text")
    db.add(f)
    db.flush()
    db.add(CustomFieldValue(field_id=f.id, entity_id=1, value="alice"))
    db.commit()
    fid = f.id

    r = client.delete(f"/api/custom-fields/{fid}")
    assert r.status_code == 204
    assert db.query(CustomFieldValue).filter_by(field_id=fid).count() == 0


def test_non_admin_cannot_create_field(client_operator, db):
    r = client_operator.post("/api/custom-fields", json={
        "entity_type": "subnet", "name": "owner", "label": "Owner", "field_type": "text",
    })
    assert r.status_code == 403


def test_tags_create_list_delete(client, db):
    r = client.post("/api/tags", json={"name": "critical"})
    assert r.status_code == 201
    tid = r.json()["id"]

    r = client.get("/api/tags")
    assert "critical" in [t["name"] for t in r.json()]

    # duplicate
    assert client.post("/api/tags", json={"name": "critical"}).status_code == 409

    assert client.delete(f"/api/tags/{tid}").status_code == 204
    assert db.query(Tag).filter_by(id=tid).count() == 0


def test_operator_can_create_tag(client_operator, db):
    r = client_operator.post("/api/tags", json={"name": "new"})
    assert r.status_code == 201
