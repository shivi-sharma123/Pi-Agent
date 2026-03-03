"""
Shared package public API.

Importing from ``sre_shared`` (the installed package) gives access to
the most commonly used classes and helpers directly.
"""

from shared.agents.base import BaseAgent
from shared.config.settings import settings
from shared.logging.logger import configure_logging, get_logger
from shared.messaging.nats_client import NATSClient, build_message
from shared.messaging.schema import AgentMessage
from shared.messaging.subjects import (
    AGENT_HEARTBEAT,
    DIAGNOSER_REQUESTS,
    DIAGNOSER_RESULTS,
    HUMAN_APPROVALS,
    INCIDENTS_LIFECYCLE,
    OBSERVER_ANOMALIES,
    REMEDIATOR_EXECUTIONS,
    REMEDIATOR_PROPOSALS,
    SAFETY_DECISIONS,
    SAFETY_REVIEWS,
)

__all__ = [
    # Base
    "BaseAgent",
    "AgentMessage",
    "NATSClient",
    "build_message",
    # Config
    "settings",
    # Logging
    "get_logger",
    "configure_logging",
    # Subjects
    "OBSERVER_ANOMALIES",
    "DIAGNOSER_REQUESTS",
    "DIAGNOSER_RESULTS",
    "REMEDIATOR_PROPOSALS",
    "REMEDIATOR_EXECUTIONS",
    "SAFETY_REVIEWS",
    "SAFETY_DECISIONS",
    "INCIDENTS_LIFECYCLE",
    "HUMAN_APPROVALS",
    "AGENT_HEARTBEAT",
]
