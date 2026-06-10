import requests

from .exceptions import (
    TransportError, APIError, AuthError, ForbiddenError, NotFoundError,
    ConflictError, ValidationError, ServerError,
)

_STATUS_EXC = {
    401: AuthError,
    403: ForbiddenError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
}


class _Transport:
    """The only object that performs network I/O. All resource methods go
    through .request, so they are unit-testable against a fake transport."""

    def __init__(self, base_url: str, token: str, timeout: float = 30, retries: int = 2):
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._retries = retries
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {token}"

    def request(self, method: str, path: str, *, params=None, json=None):
        url = f"{self._base}/api/v1{path}"
        for attempt in range(self._retries + 1):
            try:
                resp = self._session.request(
                    method, url, params=params, json=json, timeout=self._timeout,
                )
            except requests.RequestException as exc:
                if attempt < self._retries:
                    continue
                raise TransportError(str(exc)) from exc
            if resp.status_code >= 500 and attempt < self._retries:
                continue
            return self._handle(resp)

    @staticmethod
    def _handle(resp):
        if resp.status_code < 400:
            return resp.json() if resp.content else {}
        detail = None
        try:
            body = resp.json()
            detail = body.get("detail") if isinstance(body, dict) else body
        except ValueError:
            detail = resp.text or None
        exc_cls = _STATUS_EXC.get(resp.status_code)
        if exc_cls is None:
            exc_cls = ServerError if resp.status_code >= 500 else APIError
        raise exc_cls(status=resp.status_code, detail=detail)
