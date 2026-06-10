from ipforge_client.models import Address, AuditEntry
from ipforge_client.pagination import Page, PageIterator, CursorIterator


def test_page_basics():
    p = Page([1, 2, 3], total=10, limit=3, offset=0)
    assert len(p) == 3 and list(p) == [1, 2, 3] and p.total == 10


def test_page_iterator_walks_all_offset_pages():
    pages = {
        0: {"items": [{"id": 1}, {"id": 2}], "total": 3, "limit": 2, "offset": 0},
        2: {"items": [{"id": 3}], "total": 3, "limit": 2, "offset": 2},
    }
    calls = []

    def fetch(params):
        calls.append(params)
        return pages[params["offset"]]

    it = PageIterator(fetch, Address, params={"subnet_id": 5}, page_size=2)
    ids = [a.id for a in it]
    assert ids == [1, 2, 3]
    # filter param threaded into every page request
    assert all(c["subnet_id"] == 5 for c in calls)
    assert it.total == 3


def test_page_iterator_stops_on_empty():
    def fetch(params):
        return {"items": [], "total": 0, "limit": 200, "offset": 0}

    assert list(PageIterator(fetch, Address)) == []


def test_cursor_iterator_follows_next_cursor():
    seq = [
        {"items": [{"id": 1}], "next_cursor": "c1", "limit": 1},
        {"items": [{"id": 2}], "next_cursor": None, "limit": 1},
    ]
    seen_cursors = []

    def fetch(params):
        seen_cursors.append(params.get("cursor"))
        return seq.pop(0)

    out = [e.id for e in CursorIterator(fetch, AuditEntry, page_size=1)]
    assert out == [1, 2]
    assert seen_cursors == [None, "c1"]  # first page no cursor, second follows
