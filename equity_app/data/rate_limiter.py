"""
Rate limiting.

Two flavors:
1. Token-bucket (pyrate-limiter) — for APIs with quota / per-minute limits.
2. MinDelayLimiter — for polite scrapers (Finviz) that don't publish a
   formal limit but need a baseline delay between hits.

Decorator helper:
    @with_limiter(_fmp_limiter, name="fmp")
    def _get(...): ...
"""
from __future__ import annotations
import time
import threading
from functools import wraps
from typing import Any, Callable

from core.logging import get_logger

log = get_logger(__name__)


# ============================================================
# Min-delay limiter (Finviz-style polite scraping)
# ============================================================
class MinDelayLimiter:
    """Sleeps so that consecutive calls are at least ``min_delay`` seconds apart."""

    def __init__(self, min_delay: float):
        self.min_delay = float(min_delay)
        self._last_call = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < self.min_delay:
                time.sleep(self.min_delay - elapsed)
            self._last_call = time.monotonic()


# ============================================================
# Token-bucket via pyrate-limiter (with stdlib fallback)
# ============================================================
class _StdlibTokenBucket:
    """
    Minimal token-bucket fallback used when pyrate-limiter is not
    installed. Thread-safe, blocks until a token is available.
    """

    def __init__(self, calls: int, per_seconds: int):
        self.capacity = calls
        self.refill_per_sec = calls / per_seconds
        self.tokens = float(calls)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, _name: str = "default") -> None:
        with self._lock:
            now = time.monotonic()
            self.tokens = min(
                self.capacity,
                self.tokens + (now - self.last_refill) * self.refill_per_sec,
            )
            self.last_refill = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            wait_for = (1.0 - self.tokens) / self.refill_per_sec
        time.sleep(wait_for)
        return self.acquire(_name)


def make_limiter(calls: int, per_seconds: int = 60):
    """Return a token-bucket limiter (pyrate-limiter when available).

    Falls back to the stdlib bucket if pyrate-limiter is missing OR if
    its constructor signature has changed (v4 dropped ``raise_when_fail``
    and ``max_delay``, v5+ may break further). We deliberately avoid the
    removed kwargs — older versions accept the bare ``Rate`` positional.
    """
    try:
        from pyrate_limiter import Duration, Rate, Limiter  # type: ignore

        rate = Rate(calls, Duration.SECOND * per_seconds)
        return Limiter(rate)
    except (ImportError, TypeError, AttributeError) as exc:
        log.info("pyrate_limiter_unavailable_using_stdlib",
                 calls=calls, per=per_seconds, error=str(exc))
        return _StdlibTokenBucket(calls, per_seconds)


# ============================================================
# Decorator
# ============================================================
def with_limiter(limiter: Any, name: str = "default") -> Callable:
    """
    Apply a limiter to a callable.

    Works with both ``MinDelayLimiter`` and the token-bucket types above.
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if isinstance(limiter, MinDelayLimiter):
                limiter.wait()
            elif hasattr(limiter, "try_acquire"):
                limiter.try_acquire(name)        # pyrate-limiter
            elif hasattr(limiter, "acquire"):
                limiter.acquire(name)            # stdlib fallback
            return fn(*args, **kwargs)

        return wrapper
    return decorator
