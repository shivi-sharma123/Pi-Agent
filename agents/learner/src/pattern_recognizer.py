"""
PatternRecognizer
=================
Uses IncidentVectorizer to perform RAG-style lookups over historical incidents.

It answers two questions:
  1. *Have we seen this kind of incident before?*
     → Returns top-k similar past incidents ranked by cosine similarity.
  2. *Which runbook had the best success rate for this category?*
     → Aggregates metadata across the top-k hits and returns a ranked list.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

try:
    from .incident_vectorizer import IncidentVectorizer
except ImportError:
    from incident_vectorizer import IncidentVectorizer  # type: ignore

logger = logging.getLogger(__name__)

# Similarity score threshold: distances above this are considered "not similar"
# (ChromaDB cosine distance → 0.0 = identical, 2.0 = opposite)
SIMILARITY_THRESHOLD = 0.6


class PatternRecognizer:
    """
    High-level RAG interface over the ChromaDB incident store.

    Usage::

        recognizer = PatternRecognizer(vectorizer)
        context = recognizer.enrich_diagnosis(current_incident)
        # context contains `similar_incidents` and `recommended_runbook`
    """

    def __init__(self, vectorizer: IncidentVectorizer) -> None:
        self._vectorizer = vectorizer

    # ───────────────────────────────────────────────────────────────────────────
    # Public API
    # ───────────────────────────────────────────────────────────────────────────

    def find_similar(
        self,
        incident: dict[str, Any],
        n: int = 5,
        only_successful: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Find the most similar past incidents.

        Args:
            incident:         The current (unresolved) incident parameters.
            n:                Max number of results.
            only_successful:  If True, restrict to incidents with outcome=success.
        """
        where = {"outcome": "success"} if only_successful else None
        hits = self._vectorizer.find_similar(incident, n=n, where=where)
        # Filter by similarity threshold
        return [h for h in hits if h["distance"] <= SIMILARITY_THRESHOLD]

    def recommend_runbook(
        self,
        incident: dict[str, Any],
        n_search: int = 10,
    ) -> dict[str, Any]:
        """
        Recommend the runbook with the highest success rate for similar incidents.

        Returns a dict with keys: ``runbook_id``, ``success_rate``,
        ``sample_count``, ``avg_mttr_seconds``.
        """
        hits = self.find_similar(incident, n=n_search)
        if not hits:
            return {"runbook_id": None, "success_rate": 0.0, "sample_count": 0, "avg_mttr_seconds": 0}

        # Aggregate per-runbook statistics
        stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"success": 0, "total": 0, "mttr_total": 0}
        )
        for hit in hits:
            meta = hit["metadata"]
            rb_id = meta.get("runbook_id", "unknown")
            stats[rb_id]["total"] += 1
            if meta.get("outcome") == "success":
                stats[rb_id]["success"] += 1
            stats[rb_id]["mttr_total"] += meta.get("mttr_seconds", 0)

        # Pick the runbook with the best success rate (ties: prefer lower MTTR)
        best_rb = max(
            stats.items(),
            key=lambda kv: (kv[1]["success"] / max(kv[1]["total"], 1), -kv[1]["mttr_total"]),
        )
        rb_id, rb_stats = best_rb
        total = rb_stats["total"]
        success_rate = rb_stats["success"] / total if total > 0 else 0.0
        avg_mttr = rb_stats["mttr_total"] / total if total > 0 else 0

        logger.info(
            "Recommended runbook '%s' (success_rate=%.0f%%, n=%d, avg_mttr=%ds)",
            rb_id, success_rate * 100, total, avg_mttr,
        )
        return {
            "runbook_id": rb_id,
            "success_rate": round(success_rate, 3),
            "sample_count": total,
            "avg_mttr_seconds": int(avg_mttr),
        }

    def enrich_diagnosis(self, incident: dict[str, Any]) -> dict[str, Any]:
        """
        Combine similar incident retrieval and runbook recommendation into one
        enrichment payload that can be attached to the diagnosis context.
        """
        similar = self.find_similar(incident)
        recommendation = self.recommend_runbook(incident)

        return {
            "similar_incidents": [
                {
                    "id": h["id"],
                    "distance": round(h["distance"], 4),
                    **h["metadata"],
                }
                for h in similar
            ],
            "recommended_runbook": recommendation,
            "historical_sample_size": self._vectorizer.count(),
        }
