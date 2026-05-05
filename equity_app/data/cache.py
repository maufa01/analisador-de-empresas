"""
Cache layer.

Two backends behind a single interface:
- ``disk``  — diskcache.Cache, single-user / Streamlit Community Cloud
- ``redis`` — for multi-user deployments (selected via CACHE_BACKEND=redis)

Public surface:
    @cached("quote", ttl=5)
    def fetch_quote(ticker): ...

    cache_clear("quote")            # invalidate all "quote:*" keys

Cache keys are namespaced (``"<prefix>:<hash>"``) so we can clear an entire
data category without touching others. Hashing uses md5 over the pickled
function signature — collisions are negligible for this workload.
"""
from __future__ import annotations
import hashlib
import pickle
import threading
from functools import wraps
from typing import Callable, Any

from core.config import settings
from core.logging import get_logger

log = get_logger(__name__)

_cache_singleton: Any = None
_lock = threading.Lock()


# ============================================================
# Backend factory
# ============================================================
class _MemoryFallback:
    """In-process dict cache used when neither diskcache nor redis is installed."""

    def __init__(self) -> None:
        self._d: dict[str, tuple[float, Any]] = {}

    def get(self, key: str, default: Any = None) -> Any:
        import time
        v = self._d.get(key)
        if v is None:
            return default
        expires, value = v
        if expires and time.time() > expires:
            del self._d[key]
            return default
        return value

    def set(self, key: str, value: Any, expire: int | None = None) -> None:
        import time
        expires_at = (time.time() + expire) if expire else 0
        self._d[key] = (expires_at, value)

    def __delitem__(self, key: str) -> None:
        self._d.pop(key, None)

    def __iter__(self):
        return iter(list(self._d.keys()))

    def __contains__(self, key: str) -> bool:
        return key in self._d

    def clear(self) -> None:
        self._d.clear()


def _build_backend() -> Any:
    backend = settings.cache_backend
    if backend == "redis":
        try:
            import redis  # type: ignore
            client = redis.Redis.from_url(settings.redis_url, decode_responses=False)
            client.ping()
            log.info("cache_backend", backend="redis", url=settings.redis_url)
            return _RedisAdapter(client)
        except Exception as e:
            log.warning("redis_unavailable_fallback_disk", error=str(e))

    try:
        import diskcache as dc  # type: ignore
        cache = dc.Cache(settings.cache_dir, size_limit=int(2 * 1024**3))
        log.info("cache_backend", backend="disk", dir=settings.cache_dir)
        return cache
    except Exception as e:
        log.warning("diskcache_unavailable_fallback_memory", error=str(e))
        return _MemoryFallback()


class _RedisAdapter:
    """Thin adapter so the rest of the code doesn't care about the backend."""

    def __init__(self, client):
        self.c = client

    def get(self, key: str, default: Any = None) -> Any:
        v = self.c.get(key)
        if v is None:
            return default
        try:
            return pickle.loads(v)
        except Exception:
            return default

    def set(self, key: str, value: Any, expire: int | None = None) -> None:
        self.c.set(key, pickle.dumps(value), ex=expire)

    def __delitem__(self, key: str) -> None:
        self.c.delete(key)

    def __iter__(self):
        return iter(self.c.scan_iter("*"))

    def __contains__(self, key: str) -> bool:
        return bool(self.c.exists(key))

    def clear(self) -> None:
        self.c.flushdb()


def get_cache() -> Any:
    global _cache_singleton
    if _cache_singleton is not None:
        return _cache_singleton
    with _lock:
        if _cache_singleton is None:
            _cache_singleton = _build_backend()
    return _cache_singleton


# ============================================================
# Decorator
# ============================================================
def _make_key(prefix: str, fn_name: str, args: tuple, kwargs: dict) -> str:
    payload = pickle.dumps((prefix, fn_name, args, sorted(kwargs.items())))
    return f"{prefix}:{fn_name}:{hashlib.md5(payload).hexdigest()}"


def cached(prefix: str, ttl: int) -> Callable:
    """
    Cache decorator with namespaced prefix.

    Use a ``CACHE_TTL`` constant for TTL — never hardcode here.
    Falsy results (None, empty DataFrame) are NOT cached so a transient
    failure doesn't poison the cache.
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                key = _make_key(prefix, fn.__name__, args, kwargs)
            except Exception:
                # Args not picklable — bypass cache rather than crash
                return fn(*args, **kwargs)

            cache = get_cache()
            hit = cache.get(key)
            if hit is not None:
                return hit

            result = fn(*args, **kwargs)
            try:
                _is_empty = result is None or (
                    hasattr(result, "empty") and getattr(result, "empty", False)
                )
            except Exception:
                _is_empty = result is None
            if not _is_empty:
                try:
                    cache.set(key, result, expire=ttl)
                except Exception as e:
                    log.warning("cache_set_failed", key=key, error=str(e))
            return result

        return wrapper
    return decorator


def cache_clear(prefix: str | None = None) -> int:
    """Invalidate keys. ``prefix=None`` clears EVERYTHING."""
    cache = get_cache()
    if prefix is None:
        cache.clear()
        return -1
    n = 0
    for key in list(cache):
        k = key.decode() if isinstance(key, bytes) else key
        if isinstance(k, str) and k.startswith(f"{prefix}:"):
            try:
                del cache[key]
                n += 1
            except Exception:
                pass
    return n
