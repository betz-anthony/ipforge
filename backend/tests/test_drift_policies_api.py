from datetime import datetime, timezone

from app.models.scan import DriftItem, DriftPolicy, DriftCategory


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_upsert_and_list_policy(client, db):
    r = client.put("/api/drift/policies/orphan_dhcp", json={"mode": "auto", "dry_run": True})
    assert r.status_code == 200, r.text
    rows = client.get("/api/drift/policies").json()
    assert any(p["category"] == "orphan_dhcp" and p["mode"] == "auto" for p in rows)


def test_auto_rejected_for_unsafe_category(client, db):
    r = client.put("/api/drift/policies/multi_dhcp_scope", json={"mode": "auto"})
    assert r.status_code == 400


def test_review_allowed_for_unsafe(client, db):
    r = client.put("/api/drift/policies/multi_dhcp_scope", json={"mode": "review"})
    assert r.status_code == 200


def test_invalid_target_status(client, db):
    r = client.put("/api/drift/policies/active_but_available",
                   json={"mode": "auto", "params": {"target_status": "bogus"}})
    assert r.status_code == 400


def test_delete_policy(client, db):
    client.put("/api/drift/policies/orphan_dns", json={"mode": "auto"})
    assert client.delete("/api/drift/policies/orphan_dns").status_code == 204
    assert db.query(DriftPolicy).filter_by(category="orphan_dns").count() == 0


def test_policy_requires_admin(client_operator, db):
    r = client_operator.put("/api/drift/policies/orphan_dhcp", json={"mode": "auto"})
    assert r.status_code == 403


def test_policy_with_provider_action_allowed_auto(client, db):
    r = client.put("/api/drift/policies/missing_dns",
                   json={"mode": "auto", "params": {"action": "push_dns", "zone": "example.com"}})
    assert r.status_code == 200, r.text
    assert r.json()["params"]["action"] == "push_dns"


def test_subnet_policy_create_and_list(client, db):
    from app.models.subnet import Subnet
    s = Subnet(name="T", cidr="10.1.0.0/24", ip_version=4)
    db.add(s); db.commit()
    r = client.put("/api/drift/policies/orphan_dhcp",
                   json={"mode": "auto", "dry_run": False, "subnet_id": s.id})
    assert r.status_code == 200, r.text
    assert r.json()["subnet_id"] == s.id
    rows = client.get("/api/drift/policies").json()
    sub_pol = next((p for p in rows if p["subnet_id"] == s.id), None)
    assert sub_pol is not None and sub_pol["category"] == "orphan_dhcp"


def test_subnet_policy_overrides_global_in_list(client, db):
    from app.models.subnet import Subnet
    s = Subnet(name="T", cidr="10.1.0.0/24", ip_version=4)
    db.add(s); db.commit()
    client.put("/api/drift/policies/orphan_dhcp", json={"mode": "review"})
    client.put("/api/drift/policies/orphan_dhcp", json={"mode": "auto", "subnet_id": s.id})
    rows = client.get("/api/drift/policies").json()
    global_pol = next((p for p in rows if p["category"] == "orphan_dhcp" and p["subnet_id"] is None), None)
    sub_pol = next((p for p in rows if p["category"] == "orphan_dhcp" and p["subnet_id"] == s.id), None)
    assert global_pol is not None and global_pol["mode"] == "review"
    assert sub_pol is not None and sub_pol["mode"] == "auto"


def test_delete_subnet_policy(client, db):
    from app.models.subnet import Subnet
    s = Subnet(name="T", cidr="10.1.0.0/24", ip_version=4)
    db.add(s); db.commit()
    client.put("/api/drift/policies/orphan_dhcp", json={"mode": "auto", "subnet_id": s.id})
    r = client.delete(f"/api/drift/policies/orphan_dhcp?subnet_id={s.id}")
    assert r.status_code == 204
    assert db.query(DriftPolicy).filter_by(category="orphan_dhcp", subnet_id=s.id).count() == 0


def test_needs_review_filter(client, db):
    db.add(DriftItem(ip_address="10.0.0.1", category=DriftCategory.multi_dhcp_scope.value,
                     severity="warning", detected_at=_now(), resolved=False, needs_review=True))
    db.add(DriftItem(ip_address="10.0.0.2", category=DriftCategory.missing_dns.value,
                     severity="warning", detected_at=_now(), resolved=False, needs_review=False))
    db.commit()
    rows = client.get("/api/drift", params={"needs_review": "true"}).json()
    assert [d["ip_address"] for d in rows] == ["10.0.0.1"]
    assert rows[0]["needs_review"] is True
