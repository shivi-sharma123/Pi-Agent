"""
Search Service — FastAPI full-text search over Elasticsearch.

Endpoints:
  GET  /health                        → liveness + ES connectivity
  GET  /search?q=&category=&sort=&page=&size=  → full-text product search
  GET  /search/autocomplete?q=        → typeahead suggestions
"""
from __future__ import annotations

import os
import time
from typing import Optional

from elasticsearch import AsyncElasticsearch, NotFoundError
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ES_INDEX = os.getenv("ELASTICSEARCH_INDEX", "products")
PORT = int(os.getenv("PORT", "8006"))

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

SEARCH_REQUESTS = Counter(
    "search_requests_total",
    "Total search requests",
    ["query_type"],
)
SEARCH_LATENCY = Histogram(
    "search_request_duration_seconds",
    "Search request latency",
    ["query_type"],
)
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Search Service",
    description="Full-text product search backed by Elasticsearch",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy ES client — recreated per request in async context
_es: AsyncElasticsearch | None = None


def get_es() -> AsyncElasticsearch:
    global _es
    if _es is None:
        _es = AsyncElasticsearch(ES_URL, request_timeout=10)
    return _es


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Liveness + ES cluster health check."""
    es_ok = False
    try:
        info = await get_es().cluster.health(timeout="3s")
        es_ok = info.get("status") in ("green", "yellow")
    except Exception:
        pass

    return {
        "status": "healthy" if es_ok else "degraded",
        "service": "search-svc",
        "version": "0.2.0",
        "dependencies": {"elasticsearch": "ok" if es_ok else "down"},
    }


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/search")
async def search(
    q: str = Query(..., description="Search query string"),
    category: Optional[str] = Query(None, description="Filter by category"),
    sort: str = Query("relevance", description="Sort by: relevance|price_asc|price_desc|newest"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """
    Full-text product search.

    Scores by name (boosted x3), description, and tags.
    Supports category filter and multiple sort modes.
    """
    start = time.monotonic()
    SEARCH_REQUESTS.labels(query_type="full_text").inc()

    # --- Build ES query ---
    query: dict = {
        "bool": {
            "must": [
                {
                    "multi_match": {
                        "query": q,
                        "fields": ["name^3", "description", "tags^2", "sku"],
                        "type": "best_fields",
                        "fuzziness": "AUTO",
                    }
                }
            ],
            "filter": [{"term": {"is_active": True}}],
        }
    }
    if category:
        query["bool"]["filter"].append({"term": {"category": category}})

    # --- Sort ---
    sort_clause: list = []
    if sort == "price_asc":
        sort_clause = [{"price": "asc"}]
    elif sort == "price_desc":
        sort_clause = [{"price": "desc"}]
    elif sort == "newest":
        sort_clause = [{"created_at": "desc"}]
    # "relevance" → no sort_clause → ES default score desc

    from_ = (page - 1) * size
    body: dict = {"query": query, "from": from_, "size": size}
    if sort_clause:
        body["sort"] = sort_clause

    # --- Aggregations for category facets ---
    body["aggs"] = {
        "categories": {"terms": {"field": "category", "size": 20}},
        "price_stats": {"stats": {"field": "price"}},
    }

    try:
        resp = await get_es().search(index=ES_INDEX, body=body)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Search unavailable: {exc}")

    elapsed = time.monotonic() - start
    SEARCH_LATENCY.labels(query_type="full_text").observe(elapsed)

    hits = resp["hits"]
    total = hits["total"]["value"]
    results = [
        {**h["_source"], "_score": h["_score"]}
        for h in hits["hits"]
    ]

    # Aggregate buckets
    categories_agg = [
        {"name": b["key"], "count": b["doc_count"]}
        for b in resp.get("aggregations", {}).get("categories", {}).get("buckets", [])
    ]
    price_stats = resp.get("aggregations", {}).get("price_stats", {})

    return {
        "query": q,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, (total + size - 1) // size),
        "took_ms": round(elapsed * 1000, 1),
        "results": results,
        "facets": {
            "categories": categories_agg,
            "price": price_stats,
        },
    }


@app.get("/search/autocomplete")
async def autocomplete(
    q: str = Query(..., min_length=1, description="Partial query for suggestions"),
    size: int = Query(10, ge=1, le=50),
):
    """
    Typeahead autocomplete — prefix match on product name.
    Returns lightweight suggestions (id, name, category, price).
    """
    start = time.monotonic()
    SEARCH_REQUESTS.labels(query_type="autocomplete").inc()

    body = {
        "query": {
            "bool": {
                "must": [
                    {
                        "match_phrase_prefix": {
                            "name": {"query": q, "max_expansions": 20}
                        }
                    }
                ],
                "filter": [{"term": {"is_active": True}}],
            }
        },
        "_source": ["id", "name", "category", "price", "sku"],
        "size": size,
    }

    try:
        resp = await get_es().search(index=ES_INDEX, body=body)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Search unavailable: {exc}")

    elapsed = time.monotonic() - start
    SEARCH_LATENCY.labels(query_type="autocomplete").observe(elapsed)

    suggestions = [h["_source"] for h in resp["hits"]["hits"]]
    return {"query": q, "suggestions": suggestions, "took_ms": round(elapsed * 1000, 1)}
