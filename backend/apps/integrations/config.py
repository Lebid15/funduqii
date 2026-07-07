"""Settings helpers for integrations (Phase 1.6).

Reads the provider configuration from Django settings (which read env). Every
value defaults to disabled/empty, so nothing is active until real values are
provided on a server — never in Git.
"""
from __future__ import annotations

from django.conf import settings

from .constants import DISABLED


def get_map_provider_name() -> str:
    return getattr(settings, "MAP_PROVIDER", DISABLED) or DISABLED


def is_maps_enabled() -> bool:
    return get_map_provider_name() != DISABLED


def get_messaging_provider_name() -> str:
    return getattr(settings, "MESSAGING_PROVIDER", DISABLED) or DISABLED


def is_messaging_enabled() -> bool:
    return get_messaging_provider_name() != DISABLED


def get_whatsapp_provider_name() -> str:
    return getattr(settings, "WHATSAPP_PROVIDER", DISABLED) or DISABLED


def is_whatsapp_enabled() -> bool:
    return get_whatsapp_provider_name() != DISABLED
