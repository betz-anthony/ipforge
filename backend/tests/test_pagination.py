from unittest.mock import MagicMock
from app.core.pagination import paginate, _encode_cursor, _decode_cursor
from datetime import datetime


def _make_query(rows, count=None):
    """Return a mock SQLAlchemy query that yields rows."""
    q = MagicMock()
    q.order_by.return_value = q
    q.count.return_value = count if count is not None else len(rows)
    q.offset.return_value = q
    q.limit.return_value = q
    q.all.return_value = rows
    return q


def test_paginate_returns_envelope():
    rows = [object(), object(), object()]
    q = _make_query(rows)
    result = paginate(q, limit=50, offset=0, sort_map={}, sort="", dir="asc")
    assert result["total"] == 3
    assert result["items"] == rows
    assert result["limit"] == 50
    assert result["offset"] == 0


def test_paginate_limit_capped_at_200():
    q = _make_query([])
    result = paginate(q, limit=9999, offset=0, sort_map={}, sort="", dir="asc")
    assert result["limit"] == 200


def test_paginate_limit_floored_at_1():
    q = _make_query([])
    result = paginate(q, limit=0, offset=0, sort_map={}, sort="", dir="asc")
    assert result["limit"] == 1


def test_paginate_offset_floored_at_0():
    q = _make_query([])
    result = paginate(q, limit=50, offset=-10, sort_map={}, sort="", dir="asc")
    q.offset.assert_called_with(0)
    assert result["offset"] == 0


def test_paginate_unknown_sort_not_applied():
    q = _make_query([])
    paginate(q, limit=50, offset=0, sort_map={}, sort="unknown_column", dir="asc")
    # order_by should only be called once (for the count's order_by(None))
    assert q.order_by.call_count == 1


def test_paginate_blank_sort_not_applied():
    q = _make_query([])
    paginate(q, limit=50, offset=0, sort_map={}, sort="", dir="asc")
    # No second order_by call for sort column
    assert q.order_by.call_count == 1  # only the None reset for count


def test_paginate_valid_sort_applied_asc():
    col = MagicMock()
    col.asc.return_value = "col_asc"
    sort_map = {"name": col}
    q = _make_query([])
    paginate(q, limit=50, offset=0, sort_map=sort_map, sort="name", dir="asc")
    col.asc.assert_called_once()


def test_paginate_valid_sort_applied_desc():
    col = MagicMock()
    col.desc.return_value = "col_desc"
    sort_map = {"name": col}
    q = _make_query([])
    paginate(q, limit=50, offset=0, sort_map=sort_map, sort="name", dir="desc")
    col.desc.assert_called_once()


def test_cursor_roundtrip():
    ts = datetime(2026, 1, 15, 10, 30, 0)
    cursor = _encode_cursor(ts, 42)
    decoded_ts, decoded_id = _decode_cursor(cursor)
    assert decoded_id == 42
    assert decoded_ts == ts


def test_decode_cursor_invalid_returns_none():
    assert _decode_cursor("not-valid-base64!!!") is None
    assert _decode_cursor(None) is None
