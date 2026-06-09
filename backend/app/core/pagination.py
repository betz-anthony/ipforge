import base64
from datetime import datetime


def paginate(query, *, limit: int, offset: int, sort_map: dict, sort: str, dir: str) -> dict:
    total = query.order_by(None).count()
    col = sort_map.get(sort or "")
    if col is not None:
        query = query.order_by(col.desc() if dir == "desc" else col.asc())
    limit = min(max(limit, 1), 200)
    items = query.offset(max(offset, 0)).limit(limit).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _encode_cursor(timestamp: datetime, row_id: int) -> str:
    raw = f"{timestamp.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str | None) -> tuple[datetime, int] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(ts_str), int(id_str)
    except Exception:
        return None
