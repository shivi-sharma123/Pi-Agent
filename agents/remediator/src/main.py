import os
import sys
import json
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

# Adjust Python path to allow importing from shared and current dir
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from shared.agents.base import BaseAgent
from shared.messaging.schema import AgentMessage
from shared.messaging.subjects import (
    DIAGNOSER_RESULTS as SUBJECT_DIAGNOSER_RESULTS,
    SAFETY_REVIEWS as SUBJECT_SAFETY_REVIEWS,
    SAFETY_DECISIONS as SUBJECT_SAFETY_DECISIONS,
    REMEDIATOR_PROPOSALS as SUBJECT_REMEDIATOR_PROPOSALS,
    REMEDIATOR_EXECUTIONS as SUBJECT_REMEDIATOR_EXECUTIONS
)

from runbook_engine import RunbookEngine
from action_executor import ActionExecutor
from verification_engine import VerificationEngine
from rollback_manager import RollbackManager

logger = logging.getLogger(__name__)

class RemediatorAgent(BaseAgent):
    """
    Subscribes to `agents.diagnoser.results`.
    Given a diagnosis, matches a runbook, proposes actions to the Safety Agent,
    waits for approval, executes, and verifies.
    """
    
    agent_type = "agents.remediator"

    def __init__(self, nats_url: str = None):
        super().__init__()
        self.runbook_engine = RunbookEngine()
        self.action_executor = ActionExecutor()
        self.verification_engine = VerificationEngine()
        self.rollback_manager = RollbackManager(self.action_executor)
        
        # In-flight remediation state
        self.active_remediations: Dict[str, Dict[str, Any]] = {}
        
    async def setup(self):
        await self._subscribe()
        logger.info("Remediator Agent setup complete")

    async def run_loop(self):
        # The base agent handles the heartbeat and signal handling.
        # We just need to keep the event loop alive here since the NATS subscriptions are active callbacks.
        while self._running:
            await asyncio.sleep(1.0)
            
    async def teardown(self):
        logger.info("Tearing down Remediator Agent")

    async def _subscribe(self):
        # Listen for new diagnoses from the RCA Engine
        try:
            self.sub_diag = await self.nats.subscribe(
                SUBJECT_DIAGNOSER_RESULTS,
                durable="remediator-diagnoser-consumer",
                handler=self._handle_diagnosis
            )
            
            # Listen for safety decisions (Approve/Reject) from the Safety Agent
            self.sub_safety = await self.nats.subscribe(
                SUBJECT_SAFETY_DECISIONS,
                durable="remediator-safety-consumer",
                handler=self._handle_safety_decision
            )
        except Exception as e:
            logger.error(f"Failed to subscribe to JetStream: {e}")

    async def _handle_diagnosis(self, request: AgentMessage):
        try:
            diagnosis = request.payload
            correlation_id = request.correlation_id
            
            logger.info(f"Received diagnosis for {correlation_id}. category: {diagnosis.get('root_cause', {}).get('category')}")
            
            # Step 1: Match runbook
            runbook = self.runbook_engine.find_match(diagnosis)
            
            if not runbook:
                logger.info(f"No runbook found for diagnosis. Dropping {correlation_id}.")
                return
                
            # For MVP, we only take the first action from the runbook
            actions = runbook.get("actions", [])
            if not actions:
                logger.warning(f"Runbook '{runbook['id']}' has no actions.")
                return
                
            raw_action = actions[0]
            # Interpolate context into action params
            rendered_action = self.runbook_engine.render_action(raw_action, diagnosis)
            
            # Store in state
            self.active_remediations[correlation_id] = {
                "diagnosis": diagnosis,
                "runbook": runbook,
                "action": rendered_action
            }
            
            # Step 2: Pitch proposal to Safety Agent
            await self._propose_action(correlation_id, request, diagnosis, rendered_action)
            
        except Exception as e:
            logger.exception("Error handling diagnosis")
            raise

    async def _propose_action(self, correlation_id: str, request: AgentMessage, diagnosis: dict, action: dict):
        proposal_msg = AgentMessage(
            message_id=str(uuid.uuid4()),
            correlation_id=correlation_id,
            source_agent="agents.remediator",
            target_agent="agents.safety",
            message_type="safety_review_request",
            priority=request.priority,
            timestamp=datetime.now(timezone.utc),
            payload={
                "diagnosis": diagnosis,
                "action": action
            },
            context=request.context,
            ttl_seconds=300,
            retry_count=0,
            trace_id=request.trace_id
        )
        
        await self.nats.publish(
            SUBJECT_SAFETY_REVIEWS,
            proposal_msg
        )
        logger.info(f"Proposed action '{action.get('type')}' to Safety Agent for {correlation_id}")

    async def _handle_safety_decision(self, response: AgentMessage):
        """
        Receives Approved/Rejected verdicts from the SafetyAgent.
        """
        try:
            cid = response.correlation_id
            state = self.active_remediations.get(cid)
            
            if not state:
                logger.warning(f"Received safety decision for unknown/expired incident {cid}")
                return
                
            decision_payload = response.payload
            status = decision_payload.get("status")
            
            if status == "rejected":
                logger.warning(f"Action rejected by Safety Agent: {decision_payload.get('reason')}")
                # Optional: Handle rejection (notify human, drop)
                del self.active_remediations[cid]
                return
                
            if status == "pending_human_approval":
                logger.info(f"Action requires human approval: {decision_payload.get('reason')}. Waiting...")
                return
                
            if status == "approved":
                logger.info(f"Action approved! Executing: {state['action']['type']}")
                
                # Step 3: Execute Action
                exec_ok, exec_reason = self.action_executor.execute(state["action"])
                
                if exec_ok:
                    # Step 4: Verify Fix
                    vf_ok, vf_reason = await self.verification_engine.verify(state["runbook"], state["diagnosis"])
                    
                    if vf_ok:
                        logger.info(f"Remediation verified successful for {cid}: {vf_reason}")
                        await self._publish_completion(response, state, "success", vf_reason)
                    else:
                        logger.error(f"Verification failed: {vf_reason}. Triggering Rollback.")
                        self.rollback_manager.rollback(state["action"])
                        await self._publish_completion(response, state, "failed_verification", vf_reason)
                else:
                    logger.error(f"Action Execution failed: {exec_reason}")
                    await self._publish_completion(response, state, "failed_execution", exec_reason)
                    
                del self.active_remediations[cid]
                return

        except Exception as e:
            logger.exception("Error handling safety decision")
            raise

    async def _publish_completion(self, request: AgentMessage, state: dict, result: str, details: str):
        """
        Notifys Orchestrator that the remediation loop has completed (success/fail).
        """
        response_msg = AgentMessage(
            message_id=str(uuid.uuid4()),
            correlation_id=request.correlation_id,
            source_agent="agents.remediator",
            target_agent="agents.orchestrator",
            message_type="remediation_execution",
            priority=request.priority,
            timestamp=datetime.now(timezone.utc),
            payload={
                "action_type": state["action"].get("type"),
                "status": result,
                "details": details
            },
            context=request.context,
            ttl_seconds=300,
            retry_count=0,
            trace_id=request.trace_id
        )
        
        await self.nats.publish(
            SUBJECT_REMEDIATOR_EXECUTIONS,
            response_msg
        )
        logger.info(f"Published completion '{result}' for {request.correlation_id}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = RemediatorAgent()
    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        pass
