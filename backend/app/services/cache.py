"""TTL-based in-memory cache for leaderboard data."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from backend.app.config import settings


class TTLCache:
    """Simple async-safe TTL cache for leaderboard data.

    Stores cached values with a time-to-live.  Thread-safe through
    ``asyncio.Lock``.
    """

    def __init__(self, default_ttl: int | None = None) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
        self._default_ttl = default_ttl or settings.cache_ttl

    async def get(self, key: str) -> Any | None:
        """Return the cached value for *key*, or ``None`` if expired/missing."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if time.monotonic() > expiry:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store *value* under *key* with an optional custom TTL."""
        async with self._lock:
            expiry = time.monotonic() + (ttl or self._default_ttl)
            self._store[key] = (value, expiry)

    async def invalidate(self, key: str | None = None) -> None:
        """Remove a specific key or clear the entire cache."""
        async with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)


# Global cache instance
cache = TTLCache()
