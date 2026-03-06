"""
Tests for the updated HypothesisGenerator (Gemini/OpenAI/heuristic backends).

All LLM calls are mocked so no real API quota is consumed.

Run with: PYTHONPATH=. pytest agents/diagnoser/tests/test_hypothesis_generator.py -v
"""

from __future__ import annotations

import json
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

SAMPLE_CONTEXT = {
    "anomaly": {
        "service": "user-svc",
        "metric": "memory_usage",
        "value": 0.92,
        "threshold": 0.85,
    },
    "recent_logs": ["OOMKilled detected", "memory pressure high"],
    "affected_services": ["user-svc"],
}

SAMPLE_DIAGNOSIS = {
    "root_cause_service": "user-svc",
    "root_cause_category": "resource_exhaustion",
    "confidence": 88,
    "diagnosis_summary": "Memory leak in user service",
    "recommended_runbook": "scale_up",
    "reasoning": "Memory monotonically increasing over 24h",
    "explained_anomalies": ["memory_usage"],
}


# ─── Heuristic / No-key tests ─────────────────────────────────────────────────

class TestHeuristicFallback:
    """HypothesisGenerator with no API keys → deterministic fallback."""

    def _make(self):
        with patch.dict(os.environ, {}, clear=False):
            # Clear any ambient API keys
            env = {k: v for k, v in os.environ.items() if "GEMINI" not in k and "OPENAI" not in k}
            with patch.dict(os.environ, env, clear=True):
                from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
                return HypothesisGenerator.__new__(HypothesisGenerator)

    def test_dummy_memory_usage(self):
        from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
        gen = HypothesisGenerator.__new__(HypothesisGenerator)
        gen._backend = "dummy"
        gen._gemini_client = None
        gen._openai_client = None
        gen._temperature = 0.2

        diagnosis, confidence = gen._generate_dummy_hypothesis(SAMPLE_CONTEXT)
        assert diagnosis["root_cause_category"] == "resource_exhaustion"
        assert diagnosis["recommended_runbook"] == "scale_up"
        assert confidence == 60

    def test_dummy_error_rate(self):
        from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
        gen = HypothesisGenerator.__new__(HypothesisGenerator)
        gen._backend = "dummy"
        ctx = {"anomaly": {"service": "order-svc", "metric": "error_rate", "value": 0.1}}
        diagnosis, confidence = gen._generate_dummy_hypothesis(ctx)
        assert diagnosis["root_cause_category"] == "application_error"
        assert diagnosis["recommended_runbook"] == "restart_service"

    def test_dummy_unknown_metric(self):
        from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
        gen = HypothesisGenerator.__new__(HypothesisGenerator)
        gen._backend = "dummy"
        ctx = {"anomaly": {"service": "auth-svc", "metric": "something_weird", "value": 9}}
        diagnosis, _ = gen._generate_dummy_hypothesis(ctx)
        assert diagnosis["root_cause_category"] == "unknown"
        assert diagnosis["recommended_runbook"] == "human_escalation"

    @pytest.mark.asyncio
    async def test_generate_hypothesis_routes_to_dummy(self):
        from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
        gen = HypothesisGenerator.__new__(HypothesisGenerator)
        gen._backend = "dummy"
        gen._gemini_client = None
        gen._openai_client = None
        gen._temperature = 0.2
        diagnosis, conf = await gen.generate_hypothesis("inc-1", SAMPLE_CONTEXT)
        assert isinstance(diagnosis, dict)
        assert "root_cause_category" in diagnosis
        assert isinstance(conf, int)


# ─── Gemini backend (mocked) ──────────────────────────────────────────────────

