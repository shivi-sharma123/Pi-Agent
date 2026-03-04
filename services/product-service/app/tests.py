"""
Tests for Product Service.
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase
from rest_framework.test import APIClient
from app.models import Product, Category


class ProductServiceTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create a category
        self.cat = Category.objects.create(
            name="Electronics",
            slug="electronics",
            description="Gadgets"
        )

    @patch("app.urls.get_es")
    def test_health_endpoint(self, mock_get_es):
        mock_es = MagicMock()
        mock_es.cluster.health.return_value = {"status": "green"}
        mock_get_es.return_value = mock_es

        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "healthy")

    @patch("django.core.handlers.base.log_response")
    @patch("app.urls.get_es")
    def test_health_degraded(self, mock_get_es, mock_log_response):
        mock_es = MagicMock()
        mock_es.cluster.health.side_effect = Exception("Down")
        mock_get_es.return_value = mock_es

        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["status"], "degraded")

    @patch("app.models.get_es")
    def test_create_product_indexes_es(self, mock_get_es):
        mock_es = MagicMock()
        mock_get_es.return_value = mock_es

        data = {
            "sku": "TEST-123",
            "name": "Test Laptop",
            "description": "A very fast laptop",
            "category": str(self.cat.id),
            "price": "999.99",
            "stock": 10
        }
        resp = self.client.post("/products/", data, format="json")
        self.assertEqual(resp.status_code, 201)

        product_id = resp.json()["id"]

        # Was it indexed?
        mock_es.index.assert_called_once()
        call_args = mock_es.index.call_args[1]
        self.assertEqual(call_args["id"], product_id)
        self.assertEqual(call_args["document"]["name"], "Test Laptop")

    @patch("app.models.get_es")
    def test_delete_product_removes_from_es(self, mock_get_es):
        mock_es = MagicMock()
        mock_get_es.return_value = mock_es

        prod = Product.objects.create(
            sku="DEL-1", name="Delete Me", price="10.0"
        )

        resp = self.client.delete(f"/products/{prod.id}/")
        self.assertEqual(resp.status_code, 204)

        # Was it removed from ES?
        mock_es.delete.assert_called_once()
        self.assertEqual(mock_es.delete.call_args[1]["id"], str(prod.id))

        # Soft deleted in DB?
        prod.refresh_from_db()
        self.assertFalse(prod.is_active)
