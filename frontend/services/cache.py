"""Thread-safe in-memory cache with TTL expiration.

All ApiClient methods run on worker threads (via run_api), so every
operation must be safe for concurrent access. A single threading.Lock
guards the store dict; individual entries expire after a configurable TTL.
"""

import threading
import time
from typing import Any


class AppCache:
    def __init__(self, default_ttl: float = 30.0) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl

    def get(self, key: str) -> tuple[bool, Any]:
        """Return (hit, value). On miss or expiry, (False, None)."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False, None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return False, None
            return True, value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        with self._lock:
            t = ttl if ttl is not None else self._default_ttl
            self._store[key] = (time.monotonic() + t, value)

    def invalidate(self, *prefixes: str) -> None:
        """Remove all entries whose key starts with any of the given prefixes."""
        with self._lock:
            to_remove = [
                k for k in self._store if any(k.startswith(p) for p in prefixes)
            ]
            for k in to_remove:
                del self._store[k]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
