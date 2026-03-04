"""
Tests for Search Service.
"""
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@patch("app.main.get_es")
def test_health_ok(mock_get_es):
    mock_es = AsyncMock()
    mock_es.cluster.health.return_value = {"status": "green"}
    mock_get_es.return_value = mock_es

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


@patch("app.main.get_es")
def test_health_degraded(mock_get_es):
    mock_es = AsyncMock()
    mock_es.cluster.health.side_effect = Exception("Down")
    mock_get_es.return_value = mock_es

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"


@patch("app.main.get_es")
def test_search(mock_get_es):
    mock_es = AsyncMock()
    mock_es.search.return_value = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_source": {"id": "1", "name": "Laptop", "price": 1000},
                    "_score": 1.5
                }
            ]
        },
        "aggregations": {
            "categories": {"buckets": [{"key": "Electronics", "doc_count": 1}]},
            "price_stats": {"min": 1000, "max": 1000}
        }
    }
    mock_get_es.return_value = mock_es

    resp = client.get("/search?q=laptop")
    assert resp.status_code == 200
    data = resp.json()

    assert data["query"] == "laptop"
    assert data["total"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["name"] == "Laptop"
    assert data["facets"]["categories"][0]["name"] == "Electronics"

    # Verify query
    query_body = mock_es.search.call_args[1]["body"]
    assert "laptop" in query_body["query"]["bool"]["must"][0]["multi_match"]["query"]


@patch("app.main.get_es")
def test_autocomplete(mock_get_es):
    mock_es = AsyncMock()
    mock_es.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_source": {"id": "1", "name": "Lap", "price": 100}
                }
            ]
        }
    }
    mock_get_es.return_value = mock_es

    resp = client.get("/search/autocomplete?q=lap")
    assert resp.status_code == 200
    data = resp.json()

    assert data["query"] == "lap"
    assert len(data["suggestions"]) == 1
    assert data["suggestions"][0]["name"] == "Lap"
