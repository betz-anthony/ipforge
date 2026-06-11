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


class ServerError(APIError):
    """5xx."""
