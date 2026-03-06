"""
HypothesisGenerator
===================
Uses Google Gemini (primary) or OpenAI (fallback) to generate a structured
Root Cause Analysis hypothesis from incident context.

Environment variables:
  GEMINI_APY_KEY    — Google Gemini API key  (note: env var has typo "APY" preserved for compatibility)
  OPENAI_API_KEY    — OpenAI API key (fallback)
  LLM_MODEL        — Override model name (defaults depend on which backend is active)
"""

import json
import logging
import os
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

# System prompt shared by both backends
_SYSTEM_PROMPT = """
You are an elite SRE Root Cause Analysis (RCA) engine. You will be provided
with context about an active production incident, including detected anomalies,
recent logs, and basic metrics for the affected services.

Analyse the context to determine the likely root cause.
Return ONLY valid JSON with the following structure (no markdown blocks):
{
    "root_cause_service": "name of service",
    "root_cause_category": "database|network|application_error|resource_exhaustion|unknown",
    "confidence": 85,
    "diagnosis_summary": "Short explanation of why this conclusion was reached",
    "recommended_runbook": "restart_service|scale_up|circuit_break|human_escalation",
    "reasoning": "Detailed chain-of-thought reasoning",
    "explained_anomalies": ["anomaly1", "anomaly2"]
}
""".strip()


class HypothesisGenerator:
    """
    Generates LLM-powered RCA hypotheses.

    Primary backend: Google Gemini (GEMINI_APY_KEY)
    Fallback backend: OpenAI (OPENAI_API_KEY)
    No-key fallback: deterministic heuristic
    """

    def __init__(self, api_key: str | None = None, temperature: float = 0.2) -> None:
        self._temperature = temperature
        self._gemini_client = None
        self._openai_client = None
        self._backend: str = "dummy"

        # Try Gemini first (user's primary API key)
        gemini_key = api_key or os.getenv("GEMINI_APY_KEY") or os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                import google.generativeai as genai  # type: ignore
                genai.configure(api_key=gemini_key)
                model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
                self._gemini_client = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json",
                        temperature=temperature,
                    ),
                    system_instruction=_SYSTEM_PROMPT,
                )
                self._backend = "gemini"
                logger.info("HypothesisGenerator: using Gemini backend (%s)", model_name)
            except ImportError:
                logger.warning("google-generativeai not installed; skipping Gemini backend.")
            except Exception as e:
                logger.warning("Failed to initialise Gemini client: %s", e)

        # Try OpenAI as fallback
        if self._backend == "dummy":
            from openai import AsyncOpenAI  # type: ignore
            openai_key = os.getenv("OPENAI_API_KEY", "")
            if openai_key:
                self._openai_client = AsyncOpenAI(api_key=openai_key)
                self._openai_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
                self._backend = "openai"
                logger.info("HypothesisGenerator: using OpenAI backend (%s)", self._openai_model)
            else:
                logger.warning("No LLM API key set. Using heuristic dummy generator.")

    # ─── Public API ───────────────────────────────────────────────────────────

    async def generate_hypothesis(
        self,
        incident_id: str,
        context: Dict[str, Any],
        temperature: float | None = None,
    ) -> Tuple[Dict[str, Any], int]:
        """
        Generate an RCA hypothesis from incident context.

        Args:
            incident_id: Unique incident identifier (for logging).
            context:     Dict of anomalies, logs, metrics, events.
            temperature: Override generation temperature (for debate engine).

        Returns:
            Tuple of (diagnosis_dict, confidence_int).
        """
        if self._backend == "gemini":
            return await self._gemini_generate(incident_id, context, temperature)
        elif self._backend == "openai":
            return await self._openai_generate(incident_id, context, temperature)
        else:
            return self._generate_dummy_hypothesis(context)

    # ─── Gemini backend ───────────────────────────────────────────────────────

    async def _gemini_generate(
        self,
        incident_id: str,
        context: Dict[str, Any],
        temperature: float | None,
    ) -> Tuple[Dict[str, Any], int]:
        import asyncio
        import google.generativeai as genai  # type: ignore

        user_prompt = f"Incident ID: {incident_id}\nContext:\n{json.dumps(context, indent=2)}"

        # If temperature override requested, create a fresh config
        config = None
        if temperature is not None and temperature != self._temperature:
            config = genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=temperature,
            )

        try:
            # Gemini SDK is synchronous — run in thread pool to keep async-safe
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._gemini_client.generate_content(
                    user_prompt,
                    generation_config=config,
                ),
            )
            diagnosis = json.loads(response.text)
            confidence = int(diagnosis.get("confidence", 50))
            logger.info(
                "Gemini RCA for %s: category=%s confidence=%d%%",
                incident_id,
                diagnosis.get("root_cause_category", "?"),
                confidence,
            )
            return diagnosis, confidence
        except Exception as e:
            logger.exception("Gemini generation failed for incident %s: %s", incident_id, e)
            return {"error": str(e), "diagnosis_summary": "Gemini LLM failure"}, 0

    # ─── OpenAI backend ───────────────────────────────────────────────────────

    async def _openai_generate(
        self,
        incident_id: str,
        context: Dict[str, Any],
        temperature: float | None,
    ) -> Tuple[Dict[str, Any], int]:
        user_prompt = f"Incident ID: {incident_id}\nContext:\n{json.dumps(context, indent=2)}"
        temp = temperature if temperature is not None else self._temperature
        try:
            response = await self._openai_client.chat.completions.create(
                model=self._openai_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temp,
                response_format={"type": "json_object"},
            )
            diagnosis = json.loads(response.choices[0].message.content)
            confidence = int(diagnosis.get("confidence", 50))
            return diagnosis, confidence
        except Exception as e:
            logger.exception("OpenAI generation failed for incident %s", incident_id)
            return {"error": str(e), "diagnosis_summary": "OpenAI LLM failure"}, 0

    # ─── Heuristic fallback ───────────────────────────────────────────────────

    def _generate_dummy_hypothesis(self, context: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """Deterministic fallback when no LLM key is configured."""
        anomaly = context.get("anomaly", {})
        service = anomaly.get("service", "unknown")
        metric = anomaly.get("metric", "unknown")

        category_map = {
            "cpu_usage": ("resource_exhaustion", "scale_up"),
            "memory_usage": ("resource_exhaustion", "scale_up"),
            "error_rate": ("application_error", "restart_service"),
            "http_health": ("network", "restart_service"),
            "latency_p99": ("application_error", "circuit_break"),
        }
        category, runbook = category_map.get(metric, ("unknown", "human_escalation"))

        diagnosis = {
            "root_cause_service": service,
            "root_cause_category": category,
            "confidence": 60,
            "diagnosis_summary": f"Heuristic inference from {metric} anomaly on {service}",
            "recommended_runbook": runbook,
            "reasoning": f"Metric '{metric}' exceeded threshold on service '{service}'.",
            "explained_anomalies": [metric],
        }
        return diagnosis, 60
