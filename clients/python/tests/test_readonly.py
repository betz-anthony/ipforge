from ipforge_client.resources.drift import Drift
from ipforge_client.resources.discovery import Discovery
from ipforge_client.resources.audit import Audit


def test_drift_list_filters(fake):
    fake.set("GET", "/drift", [{"id": 1, "category": "missing_dns", "severity": "high"}])
    out = Drift(fake).list(category="missing_dns")
    assert out[0].category == "missing_dns"
    assert fake.calls[0][2] == {"category": "missing_dns"}


def test_discovery_endpoints(fake):
    fake.set("GET", "/discovery/endpoints", [{"ip": "10.0.0.5", "mac": "aa:bb:cc:dd:ee:ff"}])
    out = Discovery(fake).list_endpoints(ip="10.0.0.5")
    assert out[0].mac == "aa:bb:cc:dd:ee:ff"


def test_audit_list_is_cursor_iterator(fake):
    fake.set("GET", "/audit",
             {"items": [{"id": 1, "action": "create"}], "next_cursor": None, "limit": 200})
    out = list(Audit(fake).list(username="admin"))
    assert out[0].action == "create"
    assert fake.calls[0][2]["username"] == "admin"
