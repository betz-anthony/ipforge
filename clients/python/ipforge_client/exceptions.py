class IPForgeError(Exception):
    """Base for all client errors."""


class ConfigError(IPForgeError):
    """Missing/invalid client configuration (base_url or token)."""


class TransportError(IPForgeError):
    """Network failure or timeout (wraps the underlying requests exception)."""


class APIError(IPForgeError):
    """Non-2xx HTTP response. Carries the status code and server detail."""

    def __init__(self, status: int, detail=None):
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail}")


class AuthError(APIError):
    """401 — missing/invalid credentials."""


class ForbiddenError(APIError):
    """403 — authenticated but not allowed (e.g. read-only token writing)."""


class NotFoundError(APIError):
    """404."""


class ConflictError(APIError):
    """409."""


class ValidationError(APIError):
    """422 — request failed server validation; see .detail."""


class PoolNotSupportedError(IPForgeError):
    """An allocation was requested from a pool but the server did not honour it
    (typically a server release without allocation pools). The server has
    already allocated `result["address"]` from the whole subnet; release it if
    it is not wanted."""

    def __init__(self, pool: str, result: dict):
        self.pool = pool
        self.result = result
        super().__init__(
            f'server did not allocate from pool "{pool}" (it may not support allocation pools); '
            f'it allocated {result.get("address")} instead'
        )


class ServerError(APIError):
    """5xx."""
