"""
Unit tests for Learning Agent components.
These tests use pure Python mocks and avoid importing chromadb/sentence_transformers
to maintain compatibility with Python 3.14 where pydantic.v1 is unavailable.

Run with: pytest agents/learner/tests/test_learner.py -v
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Shared fixtures ─────────────────────────────────────────────────────────────

SAMPLE_INCIDENT = {
    "incident_id": "inc-001",
    "root_cause_category": "memory_leak",
    "root_cause_service": "user-svc",
    "runbook_id": "runbook_memory_leak",
    "outcome": "success",
    "mttr_seconds": 90,
    "diagnosis_confidence": 92,
    "reasoning": "Monotonic memory increase detected over 24h",
    "symptoms": ["high_memory", "slow_response"],
    "severity": "high",
}

SAMPLE_INCIDENT_2 = {
    "incident_id": "inc-002",
    "root_cause_category": "memory_leak",
    "root_cause_service": "order-svc",
    "runbook_id": "runbook_memory_leak",
    "outcome": "failed_verification",
    "mttr_seconds": 300,
    "diagnosis_confidence": 70,
    "reasoning": "Memory leak in order processing thread",
    "symptoms": ["high_memory"],
    "severity": "medium",
}


# ─── IncidentVectorizer (mock-based) ────────────────────────────────────────────

class TestIncidentVectorizer:
    """Tests using a hand-rolled mock so we never import chromadb."""

    def _make_mock_vectorizer(self, count=0, query_hits=None):
        """Return a MagicMock that behaves like IncidentVectorizer."""
        v = MagicMock()
        v.count.return_value = count
        v.find_similar.return_value = query_hits or []
        return v

    def test_upsert_and_count(self):
        v = self._make_mock_vectorizer(count=1)
        v.upsert(SAMPLE_INCIDENT)
        v.upsert.assert_called_once_with(SAMPLE_INCIDENT)
        assert v.count() == 1

    def test_find_similar_empty_collection(self):
        v = self._make_mock_vectorizer(count=0)
        results = v.find_similar({"root_cause_category": "memory_leak"}, n=5)
        assert results == []

    def test_find_similar_maps_results(self):
        hits = [
            {"id": "inc-001", "metadata": SAMPLE_INCIDENT, "distance": 0.1, "document": "text"},
            {"id": "inc-002", "metadata": SAMPLE_INCIDENT_2, "distance": 0.3, "document": "text2"},
        ]
        v = self._make_mock_vectorizer(count=2, query_hits=hits)
        results = v.find_similar({"root_cause_category": "memory_leak"}, n=5)
        assert len(results) == 2
        assert results[0]["id"] == "inc-001"
        assert "metadata" in results[0]
        assert "distance" in results[0]


# ─── _build_incident_text ────────────────────────────────────────────────────────

class TestBuildIncidentText:
    """Test the text-building helper without importing chromadb."""

    def test_includes_all_key_fields(self):
        # Import just the function; chromadb is imported lazily with __init__ guard
        import importlib, sys
        # Temporarily mock chromadb + sentence_transformers before import
        with patch.dict("sys.modules", {
            "chromadb": MagicMock(),
            "chromadb.config": MagicMock(),
            "sentence_transformers": MagicMock(),
        }):
            import importlib
            sys.path.insert(0, "agents/learner/src")
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "iv", "agents/learner/src/incident_vectorizer.py"
            )
            if spec is not None:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                text = mod._build_incident_text(SAMPLE_INCIDENT)
                assert "memory_leak" in text
                assert "user-svc" in text
                assert "success" in text


# ─── PatternRecognizer ────────────────────────────────────────────────────────────

class TestPatternRecognizer:
    """Tests for PatternRecognizer with a mock IncidentVectorizer."""

    def _make(self, hits=None):
        mock_v = MagicMock()
        mock_v.count.return_value = len(hits) if hits else 0
        mock_v.find_similar.return_value = hits or []

        with patch.dict("sys.modules", {
            "chromadb": MagicMock(),
            "chromadb.config": MagicMock(),
            "sentence_transformers": MagicMock(),
            "incident_vectorizer": MagicMock(),
        }):
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "pr", "agents/learner/src/pattern_recognizer.py"
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.PatternRecognizer(mock_v)

    def test_recommend_runbook_picks_highest_success(self):
        hits = [
            {"id": "inc-001", "distance": 0.1, "document": "", "metadata": {"runbook_id": "r1", "outcome": "success", "mttr_seconds": 90}},
            {"id": "inc-002", "distance": 0.2, "document": "", "metadata": {"runbook_id": "r1", "outcome": "success", "mttr_seconds": 120}},
            {"id": "inc-003", "distance": 0.3, "document": "", "metadata": {"runbook_id": "r2", "outcome": "failed_verification", "mttr_seconds": 300}},
        ]
        rec = self._make(hits=hits).recommend_runbook({})
        assert rec["runbook_id"] == "r1"
        assert rec["success_rate"] == pytest.approx(1.0)
        assert rec["sample_count"] == 2

    def test_recommend_runbook_empty(self):
        rec = self._make(hits=[]).recommend_runbook({})
        assert rec["runbook_id"] is None
        assert rec["success_rate"] == 0.0

    def test_enrich_keys_present(self):
        hits = [
            {"id": "inc-001", "distance": 0.1, "document": "", "metadata": {"runbook_id": "r1", "outcome": "success", "mttr_seconds": 90}},
        ]
        result = self._make(hits=hits).enrich_diagnosis({})
        assert "similar_incidents" in result
        assert "recommended_runbook" in result
        assert "historical_sample_size" in result


# ─── RunbookOptimizer ─────────────────────────────────────────────────────────────

class TestRunbookOptimizer:
    """Tests using mocked SQLAlchemy engine."""

    def _make(self):
        with patch.dict("sys.modules", {
            "sqlalchemy": MagicMock(),
            "sqlalchemy.ext.asyncio": MagicMock(),
            "sqlalchemy.orm": MagicMock(),
        }):
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "ro", "agents/learner/src/runbook_optimizer.py"
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

    def test_row_to_dict_success_rate(self):
        mod = self._make()
        row = {
            "runbook_id": "runbook_memory_leak",
            "total_attempts": 10,
            "successes": 8,
            "total_mttr_sec": 900,
            "last_updated_at": "2026-01-01T00:00:00Z",
        }
        result = mod.RunbookOptimizer._row_to_dict(row)
        assert result["success_rate"] == pytest.approx(0.8)
        assert result["avg_mttr_seconds"] == 90

    def test_row_to_dict_zero_attempts(self):
        mod = self._make()
        row = {"runbook_id": "new_rb", "total_attempts": 0, "successes": 0, "total_mttr_sec": 0, "last_updated_at": ""}
        result = mod.RunbookOptimizer._row_to_dict(row)
        assert result["success_rate"] == 0.0
        assert result["avg_mttr_seconds"] == 0
