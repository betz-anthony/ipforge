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


def test_needs_review_filter(client, db):
    db.add(DriftItem(ip_address="10.0.0.1", category=DriftCategory.multi_dhcp_scope.value,
                     severity="warning", detected_at=_now(), resolved=False, needs_review=True))
    db.add(DriftItem(ip_address="10.0.0.2", category=DriftCategory.missing_dns.value,
                     severity="warning", detected_at=_now(), resolved=False, needs_review=False))
    db.commit()
    rows = client.get("/api/drift", params={"needs_review": "true"}).json()
    assert [d["ip_address"] for d in rows] == ["10.0.0.1"]
    assert rows[0]["needs_review"] is True
