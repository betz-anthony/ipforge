from typing import Any, Callable, Dict, Iterator, List, Optional, Type

_DEFAULT_PAGE_SIZE = 200


class Page:
    """A single page of results from an offset-paginated endpoint."""

    def __init__(self, items: list, total: int, limit: int, offset: int):
        self.items = items
        self.total = total
        self.limit = limit
        self.offset = offset

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)


class PageIterator:
    """Lazily walks offset pages, yielding model instances across all pages."""

    def __init__(self, fetch: Callable[[Dict[str, Any]], dict],
                 model: Type, params: Optional[dict] = None,
                 page_size: int = _DEFAULT_PAGE_SIZE):
        self._fetch = fetch
        self._model = model
        self._params = dict(params or {})
        self._page_size = page_size
        self._total: Optional[int] = None

    @property
    def total(self) -> int:
        if self._total is None:
            env = self._fetch({**self._params, "limit": 1, "offset": 0})
            self._total = env.get("total", 0)
        return self._total

    def __iter__(self) -> Iterator:
        offset = 0
        while True:
            env = self._fetch({**self._params, "limit": self._page_size, "offset": offset})
            self._total = env.get("total", 0)
            items = env.get("items", [])
            for it in items:
                yield self._model(it)
            offset += len(items)
            if not items or offset >= self._total:
                break

    def list(self) -> List:
        return list(self)


class CursorIterator:
    """Walks a cursor-paginated endpoint, following next_cursor until exhausted."""

    def __init__(self, fetch: Callable[[Dict[str, Any]], dict],
                 model: Type, params: Optional[dict] = None,
                 page_size: int = _DEFAULT_PAGE_SIZE):
        self._fetch = fetch
        self._model = model
        self._params = dict(params or {})
        self._page_size = page_size

    def __iter__(self) -> Iterator:
        cursor = None
        while True:
            p = {**self._params, "limit": self._page_size}
            if cursor:
                p["cursor"] = cursor
            env = self._fetch(p)
            for it in env.get("items", []):
                yield self._model(it)
            cursor = env.get("next_cursor")
            if not cursor:
                break

    def list(self) -> List:
        return list(self)
