"""Provider registry (Phase 1.6).

Resolves the active provider for a capability. In Phase 1.6 only the safe no-op
providers exist; real providers are registered here in later phases based on the
configured provider name — without the rest of the app depending on any vendor.
"""
from __future__ import annotations

from .config import get_messaging_provider_name, get_map_provider_name
from .providers import (
    MapsProvider,
    MessagingProvider,
    NoopMapsProvider,
    NoopMessagingProvider,
)


def get_messaging_provider() -> MessagingProvider:
    # Foundation: always the no-op provider (nothing is sent). Later phases map
    # get_messaging_provider_name() -> a real adapter.
    _ = get_messaging_provider_name()
    return NoopMessagingProvider()


def get_maps_provider() -> MapsProvider:
    _ = get_map_provider_name()
    return NoopMapsProvider()
