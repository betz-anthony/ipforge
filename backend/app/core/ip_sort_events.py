"""Keeps ip_sort_key columns in sync with their IP column on every write, so
no call site (API handlers, sync.py's cache upserts) has to remember to set
it itself. Imported once, for its registration side effect, from
app/models/__init__.py."""
from sqlalchemy import event

from app.core.ip_sort import ip_sort_key
from app.models.address import IPAddress
from app.models.cache import CachedDHCPLease


def _sync_address(_mapper, _connection, target: IPAddress) -> None:
    target.ip_sort_key = ip_sort_key(target.address)


def _sync_lease(_mapper, _connection, target: CachedDHCPLease) -> None:
    target.ip_sort_key = ip_sort_key(target.ip_address)


event.listen(IPAddress, "before_insert", _sync_address)
event.listen(IPAddress, "before_update", _sync_address)
event.listen(CachedDHCPLease, "before_insert", _sync_lease)
event.listen(CachedDHCPLease, "before_update", _sync_lease)
