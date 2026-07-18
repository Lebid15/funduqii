"""DRF serializers for guests (Phase 7 + final closure).

Hotel scoping is enforced by the views (queryset + ``hotel=request.hotel`` on
save). Field formats and per-hotel document uniqueness are validated here.

Sensitive data: the document number is MASKED at this API layer for callers
without ``guests.view_sensitive_data`` — hiding it in the frontend alone is
not protection. VIP/block flags are read-only here; they change only through
the dedicated service endpoints.
"""
from __future__ import annotations

import re

from django.urls import reverse

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from apps.notifications.models import ActivityEvent
from apps.reservations.models import Reservation, ReservationDocument
from apps.stays.models import Stay, StayStatus

from .models import DocumentType, Guest
from .normalize import PhoneNormalizationError, canonical_phone, normalize_id
from .services import mask_document

_PHONE_RE = re.compile(r"^[0-9+\-\s()]{4,32}$")


def can_view_sensitive(request) -> bool:
    from apps.rbac.services import has_hotel_permission

    user = getattr(request, "user", None)
    hotel = getattr(request, "hotel", None)
    if user is None or hotel is None:
        return False
    return has_hotel_permission(user, hotel, "guests.view_sensitive_data")


class GuestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guest
        fields = [
            "id",
            "full_name",
            "first_name",
            "last_name",
            "father_name",
            "mother_name",
            "phone",
            "email",
            "no_email",
            "nationality",
            "national_id",
            "document_type",
            "document_number",
            "date_of_birth",
            "gender",
            "address",
            "notes",
            "is_active",
            "is_vip",
            "is_blocked",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_vip", "is_blocked", "created_at", "updated_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        # Fail CLOSED: mask when there is NO request context OR the caller lacks
        # ``guests.view_sensitive_data``. A missing request can never be treated
        # as authorized (``can_view_sensitive(None)`` is False anyway) — this
        # matches the reservations serializers and prevents leaking the raw
        # ``national_id`` / ``document_number`` when a serializer is used out of
        # a request cycle.
        if request is None or not can_view_sensitive(request):
            # The generic document number AND the structured national ID are
            # both sensitive — mask both for callers without the permission.
            data["document_number"] = mask_document(instance.document_number)
            data["national_id"] = mask_document(instance.national_id)
        return data

    def validate_full_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("A guest name is required.")
        return value.strip()

    def validate_phone(self, value):
        if value and not _PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def validate_document_number(self, value):
        # A masked value must never round-trip back into the profile.
        if value and "•" in value:
            raise serializers.ValidationError(
                "Enter the real document number (masked values are rejected)."
            )
        return (value or "").strip()

    def validate_national_id(self, value):
        # A masked value must never round-trip back into the profile.
        if value and "•" in value:
            raise serializers.ValidationError(
                "Enter the real national ID (masked values are rejected)."
            )
        return (value or "").strip()

    def validate(self, attrs):
        hotel = self.context["request"].hotel
        doc_type = attrs.get(
            "document_type", getattr(self.instance, "document_type", "")
        )
        doc_number = attrs.get(
            "document_number", getattr(self.instance, "document_number", "")
        )
        # Decision 3: the national ID is a first-class field (``Guest.national_id``)
        # and the central identity service keys the ban/dedup on it. It must NEVER
        # be smuggled in as a generic document, so reject ``document_type =
        # 'national_id'`` outright. Passport stays a normal document.
        if doc_type == DocumentType.NATIONAL_ID:
            raise serializers.ValidationError(
                {
                    "document_type": [
                        ErrorDetail(
                            "A national ID must be stored in the national_id "
                            "field, not as a document.",
                            code="national_id_must_use_national_id_field",
                        )
                    ]
                }
            )
        # Decision 1: an edited phone is stored CANONICAL E.164 so the stored key
        # and every lookup key stay identical. An uninterpretable phone (or a
        # local number with no resolvable hotel country) is a clean 400 — it is
        # never persisted as-typed / approximately. Only runs when phone is part
        # of this write (a PATCH that omits phone leaves it untouched).
        if "phone" in attrs:
            default_country = (
                getattr(getattr(hotel, "settings", None), "default_phone_country", "")
                or None
            )
            try:
                attrs["phone"] = canonical_phone(
                    (attrs.get("phone") or "").strip(),
                    default_country=default_country,
                )
            except PhoneNormalizationError:
                raise serializers.ValidationError(
                    {
                        "phone": [
                            ErrorDetail(
                                "This phone number could not be interpreted; "
                                "enter it in international +country form.",
                                code="invalid_phone",
                            )
                        ]
                    }
                )
        if doc_number:
            qs = Guest.objects.filter(
                hotel=hotel, document_type=doc_type, document_number=doc_number
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"document_number": "A guest with this document already exists."}
                )
        # Mirror the DB partial constraint (unique_guest_national_id_per_hotel),
        # which is enforced on the NORMALIZED value, so a duplicate national ID
        # returns a clean 400, not a raw IntegrityError. Two differently-typed
        # IDs ("1234-5678" / "12345678") normalize to the same key and collide.
        national_id = attrs.get(
            "national_id", getattr(self.instance, "national_id", "")
        )
        national_id_normalized = normalize_id(national_id)
        if national_id_normalized:
            qs = Guest.objects.filter(
                hotel=hotel, national_id_normalized=national_id_normalized
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"national_id": "A guest with this national ID already exists."}
                )
        return attrs


class GuestBlockSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class GuestUnblockSerializer(serializers.Serializer):
    note = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )


class GuestVipSerializer(serializers.Serializer):
    vip = serializers.BooleanField()


# --------------------------------------------------------------------------- #
# GAP-1 read-only profile sub-resources (paginated)                           #
# EXEC-GUESTS-CLOSURE-01 / W3b — Decision 11. Every one of these is READ-ONLY  #
# and paginated by the common ``DefaultPagination``; hotel scoping + the       #
# other-hotel 404 are enforced by the views, and the sensitive fields reuse    #
# the SAME masking gate as the rest of the guests section (fail-closed).       #
# --------------------------------------------------------------------------- #


def _select_primary_folio(folios):
    """Pick the folio to surface for a stay row — mirrors
    ``GuestProfileView._folio_of``: an OPEN folio wins, then the highest id.

    ``folios`` is an ALREADY-PREFETCHED iterable, so this never issues a query
    per row (the view prefetches ``folios``).
    """
    ordered = sorted(folios, key=lambda f: (f.status != "open", -f.id))
    return ordered[0] if ordered else None


class GuestStayHistorySerializer(serializers.ModelSerializer):
    """One row of a guest's stay history (read-only, newest-first by the view).

    Only OPERATIONAL view-links are exposed (stay / reservation / folio
    identifiers). No monetary value is returned here — folio *money* stays gated
    behind ``finance.view`` elsewhere and is deliberately out of this read wave.
    """

    stay_id = serializers.IntegerField(source="id", read_only=True)
    check_in_date = serializers.DateField(
        source="planned_check_in_date", read_only=True
    )
    check_out_date = serializers.DateField(
        source="planned_check_out_date", read_only=True
    )
    nights = serializers.IntegerField(read_only=True)
    is_checked_out = serializers.SerializerMethodField()
    room_number = serializers.CharField(source="room.number", read_only=True)
    room_type_name = serializers.CharField(
        source="room.room_type.name", read_only=True
    )
    reservation_number = serializers.SerializerMethodField()
    folio = serializers.SerializerMethodField()

    class Meta:
        model = Stay
        fields = [
            "stay_id",
            "status",
            "is_checked_out",
            "check_in_date",
            "check_out_date",
            "actual_check_out_at",
            "nights",
            "room_number",
            "room_type_name",
            "reservation_id",
            "reservation_number",
            "folio",
        ]
        read_only_fields = fields

    def get_is_checked_out(self, obj) -> bool:
        return obj.status == StayStatus.CHECKED_OUT

    def get_reservation_number(self, obj):
        return obj.reservation.reservation_number if obj.reservation_id else None

    def get_folio(self, obj):
        folio = _select_primary_folio(list(obj.folios.all()))
        if folio is None:
            return None
        # Identifiers only — a view-link, never money.
        return {
            "id": folio.id,
            "folio_number": folio.folio_number,
            "status": folio.status,
        }


