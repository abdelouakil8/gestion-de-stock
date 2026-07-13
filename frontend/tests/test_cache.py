"""Tests for the in-memory API cache (services.cache.AppCache)."""

import threading
import time

from services.cache import AppCache


class TestGetSet:
    def test_miss_returns_false_none(self):
        cache = AppCache()
        hit, value = cache.get("missing")
        assert hit is False
        assert value is None

    def test_set_then_get(self):
        cache = AppCache()
        cache.set("k", {"data": 42})
        hit, value = cache.get("k")
        assert hit is True
        assert value == {"data": 42}

    def test_overwrite(self):
        cache = AppCache()
        cache.set("k", "old")
        cache.set("k", "new")
        _, value = cache.get("k")
        assert value == "new"


class TestTTL:
    def test_expired_entry_is_miss(self):
        cache = AppCache(default_ttl=0.05)
        cache.set("k", "v")
        time.sleep(0.08)
        hit, _ = cache.get("k")
        assert hit is False

    def test_custom_ttl_overrides_default(self):
        cache = AppCache(default_ttl=10.0)
        cache.set("short", "v", ttl=0.05)
        time.sleep(0.08)
        hit, _ = cache.get("short")
        assert hit is False

    def test_fresh_entry_is_hit(self):
        cache = AppCache(default_ttl=10.0)
        cache.set("k", "v")
        hit, value = cache.get("k")
        assert hit is True
        assert value == "v"


class TestInvalidate:
    def test_invalidate_by_prefix(self):
        cache = AppCache()
        cache.set("products:list", [1, 2])
        cache.set("products:detail:1", {"id": 1})
        cache.set("customers:list", [3])
        cache.invalidate("products:")
        assert cache.get("products:list") == (False, None)
        assert cache.get("products:detail:1") == (False, None)
        hit, _ = cache.get("customers:list")
        assert hit is True

    def test_invalidate_multiple_prefixes(self):
        cache = AppCache()
        cache.set("products:list", 1)
        cache.set("customers:list", 2)
        cache.set("categories:list", 3)
        cache.invalidate("products:", "customers:")
        assert cache.get("products:list")[0] is False
        assert cache.get("customers:list")[0] is False
        assert cache.get("categories:list")[0] is True

    def test_invalidate_no_match_is_noop(self):
        cache = AppCache()
        cache.set("k", "v")
        cache.invalidate("other:")
        assert cache.get("k")[0] is True


class TestClear:
    def test_clear_removes_all(self):
        cache = AppCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") == (False, None)
        assert cache.get("b") == (False, None)


class TestThreadSafety:
    def test_concurrent_set_get(self):
        cache = AppCache(default_ttl=5.0)
        errors: list[Exception] = []

        def writer(prefix: str):
            try:
                for i in range(100):
                    cache.set(f"{prefix}:{i}", i)
            except Exception as exc:
                errors.append(exc)

        def reader(prefix: str):
            try:
                for i in range(100):
                    cache.get(f"{prefix}:{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=("a",)),
            threading.Thread(target=writer, args=("b",)),
            threading.Thread(target=reader, args=("a",)),
            threading.Thread(target=reader, args=("b",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
