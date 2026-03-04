"""
Product Service — Django REST API.

Manages the product catalog backed by Elasticsearch for full-text search.

Endpoints:
  GET  /health                  → liveness + ES check
  GET  /products                → list products (paginated, filterable)
  POST /products                → create a new product
  GET  /products/{id}           → get product detail
  PUT  /products/{id}           → update product
  DELETE /products/{id}         → delete product (soft)
  GET  /categories              → list categories
  POST /products/{id}/reindex   → force ES reindex for product
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret-change-in-prod")
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "django_prometheus",
    "app",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # SQLite for Phase 2 product metadata; ES holds the search index.
        # Phase 3+ will migrate to PostgreSQL.
        "NAME": os.getenv("PRODUCT_DB_PATH", "/tmp/products.db"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "app.urls"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTICSEARCH_INDEX = os.getenv("ELASTICSEARCH_INDEX", "products")
