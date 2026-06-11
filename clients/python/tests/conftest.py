import pytest


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text="", content=b"{}"):
        self.status_code = status_code
        self._json = {} if json_body is None else json_body
        self.text = text
        self.content = content if json_body is None else b"x"

    def json(self):
        return self._json


class FakeTransport:
    """Records (method, path, params, json) calls and returns queued responses.
    Used to unit-test resource methods without the network."""

    def __init__(self):
        self.calls = []
        self._returns = {}

    def set(self, method, path, value):
        self._returns[(method, path)] = value

    def request(self, method, path, *, params=None, json=None):
        self.calls.append((method, path, params, json))
        return self._returns.get((method, path), {})


@pytest.fixture
def fake():
    return FakeTransport()