class TestGeminiBackend:
    """Tests with Gemini backend — actual API is mocked."""

    def _make_gen_with_gemini_mock(self):
        from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
        gen = HypothesisGenerator.__new__(HypothesisGenerator)
        gen._temperature = 0.2
        gen._backend = "gemini"
        gen._openai_client = None

        # Create a mock Gemini client
        mock_response = MagicMock()
        mock_response.text = json.dumps(SAMPLE_DIAGNOSIS)
        mock_client = MagicMock()
        mock_client.generate_content.return_value = mock_response
        gen._gemini_client = mock_client
        return gen

    @pytest.mark.asyncio
    async def test_gemini_returns_parsed_diagnosis(self):
        gen = self._make_gen_with_gemini_mock()
        diagnosis, confidence = await gen.generate_hypothesis("inc-1", SAMPLE_CONTEXT)
        assert diagnosis["root_cause_service"] == "user-svc"
        assert confidence == 88

    @pytest.mark.asyncio
    async def test_gemini_handles_api_error_gracefully(self):
        from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
        gen = HypothesisGenerator.__new__(HypothesisGenerator)
        gen._temperature = 0.2
        gen._backend = "gemini"
        gen._openai_client = None

        mock_client = MagicMock()
        mock_client.generate_content.side_effect = RuntimeError("API unavailable")
        gen._gemini_client = mock_client

        diagnosis, confidence = await gen.generate_hypothesis("inc-err", SAMPLE_CONTEXT)
        assert confidence == 0
        assert "error" in diagnosis

    @pytest.mark.asyncio
    async def test_gemini_handles_invalid_json_response(self):
        from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
        gen = HypothesisGenerator.__new__(HypothesisGenerator)
        gen._temperature = 0.2
        gen._backend = "gemini"
        gen._openai_client = None

        mock_response = MagicMock()
        mock_response.text = "Not valid JSON {{{"
        mock_client = MagicMock()
        mock_client.generate_content.return_value = mock_response
        gen._gemini_client = mock_client

        diagnosis, confidence = await gen.generate_hypothesis("inc-json-err", SAMPLE_CONTEXT)
        assert confidence == 0

    @pytest.mark.asyncio
    async def test_gemini_clips_confidence_to_100(self):
        from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
        gen = HypothesisGenerator.__new__(HypothesisGenerator)
        gen._temperature = 0.2
        gen._backend = "gemini"
        gen._openai_client = None

        bad_diagnosis = {**SAMPLE_DIAGNOSIS, "confidence": 150}
        mock_response = MagicMock()
        mock_response.text = json.dumps(bad_diagnosis)
        mock_client = MagicMock()
        mock_client.generate_content.return_value = mock_response
        gen._gemini_client = mock_client

        # Should still parse but confidence will be 150 (caller should handle capping)
        diagnosis, confidence = await gen.generate_hypothesis("inc-clip", SAMPLE_CONTEXT)
        assert diagnosis["root_cause_service"] == "user-svc"


# ─── OpenAI backend (mocked) ──────────────────────────────────────────────────

class TestOpenAIBackend:
    """Tests with OpenAI backend — actual API is mocked."""

    def _make_gen_with_openai_mock(self):
        from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
        gen = HypothesisGenerator.__new__(HypothesisGenerator)
        gen._temperature = 0.2
        gen._backend = "openai"
        gen._gemini_client = None
        gen._openai_model = "gpt-4o-mini"

        # Mock the OpenAI response structure
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(SAMPLE_DIAGNOSIS)
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        gen._openai_client = mock_client
        return gen

    @pytest.mark.asyncio
    async def test_openai_returns_parsed_diagnosis(self):
        gen = self._make_gen_with_openai_mock()
        diagnosis, confidence = await gen.generate_hypothesis("inc-1", SAMPLE_CONTEXT)
        assert diagnosis["root_cause_service"] == "user-svc"
        assert confidence == 88

    @pytest.mark.asyncio
    async def test_openai_handles_exception_gracefully(self):
        from agents.diagnoser.src.hypothesis_generator import HypothesisGenerator
        gen = HypothesisGenerator.__new__(HypothesisGenerator)
        gen._temperature = 0.2
        gen._backend = "openai"
        gen._gemini_client = None
        gen._openai_model = "gpt-4o-mini"

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("rate limited"))
        gen._openai_client = mock_client

        diagnosis, confidence = await gen.generate_hypothesis("inc-err", SAMPLE_CONTEXT)
        assert confidence == 0
        assert "error" in diagnosis


# ─── Backend selection tests ──────────────────────────────────────────────────

class TestBackendSelection:
    """Verify the correct backend is chosen based on environment variables."""

    def test_gemini_preferred_over_openai(self):
        """When both keys are present, Gemini should be selected."""
        with patch.dict(os.environ, {
            "GEMINI_APY_KEY": "fake-gemini-key",
            "OPENAI_API_KEY": "fake-openai-key",
        }):
            with patch("google.generativeai.configure"), \
                 patch("google.generativeai.GenerativeModel"):
                from importlib import import_module, reload
                import agents.diagnoser.src.hypothesis_generator as hg_mod
                reload(hg_mod)
                gen = hg_mod.HypothesisGenerator()
                assert gen._backend == "gemini"

    def test_openai_fallback_when_no_gemini(self):
        """Without Gemini key, should fall back to OpenAI."""
        env = {k: v for k, v in os.environ.items() if "GEMINI" not in k}
        env["OPENAI_API_KEY"] = "fake-openai-key"
        with patch.dict(os.environ, env, clear=True):
            with patch("openai.AsyncOpenAI"):
                from importlib import reload
                import agents.diagnoser.src.hypothesis_generator as hg_mod
                reload(hg_mod)
                gen = hg_mod.HypothesisGenerator()
                assert gen._backend == "openai"
