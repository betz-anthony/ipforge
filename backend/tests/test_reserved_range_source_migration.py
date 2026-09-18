from sqlalchemy import inspect
# Import models to ensure they're registered with Base
from app.models.subnet_range import SubnetRange
from app.models.cache import CachedDHCPScopePool


def test_subnet_range_has_source_column(reset_db):
    """Verify that SubnetRange model has the source column."""
    from tests.conftest import test_engine
    cols = {c["name"] for c in inspect(test_engine).get_columns("subnet_ranges")}
    assert "source" in cols


def test_cache_dhcp_scope_pools_table_exists(reset_db):
    """Verify that CachedDHCPScopePool model creates the cache table."""
    from tests.conftest import test_engine
    assert "cache_dhcp_scope_pools" in inspect(test_engine).get_table_names()
