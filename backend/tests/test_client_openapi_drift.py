import pathlib
import re
import sys

from app.main import app

# Make the in-tree client package importable (data-only _coverage module).
_CLIENT = pathlib.Path(__file__).resolve().parents[2] / "clients" / "python"
sys.path.insert(0, str(_CLIENT))
from ipforge_client._coverage import COVERED, DEFERRED, IN_SCOPE_PREFIXES  # noqa: E402

_METHODS = {"get", "post", "put", "delete", "patch"}


def _normalize(path: str) -> str:
    assert path.startswith("/api/v1"), path
    rel = path[len("/api/v1"):]
    return re.sub(r"\{[^}]+\}", "{}", rel)


def _in_scope_ops() -> set:
    ops = set()
    for raw_path, methods in app.openapi()["paths"].items():
        if not raw_path.startswith("/api/v1"):
            continue
        norm = _normalize(raw_path)
        first_seg = norm.strip("/").split("/")[0]
        if first_seg not in IN_SCOPE_PREFIXES:
            continue
        for method in methods:
            if method.lower() in _METHODS:
                ops.add((method.upper(), norm))
    return ops


def test_no_in_scope_endpoint_is_unaccounted():
    ops = _in_scope_ops()
    unaccounted = ops - COVERED - DEFERRED
    assert not unaccounted, (
        "In-scope /api/v1 endpoints are neither covered nor deferred by the "
        f"Python client — cover them or add to DEFERRED: {sorted(unaccounted)}"
    )


def test_client_targets_no_dead_endpoints():
    ops = _in_scope_ops()
    dead = COVERED - ops
    assert not dead, (
        f"Python client COVERED ops absent from the live API: {sorted(dead)}"
    )
