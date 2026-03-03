"""
Structured JSON logging for all agents and services.

Uses structlog to produce consistent, machine-parseable JSON logs with:
  • timestamp (ISO-8601)
  • log level
  • logger name
  • correlation_id / trace_id (bound to async context)
  • service name

Usage::

    from shared.logging.logger import get_logger, bind_context

    log = get_logger(__name__)

    # Bind request-scoped fields for all log statements in this handler
    bind_context(correlation_id="abc-123", trace_id="xyz-789")

    log.info("Processing anomaly", service="user-svc", anomaly_id="...")
    log.error("Publish failed", error=str(exc))
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

# ContextVar storage for per-task fields (works with asyncio correctly)
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


def configure_logging(
    service_name: str,
    log_level: str = "INFO",
    log_format: str = "json",
) -> None:
    """
    Configure structlog for a service or agent.

    Call this once at application startup, before creating any loggers.

    Args:
        service_name: Identifier included in every log line (e.g. 'user-svc').
        log_level:    Python log level string ('DEBUG', 'INFO', 'WARNING', …).
        log_format:   'json' for production, 'console' for local dev.
    """
    # Bind the service name globally so every log line carries it
    bind_contextvars(service=service_name)

    shared_processors: list[Any] = [
        # Merge any context variables bound via bind_contextvars / bind_context
        merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    if log_format == "json":
        # Production: newline-delimited JSON (compatible with Loki / Promtail)
        renderer = structlog.processors.JSONRenderer()
    else:
        # Local dev: pretty coloured output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib so that third-party libraries (uvicorn, etc.)
    # route through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(log_level.upper()),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a named structlog logger.

    Args:
        name: Typically __name__ of the calling module.

    Returns:
        A bound logger that emits structured log events.
    """
    return structlog.get_logger(name)


def bind_context(
    correlation_id: str | None = None,
    trace_id: str | None = None,
    **extra: Any,
) -> None:
    """
    Bind fields to the current async context.

    All subsequent log statements in the same asyncio Task will automatically
    include these fields without needing to pass them explicitly.

    Args:
        correlation_id: Incident / request correlation identifier.
        trace_id:       Distributed tracing identifier.
        **extra:        Any additional key-value pairs to bind.
    """
    context: dict[str, Any] = {**extra}
    if correlation_id:
        context["correlation_id"] = correlation_id
    if trace_id:
        context["trace_id"] = trace_id
    bind_contextvars(**context)


def clear_context() -> None:
    """
    Clear all context variables for the current async Task.

    Call this at the end of a request handler or after an incident lifecycle
    completes to avoid context bleed between tasks.
    """
    clear_contextvars()
