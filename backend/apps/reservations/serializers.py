"""DRF serializers for reservations & availability (Phase 6).

Hotel scoping and cross-tenant safety are enforced here: a reservation line may
only reference an ACTIVE room type from the SAME hotel as the request context.
Dates, quantities and capacity are validated here; overbooking is enforced in
the services/availability layer inside a transaction.
"""
from __future__ import annotations

import re
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from rest_framework import serializers

from apps.common.exceptions import CrossTenantReference
from apps.guests.models import Guest
from apps.guests.serializers import can_view_sensitive
from apps.guests.services import mask_document
from apps.rooms.models import Floor, Room, RoomStatus, RoomType

from .availability import TypeAvailability
from .models import (
    BookingKind,
    ExpectedPaymentMethod,
    OccupantRelationship,
    Reservation,
    ReservationDocument,
    ReservationOccupant,
    ReservationRoomLine,
    ReservationSource,
    ReservationStatus,
)

_PHONE_RE = re.compile(r"^[0-9+\-\s()]{4,32}$")
_WRITE_STATUSES = (ReservationStatus.HELD, ReservationStatus.CONFIRMED)


def can_view_finance(request) -> bool:
    """True when the caller may see reservation money (``finance.view``).

    Mirrors :func:`apps.guests.serializers.can_view_sensitive`: fail-closed when
    no request/user/hotel context is present. Used to gate the derived financial
    read fields (§35 — the card's financial block is permission-scoped) so the
    money is masked SERVER-SIDE, not merely hidden in the UI.
    """
    from apps.rbac.services import has_hotel_permission

    user = getattr(request, "user", None)
    hotel = getattr(request, "hotel", None)
    if user is None or hotel is None:
        return False
    return has_hotel_permission(user, hotel, "finance.view")
# Room statuses that cannot receive a specific assignment (Phase 6.1).
_NON_ASSIGNABLE_ROOM_STATUSES = (
    RoomStatus.MAINTENANCE,
    RoomStatus.OUT_OF_SERVICE,
    RoomStatus.ARCHIVED,
)


class ReservationLineReadSerializer(serializers.ModelSerializer):
    room_type_name = serializers.CharField(source="room_type.name", read_only=True)
    room_type_code = serializers.CharField(source="room_type.code", read_only=True)
    max_capacity = serializers.IntegerField(
        source="room_type.max_capacity", read_only=True
    )
    room_number = serializers.SerializerMethodField()
    # Additive read-only fields for the reworked reservations UI: the floor of
    # the SPECIFIC assigned room (a line may have no room -> both are null).
    floor_name = serializers.SerializerMethodField()
    floor_number = serializers.SerializerMethodField()

    class Meta:
        model = ReservationRoomLine
        fields = [
            "id",
            "room_type",
            "room_type_name",
            "room_type_code",
            "max_capacity",
            "room",
            "room_number",
            "floor_name",
            "floor_number",
            "quantity",
            "adults",
            "children",
            "notes",
        ]
        read_only_fields = fields

    def get_room_number(self, obj):
        return obj.room.number if obj.room_id else None

    def get_floor_name(self, obj):
        if obj.room_id and obj.room.floor_id:
            return obj.room.floor.name
        return None

    def get_floor_number(self, obj):
        if obj.room_id and obj.room.floor_id:
            return obj.room.floor.number
        return None


