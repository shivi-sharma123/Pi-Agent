"""
BaseAgent — abstract base class for all SRE agents.

All agents (Observer, Diagnoser, Remediator, Safety, Orchestrator, Learning)
inherit from BaseAgent to get:
  • Standardised start / stop lifecycle
  • NATS connection management
  • Periodic heartbeat publishing
  • Graceful shutdown on SIGINT / SIGTERM
  • Structured logging with agent identity bound to context

Usage::

    class MyObserver(BaseAgent):
        agent_type = "observer.metrics"

        async def setup(self): ...
        async def run_loop(self): ...
        async def teardown(self): ...
"""

from __future__ import annotations

import abc
import asyncio
import logging
import signal
import socket
import uuid
from datetime import datetime, timezone

from shared.config.settings import settings
from shared.logging.logger import bind_context, get_logger
from shared.messaging.nats_client import NATSClient, build_message
from shared.messaging.subjects import AGENT_HEARTBEAT

logger = get_logger(__name__)


class BaseAgent(abc.ABC):
    """
    Abstract base class for all SRE swarm agents.

    Subclasses must implement:
      - ``agent_type``: class-level string identifier (e.g. 'observer.metrics')
      - ``setup()``:    async setup called once before the main loop
      - ``run_loop()``: async main logic, called in an infinite loop
      - ``teardown()``: async cleanup called on shutdown

    The base class handles NATS connectivity, heartbeats, and shutdown signals.
    """

    # Each subclass sets this to a unique dot-separated identifier
    agent_type: str = "agent.base"

    def __init__(
        self,
        nats_url: str | None = None,
        heartbeat_interval: int | None = None,
        nats_connect_timeout: int | None = None,
    ) -> None:
        # Unique instance ID — useful when running multiple replicas
        self.agent_id = f"{self.agent_type}.{socket.gethostname()}.{uuid.uuid4().hex[:8]}"
        self.nats_url = nats_url or settings.nats_url
        self.heartbeat_interval = heartbeat_interval or settings.agent_heartbeat_interval_seconds
        # How long to wait for NATS to become available on startup (seconds)
        self.nats_connect_timeout = nats_connect_timeout or getattr(
            settings, "nats_connect_timeout_seconds", 10
        )

        self.nats: NATSClient = NATSClient(url=self.nats_url)
        self._running: bool = False
        self._start_time: datetime = datetime.now(timezone.utc)
        self._messages_processed: int = 0
        self._errors: int = 0

        # Bind agent identity to all log statements from this instance
        bind_context(agent_id=self.agent_id, agent_type=self.agent_type)
        self._log = get_logger(self.agent_id)

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """
        Start the agent.  This method runs until the agent is stopped.

        Sequence:
          1. Register OS signal handlers (SIGINT, SIGTERM)
          2. Connect to NATS
          3. Call ``setup()`` for subclass-specific initialisation
          4. Start heartbeat task
          5. Run the main loop (calls ``run_loop()`` repeatedly)
          6. On shutdown: call ``teardown()`` and close NATS
        """
        self._log.info("Agent starting", version="0.1.0")

        # Register graceful shutdown handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        # Connect to NATS (with timeout to avoid blocking forever if NATS is unreachable)
        try:
            await asyncio.wait_for(
                self.nats.connect(),
                timeout=self.nats_connect_timeout,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"NATS connect timeout after {self.nats_connect_timeout}s "
                f"(url={self.nats_url})"
            )
        self._log.info("NATS connected")

        # Subclass setup
        await self.setup()
        self._log.info("Agent setup complete")

        self._running = True

        # Run heartbeat in background
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            while self._running:
                try:
                    await self.run_loop()
                except Exception as exc:
                    self._errors += 1
                    self._log.error("run_loop error", error=str(exc), exc_info=True)
                    # Back-off to avoid tight error loops
                    await asyncio.sleep(5)
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
            await self.teardown()
            await self.nats.close()
            self._log.info("Agent stopped cleanly")

    async def stop(self) -> None:
        """Signal the agent to stop gracefully."""
        self._log.info("Stop signal received")
        self._running = False

    # ------------------------------------------------------------------ #
    # Abstract interface                                                   #
    # ------------------------------------------------------------------ #

    @abc.abstractmethod
    async def setup(self) -> None:
        """Subclass-specific initialisation (subscribe to NATS, open DB, etc.)."""
        ...

    @abc.abstractmethod
    async def run_loop(self) -> None:
        """
        Main agent logic.

        For polling agents (Metrics Observer) this runs once per poll cycle.
        For event-driven agents (Orchestrator) this can be a long-running await.
        """
        ...

    @abc.abstractmethod
    async def teardown(self) -> None:
        """Cleanup on shutdown (flush buffers, close clients, etc.)."""
        ...

    # ------------------------------------------------------------------ #
    # Heartbeat                                                            #
    # ------------------------------------------------------------------ #

    async def _heartbeat_loop(self) -> None:
        """Publish a heartbeat message every ``heartbeat_interval`` seconds."""
        while self._running:
            try:
                await self._publish_heartbeat()
            except Exception as exc:
                self._log.warning("Heartbeat publish failed", error=str(exc))
            await asyncio.sleep(self.heartbeat_interval)

    async def _publish_heartbeat(self) -> None:
        """Build and publish a single heartbeat message."""
        uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        msg = build_message(
            source_agent=self.agent_id,
            target_agent="orchestrator",
            message_type="heartbeat",
            payload={
                "agent_id": self.agent_id,
                "agent_type": self.agent_type,
                "hostname": socket.gethostname(),
                "status": "healthy",
                "uptime_seconds": uptime,
                "messages_processed": self._messages_processed,
                "errors": self._errors,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            priority=3,  # low priority — don't compete with incident traffic
            ttl_seconds=self.heartbeat_interval * 3,  # expires after 3 missed beats
        )
        await self.nats.publish(AGENT_HEARTBEAT, msg)
        self._log.debug("Heartbeat published", uptime_seconds=uptime)

    # ------------------------------------------------------------------ #
    # Helpers for subclasses                                               #
    # ------------------------------------------------------------------ #

    def _increment_processed(self, count: int = 1) -> None:
        """Increment the messages_processed counter (reflected in heartbeat)."""
        self._messages_processed += count

    def _increment_errors(self, count: int = 1) -> None:
        """Increment the errors counter (reflected in heartbeat)."""
        self._errors += count
