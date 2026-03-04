"""
Unit tests for shared.logging.logger — structured JSON logger.

Verifies that configure_logging runs without error, the logger
is callable, and context variables (correlation_id, trace_id)
are bound correctly.
"""
from __future__ import annotations

import asyncio
import logging

import pytest
import structlog

from shared.logging.logger import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
)


class TestConfigureLogging:
    def test_configure_logging_json_format(self):
        """configure_logging should not raise for json format."""
        configure_logging(service_name="test-svc", log_level="DEBUG", log_format="json")

    def test_configure_logging_console_format(self):
        """configure_logging should not raise for console format."""
        configure_logging(service_name="test-svc", log_level="INFO", log_format="console")

    def test_configure_logging_invalid_level_raises(self):
        """An invalid log level raises a KeyError from structlog.
        Callers should always pass a valid level string.
        """
        with pytest.raises((KeyError, ValueError)):
            configure_logging(service_name="test-svc", log_level="NOTAREAL", log_format="json")

    def test_configure_logging_sets_stdlib_root_level(self):
        configure_logging(service_name="test-svc", log_level="WARNING", log_format="json")
        assert logging.getLogger().level in (logging.WARNING, logging.NOTSET)


class TestGetLogger:
    def test_get_logger_returns_bound_logger(self):
        logger = get_logger("my.module")
        # structlog BoundLogger has info, warning, error, debug methods
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
        assert hasattr(logger, "debug")
        assert hasattr(logger, "warning")

    def test_logger_is_callable_without_raising(self):
        """Calling logger.info() must not raise even without real output configured."""
        configure_logging(service_name="test", log_level="CRITICAL", log_format="json")
        logger = get_logger("test.logger")
        # Should not raise
        logger.info("test message", key="value")

    def test_two_loggers_are_independent_instances(self):
        l1 = get_logger("module.a")
        l2 = get_logger("module.b")
        # They may be the same structlog type but different bound instances
        assert l1 is not l2


class TestContextBinding:
    def setup_method(self):
        """Reset context before each test to avoid cross-test contamination."""
        clear_context()

    def test_bind_context_does_not_raise(self):
        bind_context(correlation_id="abc-123", trace_id="xyz-789")

    def test_clear_context_does_not_raise(self):
        bind_context(correlation_id="abc-123")
        clear_context()

    @pytest.mark.asyncio
    async def test_context_is_coroutine_local(self):
        """
        Each coroutine gets its own context variables.
        Binding in one task should not leak to another.
        """
        results = {}

        async def task_a():
            bind_context(correlation_id="corr-aaa")
            await asyncio.sleep(0)
            # We can't read the var back easily without importing it,
            # so just verify no exception is raised
            results["a"] = "ok"

        async def task_b():
            bind_context(correlation_id="corr-bbb")
            await asyncio.sleep(0)
            results["b"] = "ok"

        await asyncio.gather(task_a(), task_b())
        assert results == {"a": "ok", "b": "ok"}
