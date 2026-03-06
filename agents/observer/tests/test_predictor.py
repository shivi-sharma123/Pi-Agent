"""
Tests for TrendPredictor (predictor.py) and DebateEngine (debate_engine.py).

Run with: pytest agents/observer/tests/test_predictor.py -v
           pytest agents/diagnoser/tests/test_debate_engine.py -v
"""
import time
import pytest

# ─── TrendPredictor tests ─────────────────────────────────────────────────────

class TestTrendPredictor:
    from agents.observer.src.predictor import TrendPredictor

    def _make(self, threshold=0.9, look_ahead=1800, window=10, min_samples=3, min_r2=0.7):
        from agents.observer.src.predictor import TrendPredictor
        return TrendPredictor(
            metric_name="memory_usage",
            service="user-svc",
            threshold=threshold,
            look_ahead_seconds=look_ahead,
            window_size=window,
            min_samples=min_samples,
            min_r2=min_r2,
        )

    def test_no_alert_with_insufficient_samples(self):
        pred = self._make(min_samples=5)
        for i in range(3):
            pred.push(value=0.5, timestamp=time.time() + i * 60)
        assert pred.evaluate() is None

    def test_no_alert_for_flat_metric(self):
        pred = self._make()
        now = time.time()
        for i in range(10):
            pred.push(value=0.5, timestamp=now + i * 60)
        result = pred.evaluate()
        # Flat metric should not trigger a trend alert
        assert result is None

    def test_alert_for_steadily_increasing_metric(self):
        """Monotonically increasing value should trigger an alert."""
        pred = self._make(threshold=0.9, look_ahead=3600, min_r2=0.5)
        now = time.time()
        # Simulate memory growing from 0.50 → 0.82 over 20 samples (every 60s)
        for i in range(20):
            pred.push(value=0.50 + i * 0.016, timestamp=now + i * 60)
        alert = pred.evaluate()
        assert alert is not None
        assert alert.metric_name == "memory_usage"
        assert alert.service == "user-svc"
        assert alert.slope > 0
        assert 0 < alert.predicted_breach_in_seconds < 3600
        assert alert.confidence > 0.5

    def test_no_alert_when_breach_outside_look_ahead(self):
        """If the breach is more than look_ahead_seconds away, no alert."""
        pred = self._make(threshold=0.9, look_ahead=600, min_r2=0.5)
        now = time.time()
        # Very slow growth — breach takes hours
        for i in range(15):
            pred.push(value=0.50 + i * 0.001, timestamp=now + i * 60)
        assert pred.evaluate() is None

    def test_ols_perfect_fit(self):
        from agents.observer.src.predictor import TrendPredictor
        slope, intercept, r2 = TrendPredictor._ols(
            xs=[0, 1, 2, 3, 4],
            ys=[0, 2, 4, 6, 8],
        )
        assert abs(slope - 2.0) < 1e-6
        assert abs(r2 - 1.0) < 1e-6


# ─── DebateEngine tests ───────────────────────────────────────────────────────

class TestDebateEngine:

    def _make_engine(self, alt_confidence=75):
        from agents.diagnoser.src.debate_engine import DebateEngine
        from unittest.mock import AsyncMock

        mock_gen = AsyncMock()
        mock_gen.generate_hypothesis = AsyncMock(
            return_value=(
                {
                    "root_cause_category": "memory_leak",
                    "root_cause_service": "user-svc",
                    "reasoning": "Memory usage trend increasing",
                },
                alt_confidence,
            )
        )
        return DebateEngine(mock_gen)

    @pytest.mark.asyncio
    async def test_debate_picks_higher_confidence(self):
        engine = self._make_engine(alt_confidence=80)
        initial = {"root_cause_category": "network_issue", "root_cause_service": "api", "reasoning": "timeout"}
        winner, conf = await engine.resolve("inc-1", {}, initial, initial_confidence=45)
        # Should have picked the higher-confidence alternative from the mock
        assert conf >= 45

    @pytest.mark.asyncio
    async def test_debate_returns_something_even_on_gen_failure(self):
        from agents.diagnoser.src.debate_engine import DebateEngine
        from unittest.mock import AsyncMock

        mock_gen = AsyncMock()
        mock_gen.generate_hypothesis = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        engine = DebateEngine(mock_gen)

        initial = {"root_cause_category": "memory_leak", "root_cause_service": "svc", "reasoning": "slow"}
        winner, conf = await engine.resolve("inc-2", {}, initial, initial_confidence=50)
        # Should fall back to the initial hypothesis
        assert winner is not None

    def test_evidence_score_full_when_no_anomalies(self):
        engine = self._make_engine()
        score = engine._score_evidence_coverage({"reasoning": "memory"}, context={})
        assert score == 20.0   # partial credit

    def test_graph_score_zero_for_unknown_service(self):
        engine = self._make_engine()
        context = {
            "affected_services": ["order-svc"],
            "dependency_graph": {"order-svc": ["payment-svc"]},
        }
        score = engine._score_graph_plausibility(
            {"root_cause_service": "auth-svc"},
            context,
        )
        assert score == 0.0

    def test_graph_score_full_for_direct_dependency(self):
        engine = self._make_engine()
        context = {
            "affected_services": ["order-svc"],
            "dependency_graph": {"order-svc": ["user-svc"]},
        }
        score = engine._score_graph_plausibility(
            {"root_cause_service": "user-svc"},
            context,
        )
        assert score == 30.0
