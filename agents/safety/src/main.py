import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone

# Adjust Python path to allow importing from shared
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from shared.agents.base import BaseAgent
from shared.messaging.schema import AgentMessage
from shared.messaging.subjects import (
    SAFETY_REVIEWS as SUBJECT_SAFETY_REVIEWS,
    SAFETY_DECISIONS as SUBJECT_SAFETY_DECISIONS
)

from policy_engine import PolicyEngine
from blast_radius import BlastRadiusCalculator
from rate_limiter import RateLimiter
from approval_gateway import HumanApprovalGateway

logger = logging.getLogger(__name__)

class SafetyAgent(BaseAgent):
    """
    Subscribes to `agents.safety.reviews`, evaluates proposed remediation
    actions against rules/blast_radius/rate_limits, and outputs a decision.
    """
    
    agent_type = "agents.safety"

    def __init__(self, nats_url: str = None):
        super().__init__()
        self.policy_engine = PolicyEngine()
        self.blast_calc = BlastRadiusCalculator()
        self.rate_limiter = RateLimiter()
        self.approval_gateway = HumanApprovalGateway()
        
    async def setup(self):
        await self._subscribe()
        logger.info("Safety Agent setup complete and listening for action proposals")

    async def run_loop(self):
        while self._running:
            await asyncio.sleep(1.0)
            
    async def teardown(self):
        logger.info("Tearing down Safety Agent")

    async def _subscribe(self):
        try:
            self.sub = await self.nats.subscribe(
                SUBJECT_SAFETY_REVIEWS,
                durable="safety-agent-consumer",
                handler=self._handle_review_request
            )
        except Exception as e:
            logger.error(f"Failed to subscribe to JetStream: {e}")

    async def _handle_review_request(self, request: AgentMessage):
        try:
            logger.info(f"Received safety review request for incident_id={request.correlation_id}")
            
            # The payload contains the diagnosis and the proposed action
            diagnosis = request.payload.get("diagnosis", {})
            action = request.payload.get("action", {})
            
            decision = await self._evaluate_action(
                request.correlation_id, diagnosis, action
            )
            
            # Publish decision
            await self._publish_decision(request, decision)
            
        except Exception as e:
            logger.exception(f"Error handling safety review request: {e}")
            raise

    async def _evaluate_action(self, incident_id: str, diagnosis: dict, action: dict) -> dict:
        """
        Runs the action through the security gamut.
        """
        # 1. Blast Radius
        blast_info = self.blast_calc.calculate(action)
        logger.debug(f"Blast radius computed: {blast_info['risk_level']}")
        
        # 2. Rate Limiting
        rate_ok, rate_reason = self.rate_limiter.check(action)
        if not rate_ok:
            logger.warning(f"Action rate-limited: {rate_reason}")
            return {
                "status": "rejected",
                "reason": rate_reason,
            }
            
        # 3. Policy Engine
        # We inject the computed blast risk into the action struct for the engine to see
        action_with_context = dict(action)
        # If the manual risk tag says medium/high OR the blast radius says medium/high
        if action.get("risk") in ["medium", "high"] or blast_info["risk_level"] in ["medium", "high"]:
            action_with_context["risk"] = "high"
            
        policy_ok, policy_reason = self.policy_engine.evaluate(action_with_context)
        
        if not policy_ok:
            logger.info(f"Action requires human approval: {policy_reason}")
            # Format and return a pending request instead of a rejection
            return self.approval_gateway.format_approval_request(
                incident_id, diagnosis, action, policy_reason, blast_info
            )
            
        # 4. Success -> Mark as Approved
        self.rate_limiter.record(action)
        logger.info(f"Action auto-approved: {action.get('type')} on {action.get('params',{}).get('target')}")
        
        return {
            "status": "approved",
            "reason": "Passed all safety checks",
            "blast_radius": blast_info,
            "action": action
        }

    async def _publish_decision(self, request: AgentMessage, decision: dict):
        response_msg = AgentMessage(
            message_id=request.message_id, # Link back to request
            correlation_id=request.correlation_id,
            source_agent="agents.safety",
            target_agent=request.source_agent,
            message_type="safety_decision",
            priority=request.priority,
            timestamp=datetime.now(timezone.utc),
            payload=decision,
            context=request.context,
            ttl_seconds=300,
            retry_count=0,
            trace_id=request.trace_id
        )
        
        await self.nats.publish(
            SUBJECT_SAFETY_DECISIONS,
            response_msg
        )
        logger.info(f"Published decision '{decision['status']}' to {SUBJECT_SAFETY_DECISIONS}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = SafetyAgent()
    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        pass