class ReservationOccupantReadSerializer(serializers.ModelSerializer):
    """Read representation of one adult companion.

    ``national_id`` is MASKED for callers without ``guests.view_sensitive_data``
    (reusing the guests masking rule) and when no request context is present.
    """

    class Meta:
        model = ReservationOccupant
        fields = [
            "id",
            "guest",
            "first_name",
            "last_name",
            "father_name",
            "mother_name",
            "national_id",
            "nationality",
            "date_of_birth",
            "relationship",
            "created_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is None or not can_view_sensitive(request):
            # ``national_id`` is bullet-masked (identity number); the remaining
            # sensitive identity fields (§36/§39, sec-F2) are REDACTED to null —
            # bullet-masking a name/DoB is meaningless. Fail-closed when there is
            # no request context, exactly like the national_id rule.
            data["national_id"] = mask_document(instance.national_id)
            data["father_name"] = None
            data["mother_name"] = None
            data["date_of_birth"] = None
        return data


class ReservationDocumentReadSerializer(serializers.ModelSerializer):
    """Metadata-only read representation of a reservation document.

    The raw image bytes are NEVER embedded here — only ``has_front`` /
    ``has_back`` existence flags plus ``front_url`` / ``back_url`` that point at
    the EXISTING signed-URL mint endpoint (``reservation-document-signed-url``).
    The document ``number`` (an identity number) is masked like the guests
    document number.

    SEC (Decision 8 / RV-SEC F-1): opening / downloading the ORIGINAL document
    image is more sensitive than listing a masked number, so ``front_url`` /
    ``back_url`` — the only path to the image mint — are returned ONLY when the
    caller ALSO holds ``guests.view_sensitive_data`` (fail-closed when there is
    no request context). Without it the URLs are ``null`` (never minted) and the
    row carries only the type + masked number; the mint/stream endpoints reject
    the reconstructed URL server-side regardless, so this merely keeps the UI
    honest (no broken "view image" button), it is NOT the enforcement point.
    ``has_front`` / ``has_back`` stay truthful existence flags but do not lead to
    the image. This mirrors ``guests.serializers.GuestDocumentSerializer``.
    """

    has_front = serializers.SerializerMethodField()
    has_back = serializers.SerializerMethodField()
    front_url = serializers.SerializerMethodField()
    back_url = serializers.SerializerMethodField()

    class Meta:
        model = ReservationDocument
        fields = [
            "id",
            "reservation",
            "occupant",
            "doc_type",
            "number",
            "has_front",
            "has_back",
            "front_url",
            "back_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_has_front(self, obj) -> bool:
        return bool(obj.front_file)

    def get_has_back(self, obj) -> bool:
        return bool(obj.back_file)

    def _mint_url(self, obj, side: str, has_side: bool):
        if not has_side:
            return None
        request = self.context.get("request")
        # Fail CLOSED: a missing request context or a caller without
        # ``guests.view_sensitive_data`` never receives the image-mint URL.
        if request is None or not can_view_sensitive(request):
            return None
        path = reverse(
            "reservations:reservation-document-signed-url",
            kwargs={"doc_id": obj.id, "side": side},
        )
        return request.build_absolute_uri(path)

    def get_front_url(self, obj):
        return self._mint_url(obj, "front", bool(obj.front_file))

    def get_back_url(self, obj):
        return self._mint_url(obj, "back", bool(obj.back_file))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is None or not can_view_sensitive(request):
            data["number"] = mask_document(instance.number)
        return data


class ReservationOccupantWriteSerializer(serializers.Serializer):
    """Write payload for one adult companion.

    ``guest`` is an OPTIONAL link to an existing guest (resolved + hotel-scoped
    by the parent serializer). When omitted, the structured identity is stored
    inline without forcing a Guest row to be created.
    """

    guest = serializers.IntegerField(required=False, allow_null=True)
    first_name = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    last_name = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    father_name = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    mother_name = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    national_id = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    nationality = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    relationship = serializers.ChoiceField(
        choices=OccupantRelationship.choices,
        required=False,
        allow_blank=True,
        default="",
    )

    def validate_national_id(self, value):
        # A masked value must never round-trip back into an occupant record.
        if value and "•" in value:
            raise serializers.ValidationError(
                "Enter the real national ID (masked values are rejected)."
            )
        return (value or "").strip()


class ReservationDocumentWriteSerializer(serializers.Serializer):
    """Metadata-only write payload for a reservation document.

    Files are uploaded through a dedicated endpoint in a later pass; this
    captures ``doc_type`` / ``number`` / optional ``occupant`` only.
    """

    occupant = serializers.IntegerField(required=False, allow_null=True)
    doc_type = serializers.ChoiceField(
        choices=ReservationDocument._meta.get_field("doc_type").choices,
        required=False,
        allow_blank=True,
        default="",
    )
    number = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default=""
    )

    def validate_number(self, value):
        if value and "•" in value:
            raise serializers.ValidationError(
                "Enter the real document number (masked values are rejected)."
            )
        return (value or "").strip()


class ReservationSerializer(serializers.ModelSerializer):
    """Read representation with nested lines and computed fields."""

    lines = ReservationLineReadSerializer(many=True, read_only=True)
    occupants = ReservationOccupantReadSerializer(many=True, read_only=True)
    nights = serializers.IntegerField(read_only=True)
    total_guests = serializers.IntegerField(read_only=True)
    created_by = serializers.SerializerMethodField()
    # Additive read-only display name for the creator (full_name, else email,
    # else null when created_by is unset). Existing created_by (email) is kept.
    created_by_name = serializers.SerializerMethodField()
    # Post-check-in guard (final closure): the UI freezes dates/rooms and
    # hides cancel when the guest is in-house — the backend enforces it too.
    has_in_house_stay = serializers.SerializerMethodField()
    # RESERVATIONS-FORM-UX-CORRECTION §25 — the LATEST related stay's status
    # (in_house / checked_out / cancelled) or null when the booking never checked
    # in. Distinguishes a departed guest from one who never arrived; complements
    # ``has_in_house_stay``. Read-only, prefetched (no N+1).
    stay_status = serializers.SerializerMethodField()
    stay_id = serializers.SerializerMethodField()
    # RESERVATIONS-FORM-UX-CORRECTION §37 — a NON-sensitive count of the
    # reservation's documents (``ReservationDocument`` rows). Lets the card show
    # the docs button only when count>0 with a count Badge. Computed from the
    # prefetched ``documents`` relation (list/detail querysets) so it never N+1s;
    # the button itself is gated on the frontend by ``reservation_documents.view``.
    document_count = serializers.SerializerMethodField()
    # RESERVATIONS-FORM-UX-CORRECTION §26/§31/§35 — compact DERIVED financial read
    # (never stored). Money fields are gated by ``finance.view`` (masked to null
    # otherwise); ``currency``/``nights`` are not sensitive.
    nightly_rate = serializers.SerializerMethodField()
    reservation_total = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    paid = serializers.SerializerMethodField()
    remaining = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    is_priced = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            "id",
            "reservation_number",
            "status",
            "source",
            "booking_kind",
            "check_in_date",
            "check_out_date",
            "expected_arrival_time",
            "nights",
            # RESERVATIONS-FORM-REWORK: optional link to the central guest
            # directory (id only) plus the structured, frozen snapshot fields.
            "primary_guest",
            "primary_guest_name",
            "primary_guest_phone",
            "primary_guest_email",
            "primary_guest_nationality",
            "primary_guest_document_type",
            "primary_guest_document_number",
            "primary_guest_first_name",
            "primary_guest_last_name",
            "primary_guest_father_name",
            "primary_guest_mother_name",
            "primary_guest_national_id",
            "primary_guest_date_of_birth",
            "adults",
            "children",
            "total_guests",
            "notes",
            "special_requests",
            "booking_channel_name",
            "expected_payment_method",
            "no_show_reason",
            "cancellation_reason",
            "cancelled_at",
            "hold_expires_at",
            # Phase 15: the hotel sees a public booking's cancel request; the
            # manage-token HASH is deliberately never serialized.
            "public_cancel_requested_at",
            "public_cancel_reason",
            "has_in_house_stay",
            "stay_status",
            "stay_id",
            "document_count",
            "nightly_rate",
            "reservation_total",
            "currency",
            "paid",
            "remaining",
            "payment_status",
            "is_priced",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
            "lines",
            "occupants",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        return obj.created_by.email if obj.created_by_id else None

    def get_created_by_name(self, obj):
        if obj.created_by_id is None:
            return None
        return obj.created_by.full_name or obj.created_by.email

    def get_has_in_house_stay(self, obj) -> bool:
        from .services import has_in_house_stay

        return has_in_house_stay(obj)

    def get_stay_status(self, obj):
        from .services import latest_stay

        stay = latest_stay(obj)
        return stay.status if stay is not None else None

    def get_stay_id(self, obj):
        from .services import latest_stay

        stay = latest_stay(obj)
        return stay.id if stay is not None else None

    def get_document_count(self, obj) -> int:
        # ``len`` of the prefetched ``documents`` relation — zero extra queries on
        # the prefetched list/detail paths (RESERVATIONS-FORM-UX-CORRECTION §37).
        return len(obj.documents.all())

    # --- Derived financial summary (permission-gated, no stored balance) ------

    def _can_finance(self) -> bool:
        """Cache the ``finance.view`` decision on the (shared, per-response) child
        serializer so a list render evaluates the permission once, not per row."""
        cached = getattr(self, "_can_finance_cache", None)
        if cached is None:
            cached = (bool(can_view_finance(self.context.get("request"))),)
            self._can_finance_cache = cached
        return cached[0]

    def _financials(self, obj) -> dict:
        """Compute (and memoize on the instance) the derived money summary — only
        when the caller may see money, so unauthorized reads skip the folio/payment
        work entirely (fail-closed + cheaper)."""
        cache = getattr(obj, "_res_financials_cache", None)
        if cache is None:
            from .services import reservation_financials

            request = self.context.get("request")
            hotel = getattr(request, "hotel", None)
            if self._can_finance():
                cache = reservation_financials(obj, hotel=hotel)
                cache["_visible"] = True
            else:
                settings_obj = getattr(hotel, "settings", None)
                currency = (getattr(settings_obj, "default_currency", "") or "") or "USD"
                cache = {
                    "currency": currency,
                    "nights": obj.nights,
                    "nightly_rate": None,
                    "reservation_total": None,
                    "paid": None,
                    "remaining": None,
                    "payment_status": None,
                    "is_priced": None,
                    "_visible": False,
                }
            obj._res_financials_cache = cache
        return cache

    @staticmethod
    def _money_str(value):
        return str(value) if value is not None else None

    def get_currency(self, obj):
        return self._financials(obj)["currency"]

    def get_nightly_rate(self, obj):
        return self._money_str(self._financials(obj)["nightly_rate"])

    def get_reservation_total(self, obj):
        return self._money_str(self._financials(obj)["reservation_total"])

    def get_paid(self, obj):
        return self._money_str(self._financials(obj)["paid"])

    def get_remaining(self, obj):
        return self._money_str(self._financials(obj)["remaining"])

    def get_payment_status(self, obj):
        return self._financials(obj)["payment_status"]

    def get_is_priced(self, obj):
        return self._financials(obj)["is_priced"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # The primary guest's structured national ID AND the legacy document
        # number are sensitive identity values: mask BOTH consistently for
        # callers without ``guests.view_sensitive_data`` (and when no request
        # context is available, defaulting to masked — fail-closed). Mirrors the
        # guests masking rule.
        request = self.context.get("request")
        if request is None or not can_view_sensitive(request):
            data["primary_guest_national_id"] = mask_document(
                instance.primary_guest_national_id
            )
            data["primary_guest_document_number"] = mask_document(
                instance.primary_guest_document_number
            )
            # §36/§39 (sec-F2): the parent guest names + DoB are sensitive and
            # must not appear on the card. REDACT to null for callers without
            # ``guests.view_sensitive_data`` (fail-closed when no request).
            data["primary_guest_father_name"] = None
            data["primary_guest_mother_name"] = None
            data["primary_guest_date_of_birth"] = None
        return data


class ReservationLineWriteSerializer(serializers.Serializer):
    room_type = serializers.IntegerField()
    # Phase 6.1: an optional specific room assignment.
    room = serializers.IntegerField(required=False, allow_null=True)
    # RESERVATIONS-AUTO-ROOM: an OPTIONAL floor preference. In automatic mode it
    # narrows the deterministic picker to that floor; in manual mode it must
    # match the pinned room's floor. Request-only — never persisted on the line.
    floor = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    adults = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    children = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    # STAYS rate-integrity remediation (item 6) — an OPTIONAL explicit agreed rate.
    # Absent -> the snapshot policy applies (preserve on same RoomType, capture the
    # new type's base_rate on a type change). A value that DIFFERS from that default
    # is an OVERRIDE requiring ``stays.rate_override`` + a reason (enforced in the
    # service). Strictly positive.
    agreed_nightly_rate = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal("0.01"),
    )
    rate_override_reason = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class ReservationWriteSerializer(serializers.ModelSerializer):
    """Create/update payload. Resolves and validates lines against the hotel."""

    lines = ReservationLineWriteSerializer(many=True, required=False)
    # RESERVATIONS-FORM-REWORK: optional link to an existing guest (resolved and
    # hotel-scoped in ``validate``; declared as a plain id so ModelSerializer
    # never builds a cross-tenant queryset field) + optional adult companions.
    primary_guest = serializers.IntegerField(required=False, allow_null=True)
    occupants = ReservationOccupantWriteSerializer(many=True, required=False)
    # RESERVATIONS-AUTO-ROOM: request-only assignment mode (NOT a model field).
    # Absent -> legacy behaviour. "automatic" -> backend picks the room and any
    # client-provided line room is IGNORED. "manual" -> the line must pin a room.
    room_assignment_mode = serializers.ChoiceField(
        choices=[("automatic", "Automatic"), ("manual", "Manual")],
        required=False,
        allow_null=True,
    )
    # Round 3 §7.3: an OPTIONAL idempotency key (NOT a model field). On CREATE, a
    # matching OPEN, non-expired ``ReservationDraft`` for this hotel + key pins its
    # pre-reserved number onto the new reservation and is marked consumed; absent =>
    # a fresh number is allocated. Ignored on UPDATE (an edit reserves nothing).
    idempotency_key = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default=""
    )
    status = serializers.ChoiceField(
        choices=[(s.value, s.label) for s in _WRITE_STATUSES],
        required=False,
        default=ReservationStatus.CONFIRMED,
    )
    source = serializers.ChoiceField(
        choices=ReservationSource.choices,
        required=False,
        default=ReservationSource.DIRECT,
    )
    # Optional on write: when omitted it is derived from the check-in date
    # (today => instant, later => future).
    booking_kind = serializers.ChoiceField(
        choices=BookingKind.choices, required=False
    )
    expected_payment_method = serializers.ChoiceField(
        choices=ExpectedPaymentMethod.choices,
        required=False,
        allow_blank=True,
        default="",
    )

    class Meta:
        model = Reservation
        fields = [
            "status",
            "source",
            "booking_kind",
            "check_in_date",
            "check_out_date",
            "expected_arrival_time",
            "primary_guest",
            "primary_guest_name",
            "primary_guest_phone",
            "primary_guest_email",
            "primary_guest_nationality",
            "primary_guest_document_type",
            "primary_guest_document_number",
            "primary_guest_first_name",
            "primary_guest_last_name",
            "primary_guest_father_name",
            "primary_guest_mother_name",
            "primary_guest_national_id",
            "primary_guest_date_of_birth",
            "adults",
            "children",
            "notes",
            "special_requests",
            "booking_channel_name",
            "expected_payment_method",
            "hold_expires_at",
            "occupants",
            "lines",
            "room_assignment_mode",
            "idempotency_key",
        ]

    # --- field-level ---------------------------------------------------------

    def validate_primary_guest_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("A primary guest name is required.")
        return value.strip()

    def validate_primary_guest_national_id(self, value):
        # A masked value must never round-trip back into the snapshot.
        if value and "•" in value:
            raise serializers.ValidationError(
                "Enter the real national ID (masked values are rejected)."
            )
        return (value or "").strip()

    def validate_primary_guest_phone(self, value):
        if value and not _PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def validate_adults(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("At least one adult is required.")
        return value

    # --- object-level --------------------------------------------------------

    def _resolve_lines(self, raw_lines, *, mode=None):
        """Turn ``[{room_type: id, room: id?, floor: id?, ...}]`` into validated
        line dicts.

        Enforces cross-tenant safety, that each room type is active, and — when a
        specific room is assigned (Phase 6.1) — that the room belongs to the same
        hotel and room type, is bookable, and that quantity is 1. In AUTOMATIC
        mode (RESERVATIONS-AUTO-ROOM) any client-provided room is DROPPED and
        never validated — the backend assigns the room deterministically at save,
        so a client can never pin a room in automatic mode.
        """
        hotel = self.context["request"].hotel
        resolved = []
        for raw in raw_lines:
            rt = RoomType.objects.filter(pk=raw["room_type"]).first()
            if rt is None:
                raise serializers.ValidationError(
                    {"lines": "A referenced room type does not exist."}
                )
            if rt.hotel_id != hotel.id:
                raise CrossTenantReference({"field": "room_type"})
            if not rt.is_active:
                raise serializers.ValidationError(
                    {"lines": f"Room type '{rt.code}' is not active."}
                )
            if mode == "automatic":
                room = None  # client cannot pin a room; backend assigns it
            else:
                room = self._resolve_room(
                    raw.get("room"), rt, raw.get("quantity"), hotel
                )
            floor = self._resolve_floor(raw.get("floor"), hotel)
            resolved.append(
                {
                    "room_type": rt,
                    "room": room,
                    "floor": floor,
                    "quantity": raw["quantity"],
                    "adults": raw.get("adults"),
                    "children": raw.get("children"),
                    "notes": raw.get("notes", ""),
                }
            )
        return resolved

    def _resolve_floor(self, floor_id, hotel):
        """Validate an optional floor preference (RESERVATIONS-AUTO-ROOM)."""
        if not floor_id:
            return None
        floor = Floor.objects.filter(pk=floor_id).first()
        if floor is None:
            raise serializers.ValidationError(
                {"lines": "The referenced floor does not exist."}
            )
        if floor.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "floor"})
        return floor

    def _resolve_room(self, room_id, room_type, quantity, hotel):
        """Validate an optional specific room assignment (Phase 6.1)."""
        if not room_id:
            return None
        room = Room.objects.filter(pk=room_id).first()
        if room is None:
            raise serializers.ValidationError({"lines": "The assigned room does not exist."})
        if room.hotel_id != hotel.id:
            raise CrossTenantReference({"field": "room"})
        if room.room_type_id != room_type.id:
            raise serializers.ValidationError(
                {"lines": "The assigned room does not match the room type."}
            )
        if not room.is_active or room.status in _NON_ASSIGNABLE_ROOM_STATUSES:
            raise serializers.ValidationError(
                {"lines": f"Room {room.number} is not assignable."}
            )
        if quantity != 1:
            raise serializers.ValidationError(
                {"lines": "A line with an assigned room must have quantity 1."}
            )
        return room

    def validate(self, attrs):
        creating = self.instance is None
        check_in = attrs.get(
            "check_in_date", getattr(self.instance, "check_in_date", None)
        )
        check_out = attrs.get(
            "check_out_date", getattr(self.instance, "check_out_date", None)
        )
        if check_in and check_out and check_in >= check_out:
            raise serializers.ValidationError(
                {"check_out_date": "Check-out must be after check-in."}
            )

        # Phase 8.1 — the only two booking kinds are instant/future. When the
        # caller does not send one, derive it from the check-in date.
        booking_kind = attrs.get(
            "booking_kind", getattr(self.instance, "booking_kind", "")
        )
        if not booking_kind and check_in:
            booking_kind = (
                BookingKind.INSTANT
                if check_in <= timezone.localdate()
                else BookingKind.FUTURE
            )
            attrs["booking_kind"] = booking_kind
        if (
            booking_kind == BookingKind.INSTANT
            and check_in
            and check_in > timezone.localdate()
        ):
            raise serializers.ValidationError(
                {"booking_kind": "An instant booking must start today."}
            )

        status = attrs.get("status", getattr(self.instance, "status", None))
        if status == ReservationStatus.HELD:
            hold_expires = attrs.get(
                "hold_expires_at", getattr(self.instance, "hold_expires_at", None)
            )
            if hold_expires is None:
                raise serializers.ValidationError(
                    {"hold_expires_at": "A hold expiry time is required for held reservations."}
                )

        # RESERVATIONS-FORM-REWORK: resolve the optional primary-guest link and
        # any adult companions against THIS hotel, then keep the ``adults`` count
        # consistent (1 primary + named adult companions) so the capacity rule
        # below and downstream stay correct.
        if "primary_guest" in attrs:
            attrs["primary_guest"] = self._resolve_guest(
                attrs.get("primary_guest"), field="primary_guest"
            )
        raw_occupants = attrs.get("occupants")
        if raw_occupants is not None:
            resolved_occ = []
            for occ in raw_occupants:
                occ = dict(occ)
                occ["guest"] = self._resolve_guest(
                    occ.get("guest"), field="occupants"
                )
                resolved_occ.append(occ)
            attrs["occupants"] = resolved_occ
            # 1 primary + the named adult companions.
            attrs["adults"] = 1 + len(resolved_occ)

        raw_lines = attrs.get("lines")
        if creating and not raw_lines:
            raise serializers.ValidationError(
                {"lines": "At least one room line is required."}
            )
        if raw_lines is not None:
            mode = attrs.get("room_assignment_mode")
            resolved = self._resolve_lines(raw_lines, mode=mode)
            attrs["lines"] = resolved
            self._validate_capacity(attrs, resolved)
        return attrs

    def _resolve_guest(self, guest_id, *, field):
        """Resolve an optional guest id to a hotel-scoped ``Guest`` (or None)."""
        if not guest_id:
            return None
        hotel = self.context["request"].hotel
        guest = Guest.objects.filter(pk=guest_id).first()
        if guest is None:
            raise serializers.ValidationError(
                {field: "The referenced guest does not exist."}
            )
        if guest.hotel_id != hotel.id:
            raise CrossTenantReference({"field": field})
        return guest

    def _validate_capacity(self, attrs, resolved):
        adults = attrs.get("adults", getattr(self.instance, "adults", 1) or 1)
        children = attrs.get("children", getattr(self.instance, "children", 0) or 0)
        total_guests = adults + children
        capacity = sum(
            line["quantity"] * line["room_type"].max_capacity for line in resolved
        )
        if total_guests > capacity:
            raise serializers.ValidationError(
                {
                    "adults": (
                        "Total guests exceed the maximum capacity of the "
                        "selected rooms."
                    )
                }
            )


