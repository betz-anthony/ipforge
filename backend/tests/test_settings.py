import pytest
from app.config import settings as app_settings


@pytest.fixture(autouse=True)
def reset_util_settings():
    yield
    app_settings.util_warn_threshold = 80
    app_settings.util_critical_threshold = 95
    app_settings.util_dashboard_top_n = 5


def test_settings_returns_utilization_defaults(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["util_warn_threshold"] == 80
    assert data["util_critical_threshold"] == 95
    assert data["util_dashboard_top_n"] == 5


def test_settings_update_utilization_thresholds(client):
    r = client.put("/api/settings", json={
        "util_warn_threshold": 70,
        "util_critical_threshold": 90,
        "util_dashboard_top_n": 10,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["util_warn_threshold"] == 70
    assert data["util_critical_threshold"] == 90
    assert data["util_dashboard_top_n"] == 10
