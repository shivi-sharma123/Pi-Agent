"""
Product Service — Django REST API application.

Models: Product, Category, ProductImage
Backed by SQLite (metadata) + Elasticsearch (full-text index)
"""
from __future__ import annotations

import os
import uuid

# Bootstrap Django settings before importing anything else
import app.config  # noqa: F401 — side-effect: configures settings

import json
import time
from datetime import datetime

from django.db import models
from elasticsearch import Elasticsearch, NotFoundError
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.urls import path, include
from django.http import JsonResponse


# ---------------------------------------------------------------------------
# Elasticsearch Client
# ---------------------------------------------------------------------------

def get_es() -> Elasticsearch:
    url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    return Elasticsearch(url, request_timeout=10)


ES_INDEX = os.getenv("ELASTICSEARCH_INDEX", "products")


def ensure_index() -> None:
    """Create the products index with mappings if it doesn't exist."""
    es = get_es()
    if not es.indices.exists(index=ES_INDEX):
        es.indices.create(
            index=ES_INDEX,
            body={
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "name": {"type": "text", "analyzer": "standard"},
                        "description": {"type": "text", "analyzer": "standard"},
                        "category": {"type": "keyword"},
                        "price": {"type": "float"},
                        "stock": {"type": "integer"},
                        "tags": {"type": "keyword"},
                        "sku": {"type": "keyword"},
                        "is_active": {"type": "boolean"},
                        "created_at": {"type": "date"},
                    }
                },
                "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            },
        )


# ---------------------------------------------------------------------------
# Django ORM Models
# ---------------------------------------------------------------------------

class Category(models.Model):
    """Product category (flat, no hierarchy in Phase 2)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "app"
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    """Product in the catalog."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="products"
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    stock = models.IntegerField(default=0)
    tags = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "app"
        ordering = ["-created_at"]

    def to_es_doc(self) -> dict:
        """Serialize for Elasticsearch indexing."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "category": self.category.name if self.category else None,
            "price": float(self.price),
            "stock": self.stock,
            "tags": self.tags or [],
            "sku": self.sku,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def index_to_es(self) -> None:
        """Index (or re-index) this product into Elasticsearch."""
        try:
            es = get_es()
            es.index(index=ES_INDEX, id=str(self.id), document=self.to_es_doc())
        except Exception as exc:
            print(f"WARN: ES index failed for product {self.id}: {exc}")

    def delete_from_es(self) -> None:
        """Remove this product from Elasticsearch."""
        try:
            es = get_es()
            es.delete(index=ES_INDEX, id=str(self.id), ignore=[404])
        except Exception as exc:
            print(f"WARN: ES delete failed for product {self.id}: {exc}")


# ---------------------------------------------------------------------------
# DRF Serializers
# ---------------------------------------------------------------------------

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "created_at"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source="category.name", read_only=True, default=None
    )

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "description",
            "category", "category_name",
            "price", "stock", "tags", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# ViewSets
# ---------------------------------------------------------------------------

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    lookup_field = "id"


class ProductViewSet(viewsets.ModelViewSet):
    """Product CRUD + auto ES sync on create/update/delete."""
    queryset = Product.objects.select_related("category").filter(is_active=True)
    serializer_class = ProductSerializer
    lookup_field = "id"

    def perform_create(self, serializer):
        product = serializer.save()
        product.index_to_es()

    def perform_update(self, serializer):
        product = serializer.save()
        product.index_to_es()

    def perform_destroy(self, instance):
        instance.delete_from_es()
        instance.is_active = False  # soft delete
        instance.save()

    @action(detail=True, methods=["post"], url_path="reindex")
    def reindex(self, request, id=None):
        """Force re-index of a single product into Elasticsearch."""
        product = self.get_object()
        product.index_to_es()
        return Response({"message": f"Product {id} re-indexed successfully"})
