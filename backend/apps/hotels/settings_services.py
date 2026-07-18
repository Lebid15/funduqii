"""Typed settings groups + central audit for hotel settings (§9.1/§9.2/§9.17).

The settings stay on the single ``HotelSettings`` model (owner decision: typed
groups over the model, not per-domain models). This module defines the LOGICAL
grouping used by the §9.2 sectioned UI + per-section save endpoints, and the
append-only audit trail written on every settings change.

``default_booking_status`` is deliberately NOT in any group — it is a dead field
(documented "future settings only; NOT operations"), and §9.19 forbids surfacing
a setting that has no effect.
"""
from __future__ import annotations

from .models import SettingsAuditLog, SettingsAuditScope

# Ordered map: section key -> the HotelSettings fields it owns. The order here is
# the display order of the settings sections.
HOTEL_SETTINGS_GROUPS: dict[str, list[str]] = {
    "identity": [
        "display_name",
        "legal_name",
        "facility_type",
        "star_rating",
        "short_description",
        "description",
    ],
    "localization": [
        "default_language",
        "timezone",
        "default_currency",
        "accepted_currencies",
        "default_phone_country",
    ],
    "contact": [
        "phone",
        "whatsapp_number",
        "email",
        "website_url",
        "facebook_url",
        "instagram_url",
        "social_links",
    ],
    "location": [
        "country",
        "city",
        "area",
        "address_line",
        "latitude",
        "longitude",
        "map_url",
        "google_place_id",
        "location_notes",
    ],
    "policies": [
        "check_in_time",
        "check_out_time",
        "cancellation_policy",
        "child_policy",
        "pet_policy",
        "smoking_policy",
        "extra_bed_policy",
        "important_notes",
    ],
    "operational": [
        "require_guest_phone",
        "require_guest_document",
        "housekeeping_inspection_required",
        "restaurant_enabled",
        "cafe_enabled",
    ],
    "public": [
        "public_is_listed",
        "allow_public_booking",
        "public_booking_requires_confirmation",
        "public_featured",
        "public_slug",
        "public_min_nights",
        "public_max_nights",
        "public_terms_text",
        "public_sort_order",
    ],
}

# Every field that belongs to some group (the editable settings surface).
GROUPED_FIELDS: frozenset[str] = frozenset(
    f for fields in HOTEL_SETTINGS_GROUPS.values() for f in fields
)


def group_fields(section: str) -> list[str] | None:
    """The fields of a section, or None if the section key is unknown."""
    return HOTEL_SETTINGS_GROUPS.get(section)


def _jsonable(value):
    """Normalize a model value to something JSON-serialisable for the diff."""
    import datetime
    from decimal import Decimal

    if isinstance(value, (datetime.date, datetime.time, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def diff_settings(instance, before: dict, after: dict) -> dict:
    """Field-level diff {field: {old, new}} for fields whose value changed.

    ``before``/``after`` are dicts of field -> value snapshots taken around the
    save. Only fields present in ``after`` (i.e. the ones the request touched)
    and whose value actually changed are recorded.
    """
    changes: dict[str, dict] = {}
    for field, new_value in after.items():
        old_value = before.get(field)
        if old_value != new_value:
            changes[field] = {
                "old": _jsonable(old_value),
                "new": _jsonable(new_value),
            }
    return changes


def snapshot(instance, fields) -> dict:
    """Snapshot the given fields from a model instance."""
    return {f: getattr(instance, f) for f in fields}


def record_settings_change(
    *,
    scope: str,
    section: str,
    changes: dict,
    hotel=None,
    actor=None,
    reason: str = "",
) -> SettingsAuditLog | None:
    """Append an audit row IFF something changed. No-op on an empty diff."""
    if not changes:
        return None
    return SettingsAuditLog.objects.create(
        scope=scope,
        hotel=hotel,
        section=section,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        changes=changes,
        reason=(reason or "")[:255],
    )
