"""Public website + public booking services (Phase 15) — the safe boundary.

This app exposes hotels to VISITORS. Its rules are the opposite of every
hotel-console app: no authentication, therefore the OUTPUT is aggressively
limited and the only write is booking creation.

Hard boundaries (deliberate):
- **Reuses the internal engines**: availability goes through
  ``AvailabilityService`` and bookings through
  ``reservations.services.create_reservation`` — the SAME overbooking rules
  as the hotel console. Nothing financial is ever touched (no Payment,
  Invoice, Folio, Stay, check-in).
- **Public bookings are never instant**: ``booking_kind=future`` always, a
  room TYPE is booked (never a specific room), and the default status is
  ``held`` with a documented 72h hold — the hotel confirms from its own
  reservations console. ``confirmed`` happens only when the hotel explicitly
  disabled confirmation (``public_booking_requires_confirmation=False``).
- **Manage token**: 32 bytes of urandom, shown to the visitor exactly once;
  only its SHA-256 hex is stored, and comparison is constant-time.
- **Exposure limits**: no staff, no finance, no folio, no internal notes,
  no room numbers, no other hotels' data. Cancellation is a REQUEST — it
  never voids finance and never deletes the reservation.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import secrets

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.hotels.models import HotelMedia, HotelSettings, MediaKind
from apps.reservations.availability import AvailabilityService
from apps.reservations.models import (
    BookingKind,
    Reservation,
    ReservationSource,
    ReservationStatus,
)
from apps.reservations.services import create_reservation
from apps.rooms.models import RoomType
from apps.tenancy.models import Hotel, HotelStatus

#: How long a public `held` booking blocks inventory while awaiting the
#: hotel's confirmation (documented decision).
PUBLIC_HOLD_HOURS = 72

#: Hard caps on a single public request (documented sanity limits).
MAX_ROOMS_PER_BOOKING = 5
MAX_GUESTS_PER_BOOKING = 20
MAX_ADVANCE_DAYS = 366


def published_hotels_qs():
    """Hotels a visitor may see: ACTIVE (never suspended/setup) + listed +
    with a public slug."""
    return (
        HotelSettings.objects.select_related("hotel")
        .filter(
            hotel__status=HotelStatus.ACTIVE,
            public_is_listed=True,
            public_slug__isnull=False,
        )
        .exclude(public_slug="")
        .order_by("public_sort_order", "id")
    )


def get_published_hotel(slug: str) -> HotelSettings | None:
    return published_hotels_qs().filter(public_slug=slug).first()


def public_room_types_qs(hotel: Hotel):
    return RoomType.objects.filter(
        hotel=hotel, is_active=True, public_is_visible=True
    ).order_by("public_sort_order", "sort_order", "name")


def _media_url(media: HotelMedia | None) -> str:
    if media is None or not media.file:
        return ""
    try:
        return media.file.url
    except ValueError:  # pragma: no cover - storage without a file
        return ""


def hotel_media_payload(hotel: Hotel) -> dict:
    media = list(hotel.media.filter(is_active=True))
    cover = next((m for m in media if m.kind == MediaKind.COVER), None)
    logo = next((m for m in media if m.kind == MediaKind.LOGO), None)
    gallery = [m for m in media if m.kind == MediaKind.GALLERY]
    return {
        "cover_url": _media_url(cover),
        "logo_url": _media_url(logo),
        "gallery": [
            {"url": _media_url(m), "alt": m.alt_text}
            for m in gallery
            if _media_url(m)
        ],
    }


def room_type_public_payload(settings_obj: HotelSettings, room_type: RoomType) -> dict:
    price = room_type.public_base_price or room_type.base_rate
    return {
        "id": room_type.id,
        "name": room_type.public_name or room_type.name,
        "description": room_type.public_description or room_type.description,
        "base_capacity": room_type.base_capacity,
        "max_capacity": room_type.max_capacity,
        "bed_type": room_type.bed_type,
        "base_price": str(price) if price is not None else None,
        "currency": settings_obj.default_currency,
    }


# --- Validation --------------------------------------------------------------------


def validate_public_dates(settings_obj: HotelSettings, check_in, check_out) -> None:
    today = timezone.localdate()
    if check_in < today:
        raise serializers.ValidationError(
            {"check_in": "Check-in cannot be in the past."}
        )
    if check_out <= check_in:
        raise serializers.ValidationError(
            {"check_out": "Check-out must be after check-in."}
        )
    if (check_in - today).days > MAX_ADVANCE_DAYS:
        raise serializers.ValidationError(
            {"check_in": "Bookings this far ahead are not accepted online."}
        )
    nights = (check_out - check_in).days
    if settings_obj.public_min_nights and nights < settings_obj.public_min_nights:
        raise serializers.ValidationError(
            {"check_out": f"Minimum stay is {settings_obj.public_min_nights} nights."}
        )
    if settings_obj.public_max_nights and nights > settings_obj.public_max_nights:
        raise serializers.ValidationError(
            {"check_out": f"Maximum stay is {settings_obj.public_max_nights} nights."}
        )


def booking_open(settings_obj: HotelSettings) -> bool:
    # Phase 16: an expired/inactive subscription stops PUBLIC BOOKING too —
    # the hotel may stay listed, but visitors cannot book it.
    from apps.subscriptions.enforcement import subscription_blocks_writes

    return (
        settings_obj.hotel.status == HotelStatus.ACTIVE
        and settings_obj.public_is_listed
        and settings_obj.allow_public_booking
        and not subscription_blocks_writes(settings_obj.hotel)
    )


# --- Availability ------------------------------------------------------------------


def public_availability(
    settings_obj: HotelSettings, check_in, check_out, *, room_type_id=None
) -> list[dict]:
    """Public-safe availability: per visible room type, the available COUNT —
    never room numbers, never internal statuses."""
    hotel = settings_obj.hotel
    qs = public_room_types_qs(hotel)
    if room_type_id is not None:
        qs = qs.filter(id=room_type_id)
    results = []
    for room_type in qs:
        availability = AvailabilityService.availability_for_type(
            hotel, room_type, check_in, check_out
        )
        payload = room_type_public_payload(settings_obj, room_type)
        payload["available_quantity"] = availability.available_quantity
        payload["can_book"] = availability.available_quantity > 0
        results.append(payload)
    return results


# --- Public booking ----------------------------------------------------------------


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(reservation: Reservation, token: str) -> bool:
    if not reservation.public_manage_token_hash or not token:
        return False
    return hmac.compare_digest(
        reservation.public_manage_token_hash, _hash_token(token)
    )


@transaction.atomic
def create_public_booking(
    settings_obj: HotelSettings,
    *,
    room_type: RoomType,
    check_in,
    check_out,
    rooms_count: int,
    adults: int,
    children: int,
    guest_name: str,
    guest_phone: str,
    guest_email: str = "",
    guest_nationality: str = "",
    special_requests: str = "",
) -> tuple[Reservation, str]:
    """Create the reservation through the INTERNAL engine and attach the
    manage token. Returns ``(reservation, plaintext_token)`` — the only
    moment the plaintext exists."""
    hotel = settings_obj.hotel
    validate_public_dates(settings_obj, check_in, check_out)
    if room_type.hotel_id != hotel.id or not room_type.public_is_visible:
        raise serializers.ValidationError({"room_type": "Unknown room type."})

    status = (
        ReservationStatus.CONFIRMED
        if not settings_obj.public_booking_requires_confirmation
        else ReservationStatus.HELD
    )
    fields = dict(
        check_in_date=check_in,
        check_out_date=check_out,
        primary_guest_name=guest_name.strip(),
        primary_guest_phone=guest_phone.strip(),
        primary_guest_email=(guest_email or "").strip(),
        primary_guest_nationality=(guest_nationality or "").strip(),
        adults=adults,
        children=children,
        special_requests=(special_requests or "").strip(),
        source=ReservationSource.PUBLIC_WEBSITE,
        booking_kind=BookingKind.FUTURE,
        booking_channel_name="Funduqii Public",
    )
    if status == ReservationStatus.HELD:
        fields["hold_expires_at"] = timezone.now() + datetime.timedelta(
            hours=PUBLIC_HOLD_HOURS
        )
    # The SAME engine the hotel console uses: availability is re-checked
    # inside and overbooking raises `no_availability` — never bypassed.
    reservation = create_reservation(
        hotel,
        lines=[{"room_type": room_type, "quantity": rooms_count}],
        status=status,
        user=None,
        **fields,
    )
    token = secrets.token_urlsafe(32)
    reservation.public_manage_token_hash = _hash_token(token)
    reservation.public_manage_token_created_at = timezone.now()
    reservation.save(
        update_fields=[
            "public_manage_token_hash",
            "public_manage_token_created_at",
            "updated_at",
        ]
    )
    return reservation, token


def public_booking_payload(settings_obj: HotelSettings, reservation: Reservation) -> dict:
    """The visitor-facing view of a booking — NOTHING internal: no staff, no
    finance, no internal notes, no assigned room numbers."""
    line = reservation.lines.select_related("room_type").first()
    room_type = line.room_type if line else None
    return {
        "reference": reservation.reservation_number,
        "status": reservation.status,
        "requires_confirmation": reservation.status == ReservationStatus.HELD,
        "hotel_name": settings_obj.display_name or settings_obj.hotel.name,
        "hotel_slug": settings_obj.public_slug,
        "check_in_date": str(reservation.check_in_date),
        "check_out_date": str(reservation.check_out_date),
        "nights": reservation.nights,
        "room_type_name": (
            (room_type.public_name or room_type.name) if room_type else ""
        ),
        "rooms_count": line.quantity if line else 1,
        "adults": reservation.adults,
        "children": reservation.children,
        "guest_name": reservation.primary_guest_name,
        "guest_phone": reservation.primary_guest_phone,
        "guest_email": reservation.primary_guest_email,
        "special_requests": reservation.special_requests,
        "cancel_requested_at": (
            reservation.public_cancel_requested_at.isoformat()
            if reservation.public_cancel_requested_at
            else None
        ),
        "created_at": reservation.created_at.isoformat(),
    }


def find_public_booking(reference: str) -> Reservation | None:
    return (
        Reservation.objects.filter(
            reservation_number=reference,
            source=ReservationSource.PUBLIC_WEBSITE,
        )
        .select_related("hotel")
        .first()
    )


@transaction.atomic
def request_public_cancellation(
    reservation: Reservation, *, reason: str = ""
) -> Reservation:
    """Record a cancellation REQUEST from the visitor. It never cancels the
    reservation directly, never voids finance and never deletes anything —
    the hotel decides through its own reservations workflow. Idempotent."""
    if reservation.public_cancel_requested_at is None:
        reservation.public_cancel_requested_at = timezone.now()
        reservation.public_cancel_reason = (reason or "").strip()[:255]
        reservation.save(
            update_fields=[
                "public_cancel_requested_at",
                "public_cancel_reason",
                "updated_at",
            ]
        )
    return reservation
