import json
import logging
import os
from typing import Dict, Any, Tuple
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class HypothesisGenerator:
    """
    Uses an LLM (via OpenAI API) to evaluate incident context and generate
    a structured Root Cause Analysis hypothesis.
    """
    
    def __init__(self, api_key: str = None):
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY", "")
        self.api_key = api_key
        # We only instantiate the client if we have a key
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        
    async def generate_hypothesis(self, incident_id: str, context: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        Takes the aggregated context and returns a tuple:
        (diagnosis_dict, confidence_score_int)
        
        If no API key is provided, returns a dummy response for local testing.
        """
        if not self.client:
            logger.warning("No OPENAI_API_KEY provided. Using dummy RCA generator.")
            return self._generate_dummy_hypothesis(context)
            
        system_prompt = """
        You are an elite SRE Root Cause Analysis (RCA) engine. You will be provided with context about an active production incident.
        The context includes the anomalies detected, recent logs, and basic metrics for the affected services.
        
        Analyze the context to determine the likely root cause.
        Return ONLY valid JSON with the following structure:
        {
            "root_cause_service": "name of service",
            "root_cause_category": "database|network|application_error|resource_exhaustion|unknown",
            "confidence": 85, // integer 0-100 indicating how confident you are
            "diagnosis_summary": "Short explanation of why this conclusion was reached",
            "recommended_runbook": "restart_service|scale_up|circuit_break|human_escalation"
        }
        Do not include markdown blocks or any other text.
        """
        
        user_prompt = f"Incident ID: {incident_id}\nContext:\n{json.dumps(context, indent=2)}"
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2, # Low temp for analytical consistency
                response_format={ "type": "json_object" } # Ensure JSON response
            )
            
            result_text = response.choices[0].message.content
            diagnosis = json.loads(result_text)
            
            confidence = diagnosis.get("confidence", 50)
            return diagnosis, confidence
            
        except Exception as e:
            logger.exception("LLM generation failed for incident", extra={"incident_id": incident_id})
            return {"error": str(e), "diagnosis_summary": "LLM Failure"}, 0
            
    def _generate_dummy_hypothesis(self, context: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """Fallback when no LLM is available."""
        # A simple heuristic based on the anomaly
        anomaly = context.get("anomaly", {})
        service = anomaly.get("service", "unknown")
        metric = anomaly.get("metric", "unknown")
        
        category = "unknown"
        runbook = "human_escalation"
        
        if metric in ["cpu_usage", "memory_usage"]:
            category = "resource_exhaustion"
            runbook = "scale_up"
        elif metric == "error_rate":
            category = "application_error"
            runbook = "restart_service"
        elif metric == "http_health":
            category = "network"
            runbook = "restart_service"
            
        diagnosis = {
            "root_cause_service": service,
            "root_cause_category": category,
            "confidence": 60,
            "diagnosis_summary": f"Dummy inference based on {metric} anomaly on {service}",
            "recommended_runbook": runbook
        }
        
        return diagnosis, 60
