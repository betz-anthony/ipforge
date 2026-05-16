from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.cache import CachedDNSZone, CachedDNSRecord, CachedDHCPScope, CachedDHCPLease

router = APIRouter()

_VALID_CATEGORIES = {"dns", "dhcp"}


class PurgeResponse(BaseModel):
    category: str
    source: str
    deleted: int


def purge_cache(db: Session, category: str, source: str) -> int:
    """Delete all cache rows for the given category and source. Returns total deleted."""
    if category == "dns":
        d1 = db.query(CachedDNSRecord).filter_by(source=source).delete(synchronize_session=False)
        d2 = db.query(CachedDNSZone).filter_by(source=source).delete(synchronize_session=False)
        return d1 + d2
    else:
        d1 = db.query(CachedDHCPLease).filter_by(source=source).delete(synchronize_session=False)
        d2 = db.query(CachedDHCPScope).filter_by(source=source).delete(synchronize_session=False)
        return d1 + d2


@router.delete("/{category}", response_model=PurgeResponse)
def purge_provider_cache(
    category: str,
    source: str = Query(..., description="Provider name (source slug) to purge"),
    db: Session = Depends(get_db),
):
    if category not in _VALID_CATEGORIES:
        raise HTTPException(400, f"category must be one of: {', '.join(sorted(_VALID_CATEGORIES))}")
    deleted = purge_cache(db, category, source)
    db.commit()
    return PurgeResponse(category=category, source=source, deleted=deleted)
