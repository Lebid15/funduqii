"""Provider interfaces + safe no-op implementations (Phase 1.6 foundation).

This is the adapter/provider seam that keeps Funduqii independent of any single
vendor. In Phase 1.6 there are **no real providers**: the default no-op provider
sends nothing and performs no external calls. Real providers (official WhatsApp
Business Platform, email, SMS, maps geocoding, …) plug in behind these
interfaces in their own phases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .constants import DISABLED, MESSAGE_STATUS_DISABLED


@dataclass(frozen=True)
class MessageResult:
    """Outcome of a (would-be) message send. No side effects in Phase 1.6."""

    status: str
    provider: str
    detail: str = ""


@runtime_checkable
class MessagingProvider(Protocol):
    """A messaging adapter. Real implementations MUST use official APIs only,
    send asynchronously via Celery for non-critical messages, and never raise
    into a critical request path unless the send is itself critical."""

    name: str

    def send(
        self,
        *,
        to: str,
        template: str,
        variables: dict,
        channel: str,
    ) -> MessageResult: ...


class NoopMessagingProvider:
    """Default provider: performs NO external call and sends NOTHING.

    Returns a ``disabled`` result so callers can safely no-op until a real
    provider is configured in a later phase.
    """

    name = DISABLED

    def send(
        self,
        *,
        to: str,
        template: str,
        variables: dict,
        channel: str,
    ) -> MessageResult:
        return MessageResult(
            status=MESSAGE_STATUS_DISABLED,
            provider=self.name,
            detail="messaging disabled (Phase 1.6 foundation — nothing sent)",
        )


@dataclass(frozen=True)
class MapLocation:
    """Provider-neutral location value. Storage fields are documented in
    docs/MAPS_AND_LOCATION_STRATEGY.md; no geocoding happens here."""

    latitude: float | None = None
    longitude: float | None = None
    map_url: str = ""
    extra: dict = field(default_factory=dict)


@runtime_checkable
class MapsProvider(Protocol):
    name: str

    def build_map_url(self, location: MapLocation) -> str: ...


class NoopMapsProvider:
    """Default maps provider: no external call. Returns any stored ``map_url``
    as-is, otherwise an empty string."""

    name = DISABLED

    def build_map_url(self, location: MapLocation) -> str:
        return location.map_url or ""
