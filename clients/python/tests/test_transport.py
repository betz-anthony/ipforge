import requests
import pytest

from ipforge_client._transport import _Transport
from ipforge_client.exceptions import (
    NotFoundError, ValidationError, ServerError, TransportError, ForbiddenError,
)
from tests.conftest import FakeResponse


class _SessionStub:
    def __init__(self, responses):
        self.headers = {}
        self._responses = list(responses)
        self.sent = []

    def request(self, method, url, params=None, json=None, timeout=None):
        self.sent.append((method, url))
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _transport_with(responses, retries=2):
    t = _Transport("http://ipf", "ipfg_x", retries=retries)
    t._session = _SessionStub(responses)
    return t


def test_get_returns_json_and_builds_v1_url():
    t = _transport_with([FakeResponse(200, {"ok": True})])
    assert t.request("GET", "/subnets") == {"ok": True}
    assert t._session.sent[0][1] == "http://ipf/api/v1/subnets"


def test_404_maps_to_not_found_with_detail():
    t = _transport_with([FakeResponse(404, {"detail": "missing"})])
    with pytest.raises(NotFoundError) as ei:
        t.request("GET", "/subnets/9")
    assert ei.value.status == 404 and ei.value.detail == "missing"


def test_422_maps_to_validation_error():
    t = _transport_with([FakeResponse(422, {"detail": [{"msg": "bad"}]})])
    with pytest.raises(ValidationError):
        t.request("POST", "/subnets")


def test_403_maps_to_forbidden():
    t = _transport_with([FakeResponse(403, {"detail": "read-only"})])
    with pytest.raises(ForbiddenError):
        t.request("DELETE", "/subnets/1")


def test_5xx_retries_then_raises_server_error():
    t = _transport_with([FakeResponse(500), FakeResponse(500), FakeResponse(500)], retries=2)
    with pytest.raises(ServerError):
        t.request("GET", "/subnets")
    assert len(t._session.sent) == 3  # initial + 2 retries


def test_5xx_then_success_recovers():
    t = _transport_with([FakeResponse(503), FakeResponse(200, {"ok": 1})], retries=2)
    assert t.request("GET", "/subnets") == {"ok": 1}


def test_connection_error_wrapped_as_transport_error():
    t = _transport_with([requests.ConnectionError("boom")], retries=0)
    with pytest.raises(TransportError):
        t.request("GET", "/subnets")
