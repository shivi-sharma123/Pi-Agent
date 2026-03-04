import asyncio
import logging
from typing import Dict, Any

from shared.agents.base import BaseAgent
from shared.messaging.schema import AgentMessage
from shared.db.session import get_session
from shared.db.models import Incident

from agents.diagnoser.src.context_collector import ContextCollector
from agents.diagnoser.src.correlation_engine import CorrelationEngine
from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator

logger = logging.getLogger(__name__)

class RCAEngine(BaseAgent):
    """
    The Diagnoser Agent.
    Listens to anomalies, builds context, correlates into Incidents,
    and generates LLM-powered Root Cause Analyses.
    """
    
    agent_type = "diagnoser.rca"
    
    def __init__(self, nats_url: str):
        super().__init__(nats_url=nats_url)
        self.collector = ContextCollector()
        self.correlator = CorrelationEngine()
        self.hypothesis_gen = HypothesisGenerator()
        
    async def setup(self):
        # Subscribe to anomalies coming from the Observer Pool
        await self.nats.subscribe(
            subject="agents.observer.anomalies",
            cb=self.handle_anomaly,
            queue="diagnoser_pool" # Load balancing among multiple diagnoser instances
        )
        logger.info("RCAEngine setup complete and subscribed to anomalies.")
        
    async def run_loop(self):
        # The agent acts purely on subscriptions, so the loop just sleeps
        while True:
            await asyncio.sleep(60)
            
    async def teardown(self):
        await self.collector.close()
        logger.info("RCAEngine shutting down.")
        
    async def handle_anomaly(self, msg: AgentMessage):
        """
        Main pipeline for processing an anomaly.
        """
        payload = msg.payload
        logger.info(f"Received anomaly from {msg.source_agent} for {payload.get('service')}")
        self._increment_processed(1)
        
        try:
            # 1. Correlate anomaly into an Incident
            incident, created = await self.correlator.correlate(payload)
            logger.info(f"Anomaly mapped to Incident {incident.id}. Created={created}")
            
            # Simple debounce for MVP: If incident was just created or we haven't diagnosed it yet, do the work.
            # In a production system, we might wait for 1-2 minutes of anomalies to gather before diagnosing.
            if created or incident.status == "detecting":
                logger.info(f"Starting diagnosis for Incident {incident.id}")
                
                # 2. Gather Context
                context = await self.collector.collect_context(payload)
                
                # 3. Generate RCA Hypothesis
                diagnosis, confidence = await self.hypothesis_gen.generate_hypothesis(incident.id, context)
                
                logger.info(
                    f"Generated RCA. Root Cause: {diagnosis.get('root_cause_service')} "
                    f"({diagnosis.get('root_cause_category')}), Confidence: {confidence}%"
                )
                
                # 4. Save to Database
                async with get_session() as session:
                    db_incident = await session.get(Incident, incident.id)
                    if db_incident:
                        db_incident.diagnosis = diagnosis
                        db_incident.diagnosis_confidence = confidence
                        db_incident.root_cause_category = diagnosis.get("root_cause_category")
                        db_incident.root_cause_service = diagnosis.get("root_cause_service")
                        db_incident.status = "diagnosing" # Transitioning states
                        await session.commit()
                
                # 5. Publish Result
                await self.publish_diagnosis(incident.id, diagnosis, confidence)
                
        except Exception as e:
            logger.exception(f"Error processing anomaly in RCAEngine: {e}")
            self._increment_errors(1)
            
    async def publish_diagnosis(self, incident_id: str, diagnosis: Dict[str, Any], confidence: int):
        payload = {
            "incident_id": incident_id,
            "diagnosis": diagnosis,
            "confidence": confidence
        }
        
        msg = AgentMessage(
            source_agent=self.agent_id,
            message_type="incident_diagnosed",
            payload=payload
        )
        
        await self.nats.publish("agents.diagnoser.results", msg.to_dict())
        logger.info(f"Published diagnosis for Incident {incident_id}")
