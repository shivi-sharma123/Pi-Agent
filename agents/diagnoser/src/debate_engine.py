"""
DebateEngine
============
Resolves ambiguous Root Cause Analyses by generating and judging multiple
competing hypotheses.

When the primary HypothesisGenerator returns confidence < CONFIDENCE_THRESHOLD,
the DebateEngine:
  1. Generates two alternative hypotheses (different LLM prompts/temperatures).
  2. Scores each hypothesis on a structured rubric:
       a) Evidence coverage        (0-40 pts)  — How well does it explain all symptoms?
       b) Temporal correlation     (0-30 pts)  — Does the timeline fit?
       c) Service-graph plausibility (0-30 pts) — Does it match the dependency graph?
  3. Returns the hypothesis with the highest rubric score.

Used by: agents/diagnoser/src/rca_engine.py (when confidence < threshold)

Usage::

    debate = DebateEngine(hypothesis_gen)
    winner, score = await debate.resolve(incident_id, context, candidates=[hyp1, hyp2])
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 60
"""RCAs with confidence below this trigger the debate engine."""

# Rubric weights
_EVIDENCE_WEIGHT = 40
_TEMPORAL_WEIGHT = 30
_GRAPH_WEIGHT = 30


class DebateEngine:
    """
    Multi-hypothesis resolver for low-confidence RCA situations.
    """

    def __init__(self, hypothesis_generator) -> None:
        """
        Args:
            hypothesis_generator: Instance of HypothesisGenerator (from diagnoser).
        """
        self._gen = hypothesis_generator

    async def resolve(
        self,
        incident_id: str,
        context: dict[str, Any],
        initial_hypothesis: dict[str, Any],
        initial_confidence: int,
    ) -> tuple[dict[str, Any], int]:
        """
        Run the debate for a low-confidence hypothesis.

        Returns:
            Tuple of (winning_hypothesis, confidence_score)
        """
        logger.info(
            "[Debate] Confidence %d%% < threshold %d%% for incident %s — generating alternatives",
            initial_confidence, CONFIDENCE_THRESHOLD, incident_id,
        )

        # Generate two alternative hypotheses with higher temperature / different framing
        candidates: list[tuple[dict, int]] = [(initial_hypothesis, initial_confidence)]

        for attempt, temperature in enumerate([0.9, 1.1], start=1):
            try:
                alt_hyp, alt_conf = await self._gen.generate_hypothesis(
                    incident_id,
                    context,
                    temperature=temperature,
                )
                logger.info(
                    "[Debate] Alternative %d: category=%s confidence=%d%%",
                    attempt,
                    alt_hyp.get("root_cause_category", "?"),
                    alt_conf,
                )
                candidates.append((alt_hyp, alt_conf))
            except Exception:
                logger.exception("[Debate] Failed to generate alternative hypothesis %d", attempt)

        # Score + rank all candidates
        scored = [
            (hyp, conf, self._score(hyp, context))
            for hyp, conf in candidates
        ]
        scored.sort(key=lambda x: (x[2], x[1]), reverse=True)

        winner_hyp, winner_conf, winner_rubric = scored[0]
        logger.info(
            "[Debate] Winner: category=%s confidence=%d%% rubric=%.1f/100",
            winner_hyp.get("root_cause_category", "?"),
            winner_conf,
            winner_rubric,
        )

        # Boost confidence slightly if the debate selected the same category as initial
        if winner_hyp.get("root_cause_category") == initial_hypothesis.get("root_cause_category"):
            winner_conf = min(winner_conf + 10, 100)

        return winner_hyp, winner_conf

    # ─── Rubric scoring ───────────────────────────────────────────────────────

    def _score(self, hypothesis: dict[str, Any], context: dict[str, Any]) -> float:
        """
        Score a hypothesis on the structured rubric (0-100).
        """
        evidence_score = self._score_evidence_coverage(hypothesis, context)
        temporal_score = self._score_temporal_fit(hypothesis, context)
        graph_score = self._score_graph_plausibility(hypothesis, context)
        return evidence_score + temporal_score + graph_score

    def _score_evidence_coverage(self, hypothesis: dict, context: dict) -> float:
        """
        Does the hypothesis explain the observed symptoms and anomalies?
        Score: 0 - 40
        """
        anomalies = context.get("anomalies", [])
        if not anomalies:
            return 20.0  # Partial credit when no anomalies to compare against

        explained = hypothesis.get("explained_anomalies", [])
        if not explained:
            # Fall back: keyword overlap between reasoning and anomaly descriptions
            reasoning = hypothesis.get("reasoning", "").lower()
            explained_count = sum(
                1 for a in anomalies
                if any(kw in reasoning for kw in str(a).lower().split())
            )
        else:
            explained_count = len(explained)

        coverage = min(explained_count / max(len(anomalies), 1), 1.0)
        return round(coverage * _EVIDENCE_WEIGHT, 1)

    def _score_temporal_fit(self, hypothesis: dict, context: dict) -> float:
        """
        Does the hypothesised root cause service have anomalies that *precede*
        the cascade to other services?
        Score: 0 - 30
        """
        root_service = hypothesis.get("root_cause_service", "")
        recent_events = context.get("recent_events", [])

        if not recent_events or not root_service:
            return 15.0  # Partial credit

        # Find the first event mentioning the root service
        root_events = [e for e in recent_events if root_service in str(e)]
        other_events = [e for e in recent_events if root_service not in str(e)]

        if not root_events or not other_events:
            return 15.0

        first_root = min(e.get("timestamp", 0) for e in root_events if isinstance(e, dict))
        first_other = min(e.get("timestamp", 0) for e in other_events if isinstance(e, dict))

        if first_root <= first_other:
            return _TEMPORAL_WEIGHT  # Root-cause came first — perfect temporal fit
        elif first_root - first_other < 60:
            return _TEMPORAL_WEIGHT * 0.7  # Root came shortly after — plausible
        else:
            return _TEMPORAL_WEIGHT * 0.2  # Root came much later — poor fit

    def _score_graph_plausibility(self, hypothesis: dict, context: dict) -> float:
        """
        Is the hypothesised root service a known dependency of the affected services?
        Score: 0 - 30
        """
        root_service = hypothesis.get("root_cause_service", "")
        affected = context.get("affected_services", [])
        dependency_graph = context.get("dependency_graph", {})

        if not dependency_graph or not affected:
            return 15.0  # Partial credit

        # Check if root_service is a dependency of any affected service
        for svc in affected:
            deps = dependency_graph.get(svc, [])
            if root_service in deps:
                return _GRAPH_WEIGHT  # Direct dependency match

        # Indirect check: is it in any dep-of-dep?
        for svc in affected:
            for dep in dependency_graph.get(svc, []):
                if root_service in dependency_graph.get(dep, []):
                    return _GRAPH_WEIGHT * 0.6

        return 0.0
