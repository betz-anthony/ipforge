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


def test_list_invalid_status_422(client_admin):
    assert client_admin.get("/api/requests?status=garbage").status_code == 422


def test_submit_as_readonly(client_gr, db):
    """readonly role can submit requests (spec permission matrix)."""
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    r = client_gr.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "rohost", "purpose": "valid purpose here",
    })
    assert r.status_code == 201
    assert r.json()["requester_username"] == "test_readonly"


def test_approve_success(client_admin, client_requester, db):
    from app.models.subnet import Subnet
    from app.models.ip_request import IPRequest
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "newhost", "purpose": "valid purpose here",
    }).json()["id"]
    r = client_admin.put(f"/api/requests/{rid}/approve", json={
        "description": "approved by ops",
        "register_dns": False, "register_dhcp": False,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["allocated_ip"].startswith("10.0.0.")
    db.expire_all()
    req = db.get(IPRequest, rid)
    assert req.status == "approved"
    assert req.reviewer_username == "test_admin"
    assert req.allocated_id is not None


def test_approve_not_pending_409(client_admin, client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    assert client_admin.put(f"/api/requests/{rid}/approve", json={}).status_code == 200
    r2 = client_admin.put(f"/api/requests/{rid}/approve", json={})
    assert r2.status_code == 409


def test_approve_subnet_exhausted_keeps_pending(client_admin, client_requester, db):
    from app.models.subnet import Subnet
    from app.models.address import IPAddress, AddressStatus
    from app.models.ip_request import IPRequest
    s = Subnet(cidr="10.0.0.0/30", name="t", request_eligible=True)  # tiny
    db.add(s); db.commit()
    for ip in ["10.0.0.1", "10.0.0.2"]:
        db.add(IPAddress(address=ip, subnet_id=s.id, status=AddressStatus.assigned))
    db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "wont-fit", "purpose": "valid purpose here",
    }).json()["id"]
    r = client_admin.put(f"/api/requests/{rid}/approve", json={})
    assert r.status_code in (400, 409)
    db.expire_all()
    assert db.get(IPRequest, rid).status == "pending"


def test_approve_requires_operator(client_requester, client_gr, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    assert client_gr.put(f"/api/requests/{rid}/approve", json={}).status_code == 403
    assert client_requester.put(f"/api/requests/{rid}/approve", json={}).status_code == 403


def test_approve_emits_resolved(client_admin, client_requester, db):
    from unittest.mock import patch
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    with patch("app.api.ip_requests.emit") as e:
        client_admin.put(f"/api/requests/{rid}/approve", json={})
    resolved_calls = [c for c in e.mock_calls if c.args and c.args[0] == "ip_request_resolved"]
    assert len(resolved_calls) == 1
    assert resolved_calls[0].args[1] == f"ip_request:{rid}"


def test_deny_success(client_admin, client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    r = client_admin.put(f"/api/requests/{rid}/deny", json={"review_notes": "not approved — bad purpose"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "denied"
    assert body["review_notes"] == "not approved — bad purpose"


def test_deny_requires_notes(client_admin, client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    r = client_admin.put(f"/api/requests/{rid}/deny", json={"review_notes": ""})
    assert r.status_code == 422


def test_deny_not_pending_409(client_admin, client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    client_admin.put(f"/api/requests/{rid}/deny", json={"review_notes": "no"})
    r2 = client_admin.put(f"/api/requests/{rid}/deny", json={"review_notes": "still no"})
    assert r2.status_code == 409


def test_deny_emits_resolved(client_admin, client_requester, db):
    from unittest.mock import patch
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    with patch("app.api.ip_requests.emit") as e:
        client_admin.put(f"/api/requests/{rid}/deny", json={"review_notes": "no"})
    resolved = [c for c in e.mock_calls if c.args and c.args[0] == "ip_request_resolved"]
    assert len(resolved) == 1


def test_delete_own_pending(client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    assert client_requester.delete(f"/api/requests/{rid}").status_code == 204


def test_delete_requester_cant_delete_others(client_requester, client_admin, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_admin.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "admin-req", "purpose": "valid purpose here",
    }).json()["id"]
    assert client_requester.delete(f"/api/requests/{rid}").status_code == 403


def test_delete_requester_cant_delete_approved(client_requester, client_admin, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    client_admin.put(f"/api/requests/{rid}/approve", json={})
    assert client_requester.delete(f"/api/requests/{rid}").status_code == 403


def test_delete_operator_can_delete_any(client_operator, client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    assert client_operator.delete(f"/api/requests/{rid}").status_code == 204


def test_deny_requires_operator(client_gr, client_requester, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_requester.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    assert client_gr.put(f"/api/requests/{rid}/deny", json={"review_notes": "x"}).status_code == 403
    assert client_requester.put(f"/api/requests/{rid}/deny", json={"review_notes": "x"}).status_code == 403


def test_delete_readonly_403(client_gr, client_admin, db):
    from app.models.subnet import Subnet
    s = Subnet(cidr="10.0.0.0/29", name="t", request_eligible=True)
    db.add(s); db.commit()
    rid = client_admin.post("/api/requests", json={
        "subnet_id": s.id, "hostname": "h", "purpose": "valid purpose here",
    }).json()["id"]
    assert client_gr.delete(f"/api/requests/{rid}").status_code == 403


def test_delete_not_found_404(client_admin):
    assert client_admin.delete("/api/requests/99999").status_code == 404
