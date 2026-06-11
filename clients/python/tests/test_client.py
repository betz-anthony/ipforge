import pytest

from ipforge_client import IPForge
from ipforge_client.exceptions import ConfigError
from ipforge_client.resources.subnets import Subnets


def test_requires_base_url_and_token(monkeypatch):
    monkeypatch.delenv("IPFORGE_URL", raising=False)
    monkeypatch.delenv("IPFORGE_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        IPForge()


def test_env_fallback(monkeypatch):
    monkeypatch.setenv("IPFORGE_URL", "http://ipf")
    monkeypatch.setenv("IPFORGE_TOKEN", "ipfg_x")
    c = IPForge()
    assert isinstance(c.subnets, Subnets)


def test_namespaces_share_transport():
    c = IPForge("http://ipf", "ipfg_x")
    assert c.subnets._t is c.addresses._t is c._t


def test_search_hits_search_endpoint(monkeypatch):
    c = IPForge("http://ipf", "ipfg_x")
    captured = {}
    c._t.request = lambda m, p, **kw: captured.update(m=m, p=p, kw=kw) or {"hits": []}
    assert c.search("web") == {"hits": []}
    assert captured["m"] == "GET" and captured["p"] == "/search"
    assert captured["kw"]["params"] == {"q": "web"}
