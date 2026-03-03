"""
NATS JetStream subject constants.

All agents publish and subscribe using these constants — never raw strings.
The hierarchy follows: <namespace>.<agent>.<action>

See LLD §2.2 for the full subject map.
"""

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
ORCHESTRATOR_COMMANDS = "agents.orchestrator.commands"
"""Orchestrator broadcasts commands to the agent pool."""

# ---------------------------------------------------------------------------
# Observer
# ---------------------------------------------------------------------------
OBSERVER_ANOMALIES = "agents.observer.anomalies"
"""Observers publish detected anomalies here."""

# ---------------------------------------------------------------------------
# Diagnoser
# ---------------------------------------------------------------------------
DIAGNOSER_REQUESTS = "agents.diagnoser.requests"
"""Orchestrator posts diagnosis requests here."""

DIAGNOSER_RESULTS = "agents.diagnoser.results"
"""Diagnoser publishes completed diagnosis results here."""

# ---------------------------------------------------------------------------
# Remediator
# ---------------------------------------------------------------------------
REMEDIATOR_PROPOSALS = "agents.remediator.proposals"
"""Remediator posts proposed remediation actions here."""

REMEDIATOR_EXECUTIONS = "agents.remediator.executions"
"""Remediator publishes execution confirmations / results here."""

# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------
SAFETY_REVIEWS = "agents.safety.reviews"
"""Safety agent receives review requests here."""

SAFETY_DECISIONS = "agents.safety.decisions"
"""Safety agent publishes approve / reject decisions here."""

# ---------------------------------------------------------------------------
# Learning
# ---------------------------------------------------------------------------
LEARNING_FEEDBACK = "agents.learning.feedback"
"""Post-incident feedback for the learning agent."""

# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------
AGENT_HEARTBEAT = "agents.heartbeat"
"""All agents publish heartbeats here for health monitoring."""

INCIDENTS_LIFECYCLE = "incidents.lifecycle"
"""Incident state transitions (detecting → diagnosing → resolved …)."""

# ---------------------------------------------------------------------------
# Human-in-the-loop
# ---------------------------------------------------------------------------
HUMAN_APPROVALS = "human.approvals"
"""Safety agent posts approval requests here (consumed by dashboard)."""

HUMAN_APPROVALS_RESPONSES = "human.approvals.responses"
"""Dashboard posts human decisions (approve / reject) here."""

# ---------------------------------------------------------------------------
# Business domain events (published by microservices, consumed by agents)
# ---------------------------------------------------------------------------
ORDERS_CREATED = "orders.created"
PAYMENTS_COMPLETED = "payments.completed"
PAYMENTS_FAILED = "payments.failed"
INVENTORY_LOW = "inventory.low"

# ---------------------------------------------------------------------------
# Stream definitions (used by init_nats.py script)
# ---------------------------------------------------------------------------
STREAMS: dict[str, dict] = {
    "AGENTS": {
        "subjects": [
            ORCHESTRATOR_COMMANDS,
            OBSERVER_ANOMALIES,
            DIAGNOSER_REQUESTS,
            DIAGNOSER_RESULTS,
            REMEDIATOR_PROPOSALS,
            REMEDIATOR_EXECUTIONS,
            SAFETY_REVIEWS,
            SAFETY_DECISIONS,
            LEARNING_FEEDBACK,
            AGENT_HEARTBEAT,
        ],
        "max_age": 86_400,      # 24 hours retention
        "max_msgs": 1_000_000,
        "storage": "file",
    },
    "INCIDENTS": {
        "subjects": [INCIDENTS_LIFECYCLE],
        "max_age": 7 * 86_400,  # 7 days retention
        "max_msgs": 100_000,
        "storage": "file",
    },
    "HUMAN": {
        "subjects": [HUMAN_APPROVALS, HUMAN_APPROVALS_RESPONSES],
        "max_age": 3_600,       # 1 hour (approvals expire quickly)
        "max_msgs": 10_000,
        "storage": "memory",
    },
    "BUSINESS": {
        "subjects": [ORDERS_CREATED, PAYMENTS_COMPLETED, PAYMENTS_FAILED, INVENTORY_LOW],
        "max_age": 3 * 86_400,
        "max_msgs": 500_000,
        "storage": "file",
    },
}
