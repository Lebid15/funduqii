"""Tests for Phase 1 infrastructure and Phase 1.5 foundation."""
from django.core.cache import cache
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.common.pagination import DefaultPagination
from apps.core.tasks import ping


class HealthCheckTests(APITestCase):
    """The health endpoint must report the service as available."""

    def test_health_returns_ok(self) -> None:
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {"status": "ok", "service": "funduqii-api"},
        )


class CacheFoundationTests(SimpleTestCase):
    """The cache backend is wired and usable (Redis in prod, locmem in dev)."""

    def test_cache_set_get(self) -> None:
        cache.set("funduqii:probe", "value", timeout=30)
        self.assertEqual(cache.get("funduqii:probe"), "value")


class CeleryTaskFoundationTests(SimpleTestCase):
    """The foundation Celery task loads and runs (called synchronously)."""

    def test_ping_task_runs(self) -> None:
        self.assertEqual(ping(), "pong")


class PaginationFoundationTests(SimpleTestCase):
    """Sensible default and hard-capped page sizes are configured."""

    def test_pagination_defaults(self) -> None:
        self.assertEqual(DefaultPagination.page_size, 25)
        self.assertEqual(DefaultPagination.max_page_size, 100)
        self.assertEqual(DefaultPagination.page_size_query_param, "page_size")
