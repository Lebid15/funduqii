"""Integrations foundation tests (Phase 1.6).

Prove that everything is disabled by default and that the default providers
perform no send / no external call.
"""
from django.test import SimpleTestCase

from apps.integrations.config import (
    is_maps_enabled,
    is_messaging_enabled,
    is_whatsapp_enabled,
)
from apps.integrations.constants import MESSAGE_STATUS_DISABLED
from apps.integrations.providers import (
    MapLocation,
    NoopMapsProvider,
    NoopMessagingProvider,
)
from apps.integrations.registry import get_maps_provider, get_messaging_provider


class IntegrationsDisabledByDefaultTests(SimpleTestCase):
    def test_all_providers_disabled_by_default(self):
        self.assertFalse(is_messaging_enabled())
        self.assertFalse(is_whatsapp_enabled())
        self.assertFalse(is_maps_enabled())

    def test_default_messaging_provider_is_noop_and_sends_nothing(self):
        provider = get_messaging_provider()
        self.assertIsInstance(provider, NoopMessagingProvider)
        result = provider.send(
            to="+000000000",
            template="guest.reservation_confirmed",
            variables={"guest_name": "Test"},
            channel="whatsapp",
        )
        self.assertEqual(result.status, MESSAGE_STATUS_DISABLED)
        self.assertEqual(result.provider, "disabled")

    def test_default_maps_provider_is_noop(self):
        provider = get_maps_provider()
        self.assertIsInstance(provider, NoopMapsProvider)
        # No geocoding / external call: it only echoes a stored map_url.
        self.assertEqual(provider.build_map_url(MapLocation()), "")
        self.assertEqual(
            provider.build_map_url(MapLocation(map_url="https://maps.example/x")),
            "https://maps.example/x",
        )