class AvailabilityQuerySerializer(serializers.Serializer):
    check_in_date = serializers.DateField()
    check_out_date = serializers.DateField()
    room_type = serializers.IntegerField(required=False)
    adults = serializers.IntegerField(min_value=0, required=False)
    children = serializers.IntegerField(min_value=0, required=False)

    def validate(self, attrs):
        if attrs["check_in_date"] >= attrs["check_out_date"]:
            raise serializers.ValidationError(
                {"check_out_date": "Check-out must be after check-in."}
            )
        return attrs


class TypeAvailabilitySerializer(serializers.Serializer):
    """Serializes a :class:`TypeAvailability` dataclass result."""

    def to_representation(self, instance: TypeAvailability) -> dict:
        return instance.as_dict()


class RoomAvailabilityQuerySerializer(serializers.Serializer):
    """Query params for the per-room availability endpoint."""

    check_in = serializers.DateField()
    check_out = serializers.DateField()
    floor = serializers.IntegerField(required=False)
    room_type = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if attrs["check_in"] >= attrs["check_out"]:
            raise serializers.ValidationError(
                {"check_out": "Check-out must be after check-in."}
            )
        return attrs


class CancelReservationSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("A cancellation reason is required.")
        return value.strip()


class ReserveNumberSerializer(serializers.Serializer):
    """Request body for the reserve-number endpoint (Round 3 §7.3).

    ``idempotency_key`` is a client-generated token (a fresh UUID per form-open).
    Replaying the same key returns the SAME reserved number (idempotent).
    """

    idempotency_key = serializers.CharField(max_length=64)

    def validate_idempotency_key(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("An idempotency key is required.")
        return value


class ReservationStatusLogSerializer(serializers.Serializer):
    previous_status = serializers.CharField()
    new_status = serializers.CharField()
    note = serializers.CharField()
    changed_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_changed_by(self, obj):
        return obj.changed_by.email if obj.changed_by_id else None


class ReservationDepositSerializer(serializers.Serializer):
    """Pre-arrival DEPOSIT payload for a future/held/confirmed reservation (§27).

    Mirrors ``stays.ImmediateDepositSerializer`` exactly (same fields + FX rules):
    the base ``amount`` is in the reservation/base currency; a foreign-currency
    deposit instead supplies ``original_amount`` + ``exchange_rate`` (+ optional
    ``rate_basis``) and the finance service DERIVES the base amount (single ledger).
    A zero/negative tender is rejected (no zero payment). The recorded Payment goes
    through ``record_reservation_payment`` onto the reservation's ONE folio, which
    is reused at check-in — no duplicate ledger.
    """

    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    method = serializers.CharField(max_length=32)
    currency = serializers.CharField(
        max_length=3, required=False, allow_blank=True, default=""
    )
    original_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    exchange_rate = serializers.DecimalField(
        max_digits=18, decimal_places=8, required=False, allow_null=True
    )
    rate_basis = serializers.CharField(
        max_length=32, required=False, allow_blank=True, default=""
    )
    payer_name = serializers.CharField(
        max_length=180, required=False, allow_blank=True, default=""
    )
    reference = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_method(self, value):
        from apps.finance.models import PaymentMethod

        if value not in {code for code, _ in PaymentMethod.choices}:
            raise serializers.ValidationError("Unsupported payment method.")
        return value

    def validate_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value

    def validate_original_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Amount must be positive.")
        return value

    def validate(self, attrs):
        if attrs.get("amount") is None and attrs.get("original_amount") is None:
            raise serializers.ValidationError(
                "Provide an amount (or original_amount for a foreign-currency "
                "deposit)."
            )
        return attrs
