"""
Async NATS JetStream client wrapper.

Provides high-level publish / subscribe / request-reply helpers with:
  • Automatic reconnection
  • Exponential backoff on publish failures
  • AgentMessage serialisation / deserialisation
  • Subject-based routing helpers
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import Awaitable, Callable
from typing import Any

import nats
import nats.js
from nats.aio.client import Client as NATSConnection
from nats.aio.msg import Msg
from nats.js import JetStreamContext

from shared.messaging.schema import AgentMessage

logger = logging.getLogger(__name__)

# Type alias for message handler callbacks
MessageHandler = Callable[[AgentMessage], Awaitable[None]]


class NATSClient:
    """
    High-level async wrapper around nats-py with JetStream support.

    Usage::

        client = NATSClient(url="nats://localhost:4222")
        await client.connect()

        # Publish
        await client.publish("agents.observer.anomalies", message)

        # Subscribe (durable consumer)
        await client.subscribe("agents.observer.anomalies", handler, durable="observer")

        await client.close()
    """

    def __init__(
        self,
        url: str = "nats://localhost:4222",
        max_reconnect_attempts: int = 10,
        reconnect_time_wait: float = 2.0,
    ) -> None:
        self.url = url
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_time_wait = reconnect_time_wait

        self._nc: NATSConnection | None = None
        self._js: JetStreamContext | None = None

    # ------------------------------------------------------------------ #
    # Connection management                                                #
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        """Establish connection to NATS and obtain a JetStream context."""
        self._nc = await nats.connect(
            self.url,
            max_reconnect_attempts=self.max_reconnect_attempts,
            reconnect_time_wait=self.reconnect_time_wait,
            error_cb=self._on_error,
            disconnected_cb=self._on_disconnect,
            reconnected_cb=self._on_reconnect,
        )
        self._js = self._nc.jetstream()
        logger.info("Connected to NATS at %s", self.url)

    async def close(self) -> None:
        """Gracefully drain and close the NATS connection."""
        if self._nc and not self._nc.is_closed:
            await self._nc.drain()
            logger.info("NATS connection closed")

    @property
    def is_connected(self) -> bool:
        return self._nc is not None and self._nc.is_connected

    # ------------------------------------------------------------------ #
    # Publish                                                              #
    # ------------------------------------------------------------------ #

    async def publish(
        self,
        subject: str,
        message: AgentMessage,
        *,
        max_retries: int = 3,
    ) -> None:
        """
        Publish an AgentMessage to a JetStream subject.

        Retries with exponential backoff on transient failures.
        """
        self._ensure_connected()
        payload = json.dumps(message.to_dict()).encode()

        for attempt in range(max_retries + 1):
            try:
                await self._js.publish(subject, payload)  # type: ignore[union-attr]
                logger.debug(
                    "Published %s → %s (msg_id=%s)",
                    message.message_type,
                    subject,
                    message.message_id,
                )
                return
            except Exception as exc:
                if attempt == max_retries:
                    logger.error(
                        "Failed to publish to %s after %d attempts: %s",
                        subject,
                        max_retries + 1,
                        exc,
                    )
                    raise
                wait = self.reconnect_time_wait * math.pow(2, attempt)
                logger.warning("Publish attempt %d failed, retrying in %.1fs: %s", attempt + 1, wait, exc)
                await asyncio.sleep(wait)

    # ------------------------------------------------------------------ #
    # Subscribe                                                            #
    # ------------------------------------------------------------------ #

    async def subscribe(
        self,
        subject: str,
        handler: MessageHandler,
        *,
        durable: str | None = None,
        stream: str | None = None,
        deliver_policy: str = "new",
        ack_wait: int = 30,
    ) -> nats.js.api.PushSubscription:
        """
        Subscribe to a JetStream subject with a push consumer.

        Args:
            subject:        NATS subject string.
            handler:        Async callback receiving an AgentMessage.
            durable:        Durable consumer name (enables at-least-once delivery).
            stream:         Explicitly target a stream (auto-detected if None).
            deliver_policy: 'new', 'all', 'last', etc.
            ack_wait:       Seconds before redelivery if not acknowledged.

        Returns:
            The underlying NATS push subscription (call `.unsubscribe()` to stop).
        """
        self._ensure_connected()

        async def _raw_handler(msg: Msg) -> None:
            try:
                data = json.loads(msg.data.decode())
                agent_msg = AgentMessage.from_dict(data)

                # Discard expired messages
                if agent_msg.is_expired():
                    logger.warning("Discarding expired message %s", agent_msg.message_id)
                    await msg.ack()
                    return

                await handler(agent_msg)
                await msg.ack()
            except Exception as exc:
                logger.error("Handler error on subject %s: %s", subject, exc, exc_info=True)
                await msg.nak()  # trigger redelivery

        config = nats.js.api.ConsumerConfig(
            durable_name=durable,
            deliver_policy=getattr(nats.js.api.DeliverPolicy, deliver_policy.upper(), None),
            ack_wait=ack_wait,
            ack_policy=nats.js.api.AckPolicy.EXPLICIT,
            filter_subject=subject,
        )

        sub = await self._js.subscribe(  # type: ignore[union-attr]
            subject,
            cb=_raw_handler,
            config=config,
            stream=stream,
        )
        logger.info("Subscribed to %s (durable=%s)", subject, durable)
        return sub

    # ------------------------------------------------------------------ #
    # Request-reply                                                        #
    # ------------------------------------------------------------------ #

    async def request(
        self,
        subject: str,
        message: AgentMessage,
        timeout: float = 30.0,
    ) -> AgentMessage:
        """
        Publish a message and wait for a single response (request-reply pattern).

        Useful for synchronous-style agent interactions.
        """
        self._ensure_connected()
        payload = json.dumps(message.to_dict()).encode()
        msg = await self._nc.request(subject, payload, timeout=timeout)  # type: ignore[union-attr]
        return AgentMessage.from_dict(json.loads(msg.data.decode()))

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _ensure_connected(self) -> None:
        if not self.is_connected:
            raise RuntimeError("NATSClient is not connected. Call await client.connect() first.")

    # ------------------------------------------------------------------ #
    # Connection event callbacks                                           #
    # ------------------------------------------------------------------ #

    async def _on_error(self, exc: Exception) -> None:
        logger.error("NATS error: %s", exc)

    async def _on_disconnect(self) -> None:
        logger.warning("NATS disconnected")

    async def _on_reconnect(self) -> None:
        logger.info("NATS reconnected")


def build_message(
    *,
    source_agent: str,
    target_agent: str,
    message_type: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
    context: dict[str, Any] | None = None,
    priority: int = 2,
    ttl_seconds: int = 300,
) -> AgentMessage:
    """
    Convenience factory for constructing a properly-formed AgentMessage.

    Example::

        msg = build_message(
            source_agent="observer.metrics",
            target_agent="orchestrator",
            message_type="anomaly_detected",
            payload=anomaly.to_dict(),
            correlation_id=incident_id,
        )
        await nats_client.publish(OBSERVER_ANOMALIES, msg)
    """
    msg = AgentMessage(
        source_agent=source_agent,
        target_agent=target_agent,
        message_type=message_type,
        payload=payload,
        priority=priority,
        ttl_seconds=ttl_seconds,
        context=context or {},
    )
    if correlation_id:
        msg.correlation_id = correlation_id
    return msg
