"""Integration: confirm emission points fire emit() with correct keys.

Collision and rogue wiring tests require a full in-memory scan setup
(real DB session + subnet + ping results). Those paths are verified manually
via the running app; this file covers sync_error, which is fully unit-testable.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.alerting.emit import _queue
from tests.conftest import TestingSessionLocal


def setup_function():
    while not _queue.empty():
        _queue.get_nowait()


# ---------------------------------------------------------------------------
# Stub provider that raises on every method
# ---------------------------------------------------------------------------

class _BrokenProvider:
    source = "broken"

    def get_zones(self):
        raise RuntimeError("boom")

    def get_records(self, *a, **kw):
        raise RuntimeError("boom")

    def get_scopes(self, *a, **kw):
        raise RuntimeError("boom")

    def get_leases(self, *a, **kw):
        raise RuntimeError("boom")

    def supports_ptr(self):
        return False


def _make_session():
    """Return a test-DB session (tables already created by autouse reset_db fixture)."""
    return TestingSessionLocal()


# ---------------------------------------------------------------------------
# sync_error: DNS provider failure
# ---------------------------------------------------------------------------

def test_sync_error_emits_on_dns_provider_failure():
    """sync_dns() catches a per-provider error and calls emit('sync_error', 'sync:<source>')."""
    from app import sync as sync_module

    with patch("app.providers.registry.get_dns_providers",
               return_value=[_BrokenProvider()]), \
         patch("app.sync.SessionLocal", side_effect=_make_session), \
         patch("app.sync.emit") as mock_emit:
        try:
            sync_module.sync_dns()
        except Exception:
            pass  # sync_dns may or may not re-raise; we care about the emit call

    sync_error_calls = [c for c in mock_emit.call_args_list
                        if c.args and c.args[0] == "sync_error"]
    assert len(sync_error_calls) >= 1, (
        f"expected at least one sync_error emit, got: {mock_emit.call_args_list}"
    )
    # Verify the resource_key references the broken provider's source
    keys = [c.args[1] for c in sync_error_calls]
    assert any("broken" in k for k in keys), (
        f"expected 'sync:broken' in emit keys, got: {keys}"
    )


# ---------------------------------------------------------------------------
# sync_error: DHCP provider failure
# ---------------------------------------------------------------------------

def test_sync_error_emits_on_dhcp_provider_failure():
    """sync_dhcp() catches a per-provider error and calls emit('sync_error', 'sync:<source>')."""
    from app import sync as sync_module

    with patch("app.providers.registry.get_dhcp_providers",
               return_value=[_BrokenProvider()]), \
         patch("app.sync.SessionLocal", side_effect=_make_session), \
         patch("app.sync.emit") as mock_emit:
        try:
            sync_module.sync_dhcp()
        except Exception:
            pass

    sync_error_calls = [c for c in mock_emit.call_args_list
                        if c.args and c.args[0] == "sync_error"]
    assert len(sync_error_calls) >= 1, (
        f"expected at least one sync_error emit, got: {mock_emit.call_args_list}"
    )
    keys = [c.args[1] for c in sync_error_calls]
    assert any("broken" in k for k in keys), (
        f"expected 'sync:broken' in emit keys, got: {keys}"
    )


# ---------------------------------------------------------------------------
# sync_error: sync_all() orchestration (both providers broken)
# ---------------------------------------------------------------------------

def test_sync_all_emits_for_both_broken_providers():
    """sync_all() runs dns+dhcp in parallel; both broken providers each produce a sync_error emit."""
    from app import sync as sync_module

    with patch("app.providers.registry.get_dns_providers",
               return_value=[_BrokenProvider()]), \
         patch("app.providers.registry.get_dhcp_providers",
               return_value=[_BrokenProvider()]), \
         patch("app.sync.SessionLocal", side_effect=_make_session), \
         patch("app.sync.emit") as mock_emit:
        try:
            sync_module.sync_all()
        except Exception:
            pass

    sync_error_calls = [c for c in mock_emit.call_args_list
                        if c.args and c.args[0] == "sync_error"]
    assert len(sync_error_calls) >= 2, (
        f"expected sync_error emits from both DNS and DHCP, got: {mock_emit.call_args_list}"
    )