class GuestReservationHistorySerializer(serializers.ModelSerializer):
    """One row of a guest's reservation history (bookings the guest holds as the
    primary guest). Read-only; no snapshot PII beyond the identifiers/dates."""

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
        ]
        read_only_fields = fields


class GuestDocumentSerializer(serializers.ModelSerializer):
    """A guest identity document — resolved from the EXISTING
    ``ReservationDocument`` mechanism (see ``GuestDocumentsView``).

    The ``number`` is masked exactly like every other guests document number
    (``guests.view_sensitive_data``, fail-closed). The image bytes are NEVER
    embedded: ``front_url`` / ``back_url`` point at the EXISTING signed-URL mint
    endpoint (``reservations:reservation-document-signed-url``), which is itself
    behind ``reservation_documents.view`` and returns a short-lived, token-bound
    stream URL. No new signed-URL / file service is introduced here.

    SEC (document image needs sensitive permission): opening / downloading /
    streaming the ORIGINAL document image is more sensitive than listing a masked
    number, so ``front_url`` / ``back_url`` — the only path to the image mint — are
    returned ONLY when the caller ALSO holds ``guests.view_sensitive_data`` (on top
    of the endpoint's ``guests.view`` + ``reservation_documents.view``). Without it
    the URLs are ``null`` (never minted) and the row carries only the type + masked
    number. This is enforced server-side (the URL is absent from the response), not
    by hiding a frontend button; ``has_front`` / ``has_back`` remain truthful
    existence flags but do not lead to the image.
    """

    has_front = serializers.SerializerMethodField()
    has_back = serializers.SerializerMethodField()
    front_url = serializers.SerializerMethodField()
    back_url = serializers.SerializerMethodField()
    # The reused reservation-document mechanism does NOT capture a document
    # expiry date, so this is always ``null``. Kept in the contract for a stable
    # frontend shape; see the handoff report (owner decision to add an expiry
    # field belongs to a future write-path wave, not this read-only one).
    expiry_date = serializers.SerializerMethodField()

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
            "expiry_date",
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
        # SEC (document image needs sensitive permission): the image mint is
        # returned only to a caller holding ``guests.view_sensitive_data``.
        # Fail CLOSED — a missing request context is never authorized. Without
        # the permission the URL is absent (null); the image bytes are unreachable
        # server-side, not merely hidden in the UI.
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

    def get_expiry_date(self, obj):
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        # Fail CLOSED: mask the identity number without a request context OR
        # without ``guests.view_sensitive_data`` (same rule as the reservation
        # document read serializer and the guest profile).
        if request is None or not can_view_sensitive(request):
            data["number"] = mask_document(instance.number)
        return data


# Guest audit events whose ``message`` carries security-gated content: the block
# reason (``guest.blocked``) and the unblock note (``guest.unblocked``) live in
# the same block/unblock security history as ``Guest.block_reason``. Their
# message stays hidden unless the caller holds ``guests.block`` — mirrors the
# profile's ``block_reason`` gating, fail-closed. Every OTHER event keeps its
# message (identity values there are already masked at record time).
_BLOCK_GATED_EVENT_TYPES = ("guest.blocked", "guest.unblocked")


class GuestChangeLogSerializer(serializers.ModelSerializer):
    """One row of a guest's change-log / audit history, read from the existing
    activity store (``ActivityEvent``). Read-only."""

    actor = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()

    class Meta:
        model = ActivityEvent
        fields = [
            "id",
            "event_number",
            "event_type",
            "category",
            "severity",
            "title",
            "message",
            "actor",
            "occurred_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor(self, obj):
        return obj.actor.email if obj.actor_id else None

    def get_message(self, obj):
        if obj.event_type in _BLOCK_GATED_EVENT_TYPES and not self.context.get(
            "can_see_block_reason"
        ):
            return None
        return obj.message
