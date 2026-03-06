"""
LearnerAgent
============
Subscribes to ``agents.learning.feedback`` (published by the Remediator after
every remediation cycle) and:

  1. Stores the resolved incident as a vector in ChromaDB via IncidentVectorizer.
  2. Records per-runbook performance in PostgreSQL via RunbookOptimizer.

The agent also exposes a simple query endpoint via NATS request-reply so that
the Diagnoser can ask "have we seen this before?" before generating an RCA.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from shared.agents.base import BaseAgent
from shared.messaging.schema import AgentMessage
from shared.messaging.subjects import LEARNING_FEEDBACK

from incident_vectorizer import IncidentVectorizer
from pattern_recognizer import PatternRecognizer
from runbook_optimizer import RunbookOptimizer

logger = logging.getLogger(__name__)

# NATS subject that the Diagnoser can use to query for similar incidents
LEARNING_QUERY = "agents.learning.query"


class LearnerAgent(BaseAgent):
    """
    Subscribes to post-incident feedback and builds persistent memory.
    """

    agent_type = "agents.learner"

    def __init__(self) -> None:
        super().__init__()
        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://sre_user:sre_pass@localhost:5432/agents_db",
        )
        chroma_path = os.environ.get("CHROMA_PERSIST_PATH", "./chromadb")

        self._vectorizer = IncidentVectorizer(persist_path=chroma_path)
        self._recognizer = PatternRecognizer(self._vectorizer)
        self._optimizer = RunbookOptimizer(db_url=db_url)

    # ─── BaseAgent lifecycle ────────────────────────────────────────────────────

    async def setup(self) -> None:
        await self._optimizer.initialise()

        # Subscribe to feedback events from the Remediator
        await self.nats.subscribe(
            subject=LEARNING_FEEDBACK,
            handler=self._handle_feedback,
            durable="learner-feedback-consumer",
        )

        # Subscribe to query requests from the Diagnoser (request-reply).
        # Uses raw NATS subscription (not JetStream) so we can access msg.reply
        # for the request-reply pattern used by NATSClient.request().
        await self.nats._nc.subscribe(LEARNING_QUERY, cb=self._handle_query)

        logger.info("LearnerAgent setup complete — listening on %s and %s", LEARNING_FEEDBACK, LEARNING_QUERY)

    async def run_loop(self) -> None:
        while self._running:
            await asyncio.sleep(5)

    async def teardown(self) -> None:
        logger.info("LearnerAgent shutting down.")

    # ─── Handlers ──────────────────────────────────────────────────────────────

    async def _handle_feedback(self, msg: AgentMessage) -> None:
        """
        Persist a resolved incident from the Remediator.

        Expected payload keys:
          incident_id, root_cause_category, root_cause_service, runbook_id,
          outcome, mttr_seconds, diagnosis_confidence, reasoning, symptoms
        """
        payload = msg.payload
        incident_id = payload.get("incident_id", msg.correlation_id)
        runbook_id = payload.get("runbook_id", "unknown")
        outcome = payload.get("outcome", "unknown")
        mttr = int(payload.get("mttr_seconds", 0))

        logger.info(
            "Received feedback for incident=%s runbook=%s outcome=%s mttr=%ds",
            incident_id, runbook_id, outcome, mttr,
        )

        # 1. Vectorize + store in ChromaDB
        try:
            self._vectorizer.upsert({"incident_id": incident_id, **payload})
        except Exception:
            logger.exception("Failed to upsert incident %s into ChromaDB", incident_id)

        # 2. Record in PostgreSQL optimizer
        try:
            await self._optimizer.record(runbook_id=runbook_id, outcome=outcome, mttr_seconds=mttr)
        except Exception:
            logger.exception("Failed to record runbook stats for %s", runbook_id)

    async def _handle_query(self, raw_msg) -> None:
        """
        Request-reply handler for the Diagnoser to enrich its context with
        historical incident memory before generating an RCA.

        This handler receives a raw NATS message (not an AgentMessage) because
        NATSClient.request() uses the core NATS request-reply pattern with an
        ephemeral inbox.  We must reply to ``raw_msg.reply`` so the caller's
        ``await nats.request(...)`` actually receives the response.

        Expected payload: same structure as an incident dict (category, service…)
        Response payload: result from PatternRecognizer.enrich_diagnosis()
        """
        import json
        try:
            data = json.loads(raw_msg.data.decode())
            agent_msg = AgentMessage.from_dict(data)

            enrichment = self._recognizer.enrich_diagnosis(agent_msg.payload)
            response = AgentMessage(
                source_agent=self.agent_type,
                target_agent=agent_msg.source_agent,
                message_type="learning_query_response",
                correlation_id=agent_msg.correlation_id,
                payload=enrichment,
            )
            # Reply to the caller's ephemeral inbox so NATSClient.request() receives it
            if raw_msg.reply:
                await self.nats._nc.publish(raw_msg.reply, json.dumps(response.to_dict()).encode())
            logger.info("Enriched diagnosis for incident %s with %d similar incidents",
                        agent_msg.correlation_id, len(enrichment.get("similar_incidents", [])))
        except Exception:
            logger.exception("Failed to handle learning query")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = LearnerAgent()
    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        pass
