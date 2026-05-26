"""Tests for IP-REQUEST-001 Task 3: submit + list + eligible-subnets + get APIs."""


def test_submit_request_as_requester(client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    r = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "myhost",
        "mac_address": None, "purpose": "new server for stack X",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["hostname"] == "myhost"
    assert body["requester_username"] == "test_requester"


def test_submit_ineligible_subnet_400(client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=False)
    db.add(s); db.commit()
    r = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "host", "purpose": "valid purpose here",
    })
    assert r.status_code == 400


def test_submit_invalid_hostname_422(client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    r = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "BAD HOST!!", "purpose": "valid purpose here",
    })
    assert r.status_code == 422


def test_submit_purpose_too_short_422(client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    r = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "host", "purpose": "x",
    })
    assert r.status_code == 422


def test_submit_duplicate_pending_409(client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    body = {"subnet_id": s.id, "hostname": "dup", "purpose": "valid purpose here"}
    assert client_requester.post("/api/requests", json=body).status_code == 201
    r2 = client_requester.post("/api/requests", json=body)
    assert r2.status_code == 409


def test_submit_scoped_403(client_scoped, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    r = client_scoped.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "host", "purpose": "valid purpose here",
    })
    assert r.status_code == 403


def test_list_requester_sees_only_own(client_requester, client_admin, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "rhost", "purpose": "valid purpose here",
    })
    client_admin.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "ahost", "purpose": "valid purpose here",
    })
    r = client_requester.get("/api/requests")
    assert r.status_code == 200
    body = r.json()
    assert all(req["requester_username"] == "test_requester" for req in body)
    assert len(body) == 1


def test_list_admin_sees_all(client_requester, client_admin, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h1", "purpose": "valid purpose here",
    })
    client_admin.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h2", "purpose": "valid purpose here",
    })
    r = client_admin.get("/api/requests")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_filter_by_status(client_admin, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    client_admin.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    })
    r = client_admin.get("/api/requests?status=pending")
    assert r.status_code == 200
    assert all(req["status"] == "pending" for req in r.json())


def test_list_scoped_403(client_scoped):
    assert client_scoped.get("/api/requests").status_code == 403


def test_eligible_subnets_filters(client_requester, db):
    from app.models.subnet import Subnet
    db.add_all([
        Subnet(cidr="10.0.0.0/29", name="yes", request_eligible=True),
        Subnet(cidr="10.0.1.0/29", name="no",  request_eligible=False),
    ])
    db.commit()
    r = client_requester.get("/api/requests/eligible-subnets")
    assert r.status_code == 200
    body = r.json()
    cidrs = [s["cidr"] for s in body]
    assert "10.0.0.0/29" in cidrs
    assert "10.0.1.0/29" not in cidrs


def test_get_one_requester_own_only(client_requester, client_admin, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_admin.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "admin-req", "purpose": "valid purpose here",
    }).json()["id"]
    assert client_requester.get(f"/api/requests/{rid}").status_code == 403


def test_submit_alerting_emit_fired(client_requester, db):
    from unittest.mock import patch
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    with patch("app.api.ip_requests.emit") as e:
        client_requester.post("/api/requests", json={
            "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
        })
    submitted_calls = [c for c in e.mock_calls if c.args and c.args[0] == "ip_request_submitted"]
    assert len(submitted_calls) == 1
