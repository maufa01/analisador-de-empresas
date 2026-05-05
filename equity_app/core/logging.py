"""
Structlog configuration.

Two renderers:
- JSON     — production / aggregator-friendly
- Console  — local dev, human-readable, with colors when TTY supports it

Usage:
    from core.logging import get_logger
    log = get_logger(__name__)
    log.info("fetched", ticker="AAPL", source="fmp", ms=43)

The first call to get_logger() lazily configures structlog. We avoid
configuring at import-time so that test runners and notebooks can override.
"""
from __future__ import annotations
import logging
import sys

try:
    import structlog
    _STRUCTLOG = True
except ImportError:  # tests/sandbox without deps installed
    _STRUCTLOG = False

from .config import settings

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED or not _STRUCTLOG:
        _CONFIGURED = True
        return

    log_level = getattr(logging, str(settings.log_level).upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


class _StdlibKwargAdapter:
    """
    Adapter so call sites can use structlog-style kwargs uniformly.

    structlog: ``log.info("event", ticker="AAPL", ms=42)``
    stdlib:    rendered as ``"event ticker=AAPL ms=42"``
    """

    def __init__(self, name: str | None) -> None:
        self._log = logging.getLogger(name)

    def _emit(self, level: int, msg: str, **kwargs: object) -> None:
        if kwargs:
            extras = " ".join(f"{k}={v}" for k, v in kwargs.items())
            self._log.log(level, "%s %s", msg, extras)
        else:
            self._log.log(level, "%s", msg)

    def debug(self, msg: str, **kw: object) -> None:    self._emit(logging.DEBUG, msg, **kw)
    def info(self, msg: str, **kw: object) -> None:     self._emit(logging.INFO, msg, **kw)
    def warning(self, msg: str, **kw: object) -> None:  self._emit(logging.WARNING, msg, **kw)
    def error(self, msg: str, **kw: object) -> None:    self._emit(logging.ERROR, msg, **kw)
    def exception(self, msg: str, **kw: object) -> None:
        self._log.exception(msg)


def get_logger(name: str | None = None):
    """
    Return a structlog logger. Falls back to a kwarg-tolerant stdlib
    adapter when structlog is not installed (sandbox / minimal CI).
    """
    _configure()
    if _STRUCTLOG:
        return structlog.get_logger(name) if name else structlog.get_logger()
    return _StdlibKwargAdapter(name)
