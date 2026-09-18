from sqlalchemy import inspect
from app.models.address import IPAddress
from app.models.cache import CachedDHCPLease


def test_ip_addresses_has_ip_sort_key_column(reset_db):
    from tests.conftest import test_engine
    cols = {c["name"] for c in inspect(test_engine).get_columns("ip_addresses")}
    assert "ip_sort_key" in cols


def test_cache_dhcp_leases_has_ip_sort_key_column(reset_db):
    from tests.conftest import test_engine
    cols = {c["name"] for c in inspect(test_engine).get_columns("cache_dhcp_leases")}
    assert "ip_sort_key" in cols
