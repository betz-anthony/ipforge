import pytest
from fastapi.testclient import TestClient

from app.models.subnet import Subnet
from app.models.address import IPAddress, AddressStatus


@pytest.fixture
def noauth_client(db):
    """TestClient with only the DB overridden — real authentication runs."""
    from app.main import app
    from app.database import get_db

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_metrics_requires_auth(noauth_client):
    r = noauth_client.get("/metrics")
    assert r.status_code == 401


def test_metrics_returns_prometheus_format(client, db):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "ipam_subnets_total" in r.text


def test_metrics_subnet_and_address_counts(client, db):
    s = Subnet(name="m", cidr="10.0.0.0/24", ip_version=4)
    db.add(s)
    db.commit()
    db.add(IPAddress(address="10.0.0.5", subnet_id=s.id, status=AddressStatus.assigned))
    db.commit()

    body = client.get("/metrics").text
    assert "ipam_subnets_total 1.0" in body
    assert 'ipam_addresses{status="assigned"} 1.0' in body
    assert 'ipam_subnet_used_addresses{subnet="10.0.0.0/24"} 1.0' in body


def test_metrics_utilization_ratio(client, db):
    s = Subnet(name="u", cidr="10.0.0.0/30", ip_version=4)   # /30 -> 2 usable hosts
    db.add(s)
    db.commit()
    db.add(IPAddress(address="10.0.0.1", subnet_id=s.id, status=AddressStatus.assigned))
    db.commit()

    body = client.get("/metrics").text
    assert 'ipam_subnet_utilization_ratio{subnet="10.0.0.0/30"} 0.5' in body


def test_metrics_sync_and_collision_families_present(client, db):
    body = client.get("/metrics").text
    assert "ipam_sync_age_seconds" in body
    assert "ipam_sync_ok" in body
    assert "ipam_open_collisions" in body
    assert "ipam_stale_addresses" in body
