"""
URL configuration for Product Service.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.http import JsonResponse
import os

from app.models import CategoryViewSet, ProductViewSet, get_es

# ---------------------------------------------------------------------------
# DRF Router
# ---------------------------------------------------------------------------
router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="categories")
router.register(r"products", ProductViewSet, basename="products")


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
def health(request):
    es_ok = False
    try:
        es = get_es()
        info = es.cluster.health(timeout="3s")
        es_ok = info.get("status") in ("green", "yellow")
    except Exception:
        pass

    service_status = "healthy" if es_ok else "degraded"
    return JsonResponse(
        {
            "status": service_status,
            "service": "product-svc",
            "version": "0.2.0",
            "dependencies": {"elasticsearch": "ok" if es_ok else "down"},
        },
        status=200 if es_ok else 503,
    )


urlpatterns = [
    path("health", health),
    path("", include(router.urls)),
    path("", include("django_prometheus.urls")),
]
