"""
IncidentVectorizer
==================
Embeds resolved incidents into a ChromaDB collection so that similar past
incidents can be retrieved via vector similarity at diagnosis time.

Each document stored in ChromaDB represents one resolved incident and
contains:
  - A concatenated text string suitable for embedding
  - Structured metadata for filtering (category, outcome, runbook used, etc.)
"""

from __future__ import annotations

import json
import logging
from typing import Any

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ─── Constants ─────────────────────────────────────────────────────────────────
COLLECTION_NAME = "incidents"
MODEL_NAME = "all-MiniLM-L6-v2"   # ~80 MB — fast and accurate enough for ops use
CHROMA_PERSIST_PATH = "./chromadb"


def _build_incident_text(incident: dict[str, Any]) -> str:
    """Turn a structured incident dict into a single natural-language string."""
    parts = [
        f"Category: {incident.get('root_cause_category', 'unknown')}",
        f"Service: {incident.get('root_cause_service', 'unknown')}",
        f"Severity: {incident.get('severity', 'unknown')}",
        f"Runbook: {incident.get('runbook_id', 'none')}",
        f"Outcome: {incident.get('outcome', 'unknown')}",
        f"Reasoning: {incident.get('reasoning', '')}",
        f"Symptoms: {', '.join(incident.get('symptoms', []))}",
    ]
    return " | ".join(p for p in parts if p)


class IncidentVectorizer:
    """
    Manages a ChromaDB collection of past incidents.

    Usage::

        vectorizer = IncidentVectorizer()
        vectorizer.upsert(incident_dict)
        results = vectorizer.find_similar(query_incident, n=5)
    """

    def __init__(self, persist_path: str = CHROMA_PERSIST_PATH) -> None:
        self._model = SentenceTransformer(MODEL_NAME)
        self._client = chromadb.PersistentClient(
            path=persist_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "IncidentVectorizer ready. Collection '%s' has %d documents.",
            COLLECTION_NAME,
            self._collection.count(),
        )

    # ───────────────────────────────────────────────────────────────────────────
    # Public API
    # ───────────────────────────────────────────────────────────────────────────

    def upsert(self, incident: dict[str, Any]) -> None:
        """
        Add or update an incident in the vector store.

        Args:
            incident: Dict containing at minimum ``incident_id`` and
                      ``root_cause_category``.  All extra keys are stored as
                      metadata.
        """
        incident_id = str(incident["incident_id"])
        text = _build_incident_text(incident)
        embedding = self._model.encode(text).tolist()

        metadata = {
            "root_cause_category": str(incident.get("root_cause_category", "")),
            "root_cause_service": str(incident.get("root_cause_service", "")),
            "runbook_id": str(incident.get("runbook_id", "")),
            "outcome": str(incident.get("outcome", "")),
            "mttr_seconds": int(incident.get("mttr_seconds", 0)),
            "confidence": int(incident.get("diagnosis_confidence", 0)),
        }

        self._collection.upsert(
            ids=[incident_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata],
        )
        logger.info("Upserted incident %s into ChromaDB.", incident_id)

    def find_similar(
        self,
        query_incident: dict[str, Any],
        n: int = 5,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return the top-n most similar past incidents.

        Args:
            query_incident: Incident dict to use as the search query.
            n:              Max number of results to return.
            where:          Optional ChromaDB metadata filter dict, e.g.
                            ``{"outcome": "success"}``.

        Returns:
            List of dicts with keys ``id``, ``metadata``, ``distance``,
            ``document``.
        """
        if self._collection.count() == 0:
            logger.debug("ChromaDB collection is empty — no similar incidents found.")
            return []

        text = _build_incident_text(query_incident)
        embedding = self._model.encode(text).tolist()

        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": min(n, self._collection.count()),
            "include": ["metadatas", "distances", "documents"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        hits = []
        for idx in range(len(results["ids"][0])):
            hits.append({
                "id": results["ids"][0][idx],
                "metadata": results["metadatas"][0][idx],
                "distance": results["distances"][0][idx],
                "document": results["documents"][0][idx],
            })
        return hits

    def count(self) -> int:
        """Return total number of incidents stored."""
        return self._collection.count()
