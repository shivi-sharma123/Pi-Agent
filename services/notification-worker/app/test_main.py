"""
Tests for Notification Worker handlers.
"""
from unittest.mock import patch
from app.main import handle_order_created, handle_payment_failed, api
from fastapi.testclient import TestClient

client = TestClient(api)

def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert "orders.created" in resp.json()["subscriptions"]

@patch("app.main.send_email")
@patch("app.main.send_push")
def test_handle_order_created(mock_push, mock_email):
    handle_order_created({
        "id": "ord-123",
        "user_id": "999",
        "total": 50.0
    })

    mock_email.assert_called_once_with(
        to="user_999@example.com",
        subject="Order #ord-123 Confirmed",
        body="Your order for $50.00 has been placed successfully."
    )
    mock_push.assert_called_once()

@patch("app.main.send_email")
@patch("app.main.send_push")
def test_handle_payment_failed(mock_push, mock_email):
    handle_payment_failed({
        "order_id": "ord-123",
        "reason": "insufficient_funds"
    })

    mock_email.assert_called_once_with(
        to="customer@example.com",
        subject="Payment Failed",
        body="Payment for order #ord-123 failed: insufficient_funds. Please try again."
    )
    mock_push.assert_called_once()
