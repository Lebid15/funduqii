"""Reservation lifecycle services (Phase 6).

Every state change that can affect inventory (create, update dates/lines,
confirm, hold) runs inside a transaction and re-checks availability through the
central :class:`~apps.reservations.availability.AvailabilityService` so the
backend — never the frontend — is the source of truth against overbooking.

No guest profile, payment, folio, invoice, or check-in/out is created here.
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import BigIntegerField
from django.db.models.functions import Cast, Substr
from django.utils import timezone

from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.common.exceptions import (
    CancellationReasonRequired,
    IdempotencyKeyConflict,
    InvalidReservationTransition,
    NoShowReasonRequired,
    NoAvailability,
    PermissionDenied,
    ReservationHasActiveStay,
    ReservationKeyAlreadyUsed,
    RoomAssignmentConflict,
)

from .availability import AvailabilityService
from .models import (
    Reservation,
    ReservationDraft,
    ReservationDraftStatus,
    ReservationNumberSequence,
    ReservationOccupant,
    ReservationRoomLine,
    ReservationStatus,
    ReservationStatusLog,
)

# Structured snapshot fields on Reservation mapped to their Guest source field.
# Used to freeze a faithful snapshot at booking time from a linked guest.
_PRIMARY_GUEST_SNAPSHOT_MAP = {
    "primary_guest_first_name": "first_name",
    "primary_guest_last_name": "last_name",
    "primary_guest_father_name": "father_name",
    "primary_guest_mother_name": "mother_name",
    "primary_guest_national_id": "national_id",
}

_NUMBER_PREFIX = "R"

# Round 3 §7.3 — a reserved reservation number (its ``ReservationDraft``) is valid
# for this long. After it lapses a cleanup job may mark the draft ``expired``; the
# NUMBER itself is never reused (an expired draft leaves a gap). 30 minutes is a
# sensible default for filling in a booking form.
RESERVATION_DRAFT_TTL = timedelta(minutes=30)


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


def _max_existing_number(hotel) -> int:
    """The current MAX valid ``R#####`` sequence value for a hotel (``0`` if none).

    ITEM 9 (PG-safe): matches EXACTLY ``^R[0-9]+$`` before the ``Substr``/``Cast``
    so an imported / historical value like ``RB00001`` (or an empty / corrupt
    number) is IGNORED — not modified, not deleted. On PostgreSQL, casting the tail
    of a non-numeric value (e.g. ``B00001``) to integer raises; the regex pre-filter
    guarantees only digit tails ever reach the cast. ``BigIntegerField`` avoids a PG
    overflow on a matching-but-huge tail (e.g. ``R3000000000`` > 2^31-1).
    """
    last = (
        Reservation.objects.filter(
            hotel=hotel, reservation_number__regex=r"^R[0-9]+$"
        )
        .annotate(
            seq=Cast(Substr("reservation_number", 2), output_field=BigIntegerField())
        )
        .order_by("-seq")
        .values_list("seq", flat=True)
        .first()
    )
    return int(last or 0)


def next_reservation_number(hotel) -> str:
    """Allocate the next per-hotel reservation number (e.g. ``R00001``).

    Round 3 §7.3 — this is now the SOLE allocator. It locks the hotel's
    :class:`~apps.reservations.models.ReservationNumberSequence` row with
    ``select_for_update`` so two concurrent allocations can never collide (the same
    blessed pattern as :func:`apps.finance.services.next_number`). MUST run inside a
    transaction.

    On the FIRST allocation for a hotel the counter SEEDS from the current max
    valid reservation number (ignoring non ``^R[0-9]+$`` values), so it continues
    seamlessly from the existing ``R#####`` max — imported/corrupt prefixes are
    left untouched and per-hotel independence is preserved.
    """
    seq, created = ReservationNumberSequence.objects.select_for_update().get_or_create(
        hotel=hotel
    )
    if created:
        # Seed lazily from the existing max so the counter continues from it (no
        # data migration/backfill needed). Only raises the counter, never lowers.
        seed = _max_existing_number(hotel)
        if seed > seq.last_number:
            seq.last_number = seed
    seq.last_number += 1
    seq.save(update_fields=["last_number", "updated_at"])
    return f"{_NUMBER_PREFIX}{seq.last_number:05d}"


def _next_reservation_number(hotel) -> str:
    """Backward-compatible alias for the locked-counter allocator.

    Kept so existing internal call sites / tests keep working; delegates entirely
    to :func:`next_reservation_number` (the MAX+1 body has been removed — the
    counter is authoritative). MUST run inside a transaction.
    """
    return next_reservation_number(hotel)


@transaction.atomic
def reserve_reservation_number(hotel, *, idempotency_key, user=None) -> ReservationDraft:
    """Reserve a REAL reservation number when the booking form opens (Round 3 §7.3).

    Idempotent per ``(hotel, idempotency_key)`` ONLY while the draft is still OPEN
    and within TTL: that draft is returned unchanged (same number). A FIRST-time key
    allocates a fresh number from the locked counter and creates an OPEN draft.

    TERMINAL-DRAFT RULE (owner semantics): a draft that has reached a terminal or
    expired outcome — ``consumed`` / ``expired`` / ``cancelled``, or ``open`` but
    PAST its ``expires_at`` — is NEVER re-opened, re-numbered, or recycled, and its
    number / reservation link / status are never mutated. Re-opening a terminal
    draft would blur the boundary between a finished operation and a new one (and
    could later return a historical reservation under a "fresh" number). Instead the
    spent key raises :class:`ReservationKeyAlreadyUsed` (HTTP 409); the client opens
    a new form (a new UUID) to reserve again. The old number stays a permanent gap
    (never reused).

    There are NO side effects — no folio, payment, availability, or inventory is
    touched. The draft is hotel-scoped: a key from another hotel never matches here
    (tenant isolation).

    Concurrency: a REPLAY of an OPEN+valid key locks that row with
    ``select_for_update`` and returns it unchanged. On the FIRST-time concurrent case
    there is NO row to lock yet, so two same-key reserves can both miss the lookup,
    both allocate a number, and both attempt the insert; the unique
    ``(hotel, idempotency_key)`` constraint lets exactly ONE draft persist and the
    loser catches the ``IntegrityError`` and RE-FETCHES the winner — returning it if
    OPEN+valid (idempotent), else raising ``ReservationKeyAlreadyUsed``. The loser's
    already-allocated number becomes a permanent gap. Runs inside a transaction.
    """
    key = (idempotency_key or "").strip()
    if not key:
        raise DRFValidationError({"idempotency_key": "An idempotency key is required."})

    now = timezone.now()
    draft = (
        ReservationDraft.objects.select_for_update()
        .filter(hotel=hotel, idempotency_key=key)
        .first()
    )
    if draft is not None:
        # Idempotent replay ONLY while OPEN and within TTL -> the SAME reserved number.
        if draft.status == ReservationDraftStatus.OPEN and draft.expires_at > now:
            return draft
        # Terminal / expired outcome: the key is SPENT. Never re-open, re-number, or
        # recycle it, and never touch its link/status/audit — reserve again with a
        # fresh key.
        raise ReservationKeyAlreadyUsed()

    # First-time insert for this key. Two SAME-key reserves can BOTH reach here: the
    # ``select_for_update`` above locks nothing when no row exists yet, so both
    # allocate a number and both attempt the insert. The unique ``(hotel,
    # idempotency_key)`` constraint lets only ONE row land; the loser catches the
    # ``IntegrityError`` and RE-FETCHES the winner. The nested ``atomic`` is a
    # SAVEPOINT so the collision rolls back ONLY this insert and leaves the outer
    # transaction usable (required on PostgreSQL) — the guard ``finance`` uses too.
    number = next_reservation_number(hotel)
    expires_at = now + RESERVATION_DRAFT_TTL
    try:
        with transaction.atomic():
            return ReservationDraft.objects.create(
                hotel=hotel,
                reservation_number=number,
                idempotency_key=key,
                created_by=_actor(user),
                status=ReservationDraftStatus.OPEN,
                expires_at=expires_at,
            )
    except IntegrityError:
        # The winner's row now exists. Return it only if OPEN+valid (idempotent
        # first-time race); a spent winner means the key is already used.
        existing = (
            ReservationDraft.objects.filter(hotel=hotel, idempotency_key=key).first()
        )
        if (
            existing is not None
            and existing.status == ReservationDraftStatus.OPEN
            and existing.expires_at > now
        ):
            return existing
        if existing is not None:
            raise ReservationKeyAlreadyUsed()
        raise


def expire_stale_reservation_drafts(*, hotel_id: int | None = None) -> int:
    """Mark every OPEN reservation draft past its TTL as ``expired`` (Round 3 §7.3).

    Shared cleanup core called by BOTH the ``cleanup_reservation_drafts`` management
    command and the ``reservations.cleanup_reservation_drafts`` Celery task. It is a
    pure, idempotent state transition with NO data loss and NO side effects: no draft
    is deleted, no Reservation/folio/payment/availability row is touched, and the
    reserved NUMBER is never reused (an expired draft simply leaves a gap in the
    per-hotel monotonic sequence — the counter is authoritative). Uses a
    timezone-aware ``now()``.

    Runs across ALL hotels by default; the filter is status + expiry only, so it is
    tenant-isolation-safe. Pass ``hotel_id`` to limit the sweep to a single hotel.

    Returns the number of drafts transitioned to ``expired`` (``0`` on a second run).
    """
    qs = ReservationDraft.objects.filter(
        status=ReservationDraftStatus.OPEN,
        expires_at__lte=timezone.now(),
    )
    if hotel_id is not None:
        qs = qs.filter(hotel_id=hotel_id)
    return qs.update(status=ReservationDraftStatus.EXPIRED)


def _canonicalize(value):
    """Canonical, format-stable representation of a value for fingerprinting.

    Normalizes Decimals (fixed notation — ``50``, ``50.00`` and ``50.0`` all
    collapse to the same string), dates/times (ISO), model instances (``pk:<id>``)
    and strips strings. ``None`` is preserved DISTINCT from ``""`` so a materially
    absent value never collides with an empty one. Lists/dicts recurse; dict keys
    are sorted at dump time, so client JSON key order never affects the digest.
    """
    import datetime
    from decimal import Decimal

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _canonicalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    if hasattr(value, "pk"):
        return f"pk:{value.pk}"
    if isinstance(value, str):
        return value.strip()
    return value


def _decimal_or_none(value):
    """Coerce a money-ish value to a ``Decimal`` (so ``"50.00"`` and ``50`` match),
    or ``None`` when absent. Falls back to the stripped string if unparseable."""
    from decimal import Decimal, InvalidOperation

    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value).strip()


def _creation_fingerprint(
    *,
    operation,
    lines,
    status,
    fields,
    occupants=None,
    room_assignment_mode=None,
    extra=None,
) -> str:
    """A stable SHA-256 fingerprint of the WHOLE material operation (S6 remediation).

    It represents everything that changes the resulting records or their financial
    / operational side effects, so a replayed ``idempotency_key`` carrying a
    materially different request is rejected (409) rather than silently returning
    the original:

    * OPERATION SCOPE — so a key cannot cross between a plain reservation create and
      an immediate check-in and be replayed as the other.
    * WHAT is booked — dates, arrival, kind, source, per-line (room type + quantity
      + pinned room + agreed-rate override + reason), and the room-assignment mode.
    * HOW MANY — adults/children + named occupant identities.
    * FOR WHOM — the full guest-identity snapshot (hashed).
    * EXTRA path-specific inputs — e.g. the deposit (amount/currency/method/FX) and
      the immediate check-in room + line, supplied by the orchestration.

    Non-material UI values (language, ordering, CSRF, transient UI) are never
    included. Canonical: server-built dict, ``sort_keys`` at dump time, sorted
    lists, normalized Decimals/dates/PKs, and ``None`` kept distinct from ``""`` —
    so client JSON key order never matters and a genuine retry always matches. The
    guest identity and the whole payload are hashed, so NO raw PII is stored.
    """
    line_entries = [
        {
            "room_type": _canonicalize(line.get("room_type")),
            "quantity": int(line.get("quantity") or 1),
            "room": _canonicalize(line.get("room")),
            "rate": _canonicalize(_decimal_or_none(line.get("agreed_nightly_rate"))),
            "rate_reason": (line.get("rate_override_reason") or "").strip(),
        }
        for line in (lines or [])
    ]
    # Sort by a canonical string so line order from the client is irrelevant and
    # mixed None/str values never raise on comparison.
    line_sig = sorted(
        line_entries, key=lambda e: json.dumps(e, sort_keys=True, default=str)
    )
    occupant_sig = sorted(
        "|".join(
            [
                (occ.get("first_name") or "").strip().casefold(),
                (occ.get("last_name") or "").strip().casefold(),
                (occ.get("national_id") or "").strip(),
            ]
        )
        for occ in (occupants or [])
    )
    # Guest identity uses the STABLE snapshot fields, NOT any linked ``Guest`` PK —
    # the immediate-check-in path creates a fresh Guest from the same snapshot on
    # each call, so a PK would make an identical replay look "different" and
    # wrongly 409.
    guest_identity = "|".join(
        [
            (fields.get("primary_guest_name") or "").strip().casefold(),
            (fields.get("primary_guest_first_name") or "").strip().casefold(),
            (fields.get("primary_guest_last_name") or "").strip().casefold(),
            (fields.get("primary_guest_father_name") or "").strip().casefold(),
            (fields.get("primary_guest_mother_name") or "").strip().casefold(),
            (fields.get("primary_guest_document_type") or "").strip(),
            (fields.get("primary_guest_document_number") or "").strip(),
            (fields.get("primary_guest_national_id") or "").strip(),
            (fields.get("primary_guest_phone") or "").strip(),
            (fields.get("primary_guest_email") or "").strip().casefold(),
            (fields.get("primary_guest_nationality") or "").strip(),
        ]
    )
    payload = {
        "operation": _canonicalize(operation),
        "status": _canonicalize(status),
        "booking_kind": _canonicalize(fields.get("booking_kind")),
        "source": _canonicalize(fields.get("source")),
        "check_in": _canonicalize(fields.get("check_in_date")),
        "check_out": _canonicalize(fields.get("check_out_date")),
        "arrival": _canonicalize(fields.get("expected_arrival_time")),
        "adults": _canonicalize(fields.get("adults")),
        "children": _canonicalize(fields.get("children")),
        "room_assignment_mode": _canonicalize(room_assignment_mode),
        "lines": line_sig,
        "occupants": occupant_sig,
        "guest": hashlib.sha256(guest_identity.encode("utf-8")).hexdigest(),
        "extra": _canonicalize(extra or {}),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_same_creation_request(reservation, fingerprint: str) -> None:
    """Reject a replayed key whose payload fingerprint differs from the stored one.

    A stored/incoming empty fingerprint is treated as "unknown" and never
    conflicts (backward compatible with pre-remediation rows)."""
    stored = reservation.creation_request_fingerprint or ""
    if stored and fingerprint and stored != fingerprint:
        raise IdempotencyKeyConflict()


def _log_status(reservation, previous, new, *, note="", user=None):
    actor = user if getattr(user, "is_authenticated", False) else None
    ReservationStatusLog.objects.create(
        hotel=reservation.hotel,
        reservation=reservation,
        previous_status=previous or "",
        new_status=new,
        note=note or "",
        changed_by=actor,
    )


def _hotel_default_currency(hotel) -> str:
    """The hotel's default currency (from HotelSettings) or ``USD`` — the SAME
    source ``finance`` uses for ``folio.currency`` and ``reservation_financials``."""
    settings_obj = getattr(hotel, "settings", None)
    return (getattr(settings_obj, "default_currency", "") or "") or "USD"


def _agreed_rate_snapshot(room_type, hotel):
    """Freeze the AGREED nightly rate + currency at BOOKING time.

    STAYS rate-integrity round — the rate is ``room_type.base_rate`` quantized via
    ``money()`` at THIS moment, an INDEPENDENT snapshot: a later catalog change to
    ``base_rate`` must NEVER alter it, so the hotel always bills the agreed price.
    Returns ``(None, currency)`` when the room type is unpriced (``base_rate`` NULL
    / <= 0) — an explicitly UNPRICED line, never a live-fallback signal. The
    currency is always the hotel default (captured at booking too).
    """
    from apps.finance.services import ZERO, money

    base = getattr(room_type, "base_rate", None)
    if base is None:
        rate = None
    else:
        rate = money(base)
        if rate <= ZERO:
            rate = None
    return rate, _hotel_default_currency(hotel)


def _line_snapshot_for_write(line, *, prior_line, hotel, user):
    """Resolve ``(agreed_nightly_rate, agreed_rate_currency)`` for a line being
    (re)created, per the STAYS rate-integrity snapshot policy (item 6):

    * a matching PRIOR line of the SAME RoomType -> PRESERVE its snapshot (a guest
      edit / date-only change / internal line re-create never re-prices);
    * a new / changed RoomType -> capture the new type's ``base_rate`` (confirm
      path);
    * an explicit ``agreed_nightly_rate`` that DIFFERS from that default -> an
      OVERRIDE: it requires ``stays.rate_override`` + a non-empty
      ``rate_override_reason`` and is audited.

    ``prior_line`` is the reservation's existing line of the same RoomType (or
    ``None`` on create / a genuine type change).
    """
    room_type = line["room_type"]
    if prior_line is not None and prior_line.room_type_id == room_type.id:
        default_rate = prior_line.agreed_nightly_rate
        default_currency = (
            prior_line.agreed_rate_currency or _hotel_default_currency(hotel)
        )
    else:
        default_rate, default_currency = _agreed_rate_snapshot(room_type, hotel)

    explicit = line.get("agreed_nightly_rate")
    if explicit is None:
        return default_rate, default_currency

    from apps.finance.services import money

    explicit_m = money(explicit)
    if default_rate is not None and explicit_m == money(default_rate):
        return default_rate, default_currency  # same value — not an override

    # OVERRIDE — a manual rate differing from the snapshot/confirm default.
    from apps.rbac.services import has_hotel_permission

    if not has_hotel_permission(user, hotel, "stays.rate_override"):
        raise PermissionDenied()
    reason = (line.get("rate_override_reason") or "").strip()
    if not reason:
        raise DRFValidationError(
            {"rate_override_reason": "A reason is required to override the agreed rate."}
        )
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type="reservation.rate_override",
        category="reservation",
        severity="warning",
        title="Agreed nightly rate override",
        message=f"{getattr(room_type, 'name', room_type.id)} @ {explicit_m} · {reason}",
        actor=user,
        related_url="/hotel/reservations",
    )
    return explicit_m, default_currency


def build_reservation_identity(source, *, guest_id=None) -> dict:
    """Build the central guest-identity mapping (input to
    :func:`apps.guests.identity.resolve_or_create_guest`) from a reservation's
    primary-guest SNAPSHOT.

    ``source`` is either the create-time ``fields`` dict or a ``Reservation``
    instance, so the SAME snapshot→identity mapping is used by
    :func:`create_reservation` (booking) and ``CheckInService`` (check-in derive).
    Only the ban-and-identity keys — national id, PASSPORT document number, and the
    raw phone (canonicalized strictly inside the service) — plus the profile fields
    are forwarded. A driving-license / 'other' document is deliberately NOT treated
    as a passport (Decision 4). ``guest_id`` (an explicit reuse target) is added
    only when provided.
    """
    get = (
        source.get
        if isinstance(source, dict)
        else (lambda key: getattr(source, key, None))
    )
    doc_type = (get("primary_guest_document_type") or "").strip()
    doc_number = (get("primary_guest_document_number") or "").strip()
    identity = {
        "national_id": (get("primary_guest_national_id") or ""),
        # Only a PASSPORT document number is an identity / ban key (Decision 4);
        # ``DocumentType.PASSPORT`` == "passport".
        "passport": doc_number if doc_type == "passport" else "",
        "phone": (get("primary_guest_phone") or ""),
        "full_name": (get("primary_guest_name") or ""),
        "first_name": (get("primary_guest_first_name") or ""),
        "last_name": (get("primary_guest_last_name") or ""),
        "father_name": (get("primary_guest_father_name") or ""),
        "mother_name": (get("primary_guest_mother_name") or ""),
        # ``Guest.nationality`` is max_length=80 while the snapshot allows 100 —
        # truncate to the Guest column width so a create can never overflow on
        # PostgreSQL (mirrors the previous _create_primary_guest behaviour).
        "nationality": (get("primary_guest_nationality") or "")[:80],
        "email": (get("primary_guest_email") or ""),
        "date_of_birth": get("primary_guest_date_of_birth"),
    }
    if guest_id is not None:
        identity["guest_id"] = guest_id
    return identity


@transaction.atomic
def create_reservation(
    hotel,
    *,
    lines,
    status,
    user,
    occupants=None,
    room_assignment_mode=None,
    idempotency_key=None,
    operation="reservation",
    idempotency_extra=None,
    allow_create=True,
    **fields,
) -> Reservation:
    """Create a reservation with its room lines after an availability check.

    ``lines`` is a list of dicts: ``{"room_type": <RoomType>, "quantity": int,
    "adults": int?, "children": int?, "notes": str?, "floor": <Floor|None>}``.
    ``status`` is ``held`` or ``confirmed`` (both consume inventory, so both are
    availability-checked).

    ``room_assignment_mode`` (RESERVATIONS-AUTO-ROOM) is REQUEST-ONLY (never
    persisted) and optional:

    * ``None`` (absent) — LEGACY behaviour, unchanged: each line keeps the room
      the caller provided (or ``None``). No automatic assignment happens.
    * ``"automatic"`` — the client CANNOT pin a room; the backend
      deterministically assigns a specific room to every ``quantity == 1`` line
      inside this transaction (after ``ensure_can_book`` has locked the type). If
      no room fits a line, the whole create fails with ``no_room_available`` — no
      partial reservation, never a room of the wrong floor/type.
    * ``"manual"`` — every line must pin a specific room; the room is validated
      (hotel + type + floor + bookable + available) and a same-room overlap
      raises ``room_assignment_conflict`` (the backend never silently swaps).

    ``occupants`` (RESERVATIONS-FORM-REWORK) is an OPTIONAL list of adult
    companions ``{"guest": <Guest|None>, "first_name": str, ..., "relationship":
    str}``; children remain a count on ``fields['children']``. Passing
    ``primary_guest`` (a ``Guest``) in ``fields`` links the reservation to the
    central directory and freezes a faithful structured snapshot from it. The
    call stays backward compatible: callers that pass neither still work.

    ``allow_create`` (Guests central identity — W3, Decision 15) governs how the
    primary guest is turned into a central ``Guest``:

    * ``True`` (default; authenticated console / wizard / instant paths) — the
      identity service reuses/creates + LINKS one canonical guest and runs the ban
      check on the normalized identity.
    * ``False`` (public website, Decision 10) — the ban check still runs, but NO
      central guest is created and none is linked: the reservation stays a pure
      snapshot and is linked later at operational confirm / check-in.
    """
    check_in = fields["check_in_date"]
    check_out = fields["check_out_date"]

    # --- S6 remediation: end-to-end idempotent creation --------------------
    # A client ``idempotency_key`` makes the WHOLE create idempotent. Lock the
    # draft for the key FIRST — it is the serialization point for concurrent
    # same-key creates: a second create BLOCKS here until the winner commits,
    # then sees the draft CONSUMED + linked and returns the SAME reservation
    # BEFORE any availability/capacity work. So a retry of a booking that already
    # succeeded returns the original reservation and never a misleading
    # ``no_availability``. The fingerprint (from the RAW payload, before the
    # mutations below) rejects reusing a key for a materially DIFFERENT request.
    creation_key = (idempotency_key or "").strip() or None
    creation_fingerprint = (
        _creation_fingerprint(
            operation=operation,
            lines=lines,
            status=status,
            fields=fields,
            occupants=occupants,
            room_assignment_mode=room_assignment_mode,
            extra=idempotency_extra,
        )
        if creation_key
        else ""
    )
    locked_draft = None
    if creation_key:
        locked_draft = (
            ReservationDraft.objects.select_for_update()
            .filter(hotel=hotel, idempotency_key=creation_key)
            .first()
        )
        replay = None
        if locked_draft is not None and locked_draft.reservation_id:
            replay = locked_draft.reservation
        if replay is None:
            replay = Reservation.objects.filter(
                hotel=hotel, creation_idempotency_key=creation_key
            ).first()
        if replay is not None:
            _assert_same_creation_request(replay, creation_fingerprint)
            replay._idempotent_replay = True
            return replay

    # Backend-authoritative capacity: total persons (1 primary + adult
    # companions + children) must fit the selected rooms' max_capacity.
    _enforce_capacity(lines, fields, occupants)

    # RESERVATIONS-AUTO-ROOM: manual mode requires each line to pin a specific
    # room (validated here, before locks) — a same-room overlap is caught by
    # ``ensure_can_book`` below. Automatic assignment happens after the locks.
    if room_assignment_mode == "manual":
        _validate_manual_assignment(lines)

    # DI-F4: when named companions are supplied, store ``adults`` authoritatively
    # as 1 primary + the companions so the persisted counter can never diverge
    # from the capacity that was actually enforced (a client cannot pass a
    # capacity-2 check while storing adults=5). No companions => legacy count.
    if occupants:
        fields["adults"] = 1 + len(occupants)

    # Freeze the structured snapshot from the linked guest (create only).
    _apply_primary_guest_snapshot(fields)

    if status in (ReservationStatus.HELD, ReservationStatus.CONFIRMED):
        AvailabilityService.ensure_can_book(
            hotel, _book_payload(lines), check_in, check_out
        )

    # Guests central identity (W3 integration, Decision 15). Turn the primary guest
    # into ONE canonical central Guest through the SINGLE identity service, AFTER the
    # idempotent-replay early return above (a replay creates NO new guest) and AFTER
    # the validation guards, BEFORE the reservation row is written. The service runs
    # the ban check on the NORMALIZED identity (national id + passport + canonical
    # phone) for EVERY case — an explicit linked guest (passed as ``guest_id``) or a
    # pure snapshot — closing the fresh-guest bypass that the old raw reservation-side
    # phone/document guard (now removed) left open. A GuestBlocked /
    # GuestIdentityConflict / invalid-phone raises INSIDE this atomic and rolls the
    # WHOLE reservation back with no side effects; a guest it creates is rolled back
    # too if a later step fails (same atomic). The creation fingerprint above stays
    # on the SNAPSHOT (never the guest PK), so idempotency is unchanged.
    from apps.guests.identity import resolve_or_create_guest

    explicit_guest = fields.get("primary_guest")
    resolved_guest = resolve_or_create_guest(
        hotel,
        identity=build_reservation_identity(
            fields,
            guest_id=explicit_guest.id if explicit_guest is not None else None,
        ),
        user=user,
        allow_create=allow_create,
    )
    # Link the central guest on the authenticated paths (allow_create=True). A public
    # submission (Decision 10, allow_create=False) never CREATES a guest and stays a
    # pure snapshot — it is linked later at operational confirm / check-in; the ban
    # check above still ran for it.
    if allow_create and resolved_guest is not None:
        fields["primary_guest"] = resolved_guest

    actor = _actor(user)
    # Round 3 §7.3 + S6 remediation — pin the PRE-RESERVED number by consuming the
    # OPEN, non-expired draft the form reserved on open (already locked above);
    # otherwise allocate a fresh number from the locked counter. An expired/spent
    # draft is NOT consumed and its number is never reused. The per-hotel
    # partial-unique on ``creation_idempotency_key`` (plus the existing
    # ``reservation_number`` unique) is the DB BACKSTOP: two concurrent same-key
    # creates that both slipped past the replay check both attempt the insert,
    # exactly ONE lands, and the loser RE-FETCHES the winner (idempotent — no 500,
    # no duplicate booking), the same resilience the reserve/finance inserts use.
    now = timezone.now()
    draft = (
        locked_draft
        if (
            locked_draft is not None
            and locked_draft.status == ReservationDraftStatus.OPEN
            and locked_draft.expires_at > now
        )
        else None
    )
    number = draft.reservation_number if draft is not None else next_reservation_number(hotel)
    try:
        with transaction.atomic():
            reservation = Reservation.objects.create(
                hotel=hotel,
                reservation_number=number,
                status=status,
                created_by=actor,
                updated_by=actor,
                creation_idempotency_key=creation_key,
                creation_request_fingerprint=creation_fingerprint,
                **fields,
            )
    except IntegrityError:
        # Lost the same-key race: the winner already created the reservation.
        # Return it (idempotent) instead of surfacing a 500 or a duplicate.
        if creation_key:
            winner = Reservation.objects.filter(
                hotel=hotel, creation_idempotency_key=creation_key
            ).first()
            if winner is not None:
                _assert_same_creation_request(winner, creation_fingerprint)
                winner._idempotent_replay = True
                return winner
        raise
    if draft is not None:
        draft.status = ReservationDraftStatus.CONSUMED
        draft.reservation = reservation
        draft.save(update_fields=["status", "reservation"])

    # RESERVATIONS-AUTO-ROOM: automatic assignment runs under the type locks
    # ``ensure_can_book`` already acquired, so a concurrent booking cannot pick
    # the same room. On no match the whole transaction rolls back (no partial
    # reservation). Absent/manual mode leaves ``line["room"]`` untouched.
    if room_assignment_mode == "automatic":
        _assign_rooms_automatically(
            hotel,
            lines,
            check_in,
            check_out,
            total_persons=_total_persons_create(fields, occupants),
        )

    for line in lines:
        # STAYS rate-integrity round: freeze the AGREED nightly rate + currency at
        # THIS instant (an independent snapshot — a later catalog change never
        # rewrites it). An explicit override rate is gated on ``stays.rate_override``
        # + a reason inside the helper.
        agreed_rate, agreed_currency = _line_snapshot_for_write(
            line, prior_line=None, hotel=hotel, user=user
        )
        ReservationRoomLine.objects.create(
            hotel=hotel,
            reservation=reservation,
            room_type=line["room_type"],
            room=line.get("room"),
            quantity=line["quantity"],
            adults=line.get("adults"),
            children=line.get("children"),
            notes=line.get("notes", ""),
            agreed_nightly_rate=agreed_rate,
            agreed_rate_currency=agreed_currency,
        )
    _create_occupants(hotel, reservation, occupants)
    _log_status(reservation, "", status, note="created", user=user)
    # Phase 14: activity + permission-matched notifications (lazy import to
    # keep app loading order simple).
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type="reservation.created",
        category="reservation",
        severity="success",
        title=f"Reservation {reservation.reservation_number} created",
        message=f"{reservation.primary_guest_name} · {check_in} → {check_out}",
        actor=user,
        related_object=reservation,
        related_url="/hotel/reservations",
    )
    return reservation


@transaction.atomic
def update_reservation(
    reservation,
    *,
    lines=None,
    status=None,
    user=None,
    occupants=None,
    room_assignment_mode=None,
    **fields,
):
    """Update a reservation, re-checking availability when inventory-affecting.

    Cancelled/expired reservations are terminal for inventory-affecting edits
    (only internal notes may change). Any change to dates or lines on a
    still-blocking reservation re-runs the availability check, excluding this
    reservation from the calculation so it does not conflict with itself.

    ``room_assignment_mode`` (RESERVATIONS-AUTO-ROOM §7) never auto-reassigns on
    a plain open/edit: rooms only change when the request explicitly REPLACES the
    lines (``lines is not None``) together with a mode. ``"automatic"`` picks
    fresh rooms for the new lines (client rooms discarded); ``"manual"`` requires
    and validates a pinned room per line; absent → legacy (the provided/``None``
    room is kept). The in-house / started-stay freeze still forbids any
    date/room change once a stay exists (guard below).

    ``occupants`` (RESERVATIONS-FORM-REWORK), when not ``None``, REPLACES the
    reservation's adult companions. Capacity is re-enforced whenever the room
    lines, occupants, or adult/child counts change. The structured snapshot is
    NOT rewritten on update — it stays frozen unless the caller sends the
    snapshot fields explicitly.
    """
    if reservation.status in (
        ReservationStatus.CANCELLED,
        ReservationStatus.EXPIRED,
        ReservationStatus.NO_SHOW,
    ) and (lines is not None or _touches_dates(fields)):
        raise InvalidReservationTransition(
            {"detail": "A cancelled, expired or no-show reservation cannot be re-booked."}
        )

    # Post-check-in guard (final closure + Finance-F1): once the reservation
    # has ANY stay — in-house OR already checked-out — the STAY is the source of
    # truth, so dates and room lines are frozen here; only safe, non-operational
    # fields (notes, requests, contact snapshot) may change. A checked-out
    # reservation is still CONFIRMED, so this broadened check (``has_any_stay``,
    # not ``has_in_house_stay``) also blocks re-shaping the inventory of a booking
    # whose guest has already departed. Operational changes travel through the
    # front desk (§33/§42 — the backend is the authoritative guard).
    if (lines is not None or _touches_dates(fields)) and has_any_stay(reservation):
        raise ReservationHasActiveStay(
            {
                "reservation": reservation.id,
                "reason": "dates_and_rooms_frozen_after_check_in",
            }
        )

    check_in = fields.get("check_in_date", reservation.check_in_date)
    check_out = fields.get("check_out_date", reservation.check_out_date)

    # RESERVATIONS-AUTO-ROOM §7: manual replacement validates each new line's
    # pinned room before the locks; automatic is assigned after the availability
    # check (below). Only fires when the lines are actually being replaced.
    if lines is not None and room_assignment_mode == "manual":
        _validate_manual_assignment(lines)

    effective_lines = lines
    inventory_affecting = (
        reservation.status in (ReservationStatus.HELD, ReservationStatus.CONFIRMED)
        and (lines is not None or _touches_dates(fields))
    )
    if inventory_affecting:
        payload = (
            _book_payload(effective_lines)
            if effective_lines is not None
            else _db_lines(reservation)
        )
        AvailabilityService.ensure_can_book(
            reservation.hotel,
            payload,
            check_in,
            check_out,
            exclude_reservation_id=reservation.id,
        )

    # Backend-authoritative capacity, occupant-aware. Only re-checked when a
    # relevant input (lines / occupants / adult or child counts) changes.
    if (
        lines is not None
        or occupants is not None
        or "adults" in fields
        or "children" in fields
    ):
        _enforce_capacity_update(reservation, lines, occupants, fields)

    # DI-F4: whenever the companion list is (re)provided — including an empty
    # list that clears companions — store ``adults`` authoritatively as 1
    # primary + the companions, matching the occupant-derived capacity that was
    # just enforced. When occupants is None the list is untouched, so the
    # existing ``adults`` behavior is preserved (backward compatible).
    if occupants is not None:
        fields["adults"] = 1 + len(occupants)

    for attr, value in fields.items():
        setattr(reservation, attr, value)
    if user is not None and getattr(user, "is_authenticated", False):
        reservation.updated_by = user
    reservation.save()

    if lines is not None:
        # STAYS rate-integrity remediation (item 6 + FIX A): capture the PRIOR lines'
        # agreed snapshots BEFORE deleting so a same-type replacement PRESERVES the
        # agreed rate (a date/guest edit never re-prices). Keep a LIST per RoomType
        # (in id order) and consume by POSITION, so two lines of the SAME type at
        # DIFFERENT agreed rates (e.g. default 100 + an audited override 150) each
        # carry their OWN prior snapshot — never all collapsing onto the first.
        prior_by_type = {}
        for prior in reservation.lines.all().order_by("id"):
            prior_by_type.setdefault(prior.room_type_id, []).append(prior)
        reservation.lines.all().delete()
        # RESERVATIONS-AUTO-ROOM §7: assign the replacement lines under the locks
        # ``ensure_can_book`` acquired above; excluding this reservation so it
        # never conflicts with its own (now deleted) lines.
        if room_assignment_mode == "automatic":
            _assign_rooms_automatically(
                reservation.hotel,
                lines,
                check_in,
                check_out,
                total_persons=_total_persons_update(reservation, occupants, fields),
                exclude_reservation_id=reservation.id,
            )
        for line in lines:
            # Consume the next prior line of this RoomType (by position), so each
            # replacement line preserves its OWN snapshot; capture the new type's
            # rate on a genuine type change; gate an explicit different rate.
            bucket = prior_by_type.get(line["room_type"].id)
            prior_line = bucket.pop(0) if bucket else None
            agreed_rate, agreed_currency = _line_snapshot_for_write(
                line,
                prior_line=prior_line,
                hotel=reservation.hotel,
                user=user,
            )
            ReservationRoomLine.objects.create(
                hotel=reservation.hotel,
                reservation=reservation,
                room_type=line["room_type"],
                room=line.get("room"),
                quantity=line["quantity"],
                adults=line.get("adults"),
                children=line.get("children"),
                notes=line.get("notes", ""),
                agreed_nightly_rate=agreed_rate,
                agreed_rate_currency=agreed_currency,
            )
    if occupants is not None:
        reservation.occupants.all().delete()
        _create_occupants(reservation.hotel, reservation, occupants)
    return reservation


@transaction.atomic
def confirm_reservation(reservation, *, user=None) -> Reservation:
    """Confirm a held reservation, re-checking availability first."""
    if reservation.status == ReservationStatus.CONFIRMED:
        return reservation
    if reservation.status not in (ReservationStatus.HELD,):
        raise InvalidReservationTransition(
            {"detail": "Only a held reservation can be confirmed."}
        )
    AvailabilityService.ensure_can_book(
        reservation.hotel,
        _db_lines(reservation),
        reservation.check_in_date,
        reservation.check_out_date,
        exclude_reservation_id=reservation.id,
    )
    previous = reservation.status
    reservation.status = ReservationStatus.CONFIRMED
    reservation.hold_expires_at = None
    if user is not None and getattr(user, "is_authenticated", False):
        reservation.updated_by = user
    reservation.save(update_fields=["status", "hold_expires_at", "updated_by", "updated_at"])
    _log_status(reservation, previous, reservation.status, note="confirmed", user=user)
    return reservation


@transaction.atomic
def hold_reservation(reservation, *, hold_expires_at, user=None) -> Reservation:
    """Place or refresh a temporary hold, re-checking availability first.

    Only a held reservation can be (re)held; this refreshes its expiry, which is
    meaningful when the hold has lapsed and its inventory must be re-acquired.
    """
    from django.utils.dateparse import parse_datetime

    if reservation.status != ReservationStatus.HELD:
        raise InvalidReservationTransition(
            {"detail": "Only a held reservation can be re-held."}
        )
    if hold_expires_at is None:
        raise InvalidReservationTransition(
            {"detail": "A hold expiry time is required."}
        )
    if isinstance(hold_expires_at, str):
        parsed = parse_datetime(hold_expires_at)
        if parsed is None:
            raise InvalidReservationTransition(
                {"detail": "Invalid hold expiry time."}
            )
        hold_expires_at = parsed

    AvailabilityService.ensure_can_book(
        reservation.hotel,
        _db_lines(reservation),
        reservation.check_in_date,
        reservation.check_out_date,
        exclude_reservation_id=reservation.id,
    )
    reservation.hold_expires_at = hold_expires_at
    if user is not None and getattr(user, "is_authenticated", False):
        reservation.updated_by = user
    reservation.save(update_fields=["hold_expires_at", "updated_by", "updated_at"])
    _log_status(
        reservation, reservation.status, reservation.status, note="hold refreshed", user=user
    )
    return reservation


@transaction.atomic
def cancel_reservation(reservation, *, reason, user=None) -> Reservation:
    """Cancel a reservation (soft — never a hard delete). Requires a reason."""
    if not (reason or "").strip():
        raise CancellationReasonRequired()
    if reservation.status == ReservationStatus.CANCELLED:
        return reservation
    if reservation.status == ReservationStatus.EXPIRED:
        raise InvalidReservationTransition(
            {"detail": "An expired reservation cannot be cancelled."}
        )
    # Post-check-in guard (RESERVATIONS-FINAL-CLOSURE §2): once the reservation has
    # produced ANY stay — in-house OR already checked-out — its record belongs to
    # the stay/folio and must NOT be rewritten to "cancelled" through the normal
    # cancel cycle (that would corrupt operational history + reports). A correction
    # after check-in travels through the front desk's own reversal flow. This
    # mirrors the has_any_stay guard already enforced on update/deposit.
    if has_any_stay(reservation):
        raise ReservationHasActiveStay(
            {"reservation": reservation.id, "reason": "reservation_has_stay"}
        )
    previous = reservation.status
    reservation.status = ReservationStatus.CANCELLED
    reservation.cancellation_reason = reason.strip()
    reservation.cancelled_at = timezone.now()
    if user is not None and getattr(user, "is_authenticated", False):
        reservation.cancelled_by = user
        reservation.updated_by = user
    reservation.save()
    _log_status(reservation, previous, reservation.status, note=reason.strip(), user=user)
    from apps.notifications.services import record_activity

    record_activity(
        reservation.hotel,
        event_type="reservation.cancelled",
        category="reservation",
        severity="warning",
        title=f"Reservation {reservation.reservation_number} cancelled",
        message=reason.strip(),
        actor=user,
        related_object=reservation,
        related_url="/hotel/reservations",
    )
    return reservation


@transaction.atomic
def mark_no_show(reservation, *, reason, user=None) -> Reservation:
    """Mark an expected arrival as a NO-SHOW (§29): the guest never arrived within
    the hotel's policy and no stay was created. A SOFT transition (never a delete)
    that frees availability (``NO_SHOW`` is non-blocking) and records the reason +
    actor via the status log.

    Guards: only a LIVE arrival (held/confirmed) with NO stay, whose arrival date
    has already come (never a future booking). The deposit is NOT auto-forfeited or
    refunded here — handling it is a separate, explicit finance action per the
    hotel's cancellation policy (§29: never treat the deposit as due/refunded
    without a rule).
    """
    if not (reason or "").strip():
        raise NoShowReasonRequired()
    if reservation.status == ReservationStatus.NO_SHOW:
        return reservation
    if reservation.status not in (
        ReservationStatus.HELD,
        ReservationStatus.CONFIRMED,
    ):
        raise InvalidReservationTransition(
            {"detail": "Only a live arrival can be marked as a no-show."}
        )
    if has_any_stay(reservation):
        raise ReservationHasActiveStay(
            {"reservation": reservation.id, "reason": "reservation_has_stay"}
        )
    from apps.shifts.services import get_business_date

    business_date = get_business_date(reservation.hotel)
    if reservation.check_in_date > business_date:
        raise InvalidReservationTransition(
            {
                "detail": "The arrival date has not passed yet.",
                "check_in_date": str(reservation.check_in_date),
                "business_date": str(business_date),
            }
        )
    previous = reservation.status
    reservation.status = ReservationStatus.NO_SHOW
    reservation.no_show_reason = reason.strip()
    if user is not None and getattr(user, "is_authenticated", False):
        reservation.updated_by = user
    reservation.save()
    _log_status(
        reservation,
        previous,
        reservation.status,
        note=f"no-show · {reason.strip()}",
        user=user,
    )
    from apps.notifications.services import record_activity

    record_activity(
        reservation.hotel,
        event_type="reservation.no_show",
        category="reservation",
        severity="warning",
        title=f"Reservation {reservation.reservation_number} marked no-show",
        message=reason.strip(),
        actor=user,
        related_object=reservation,
        related_url="/hotel/front-desk",
    )
    return reservation


def _book_payload(lines) -> list[dict]:
    """Normalize lines into ``ensure_can_book`` input dicts.

    Accepts serializer lines (``room_type``/``room`` model instances) or DB-shaped
    lines (``room_type_id``/``room_id``).
    """
    payload = []
    for line in lines:
        rt = line.get("room_type")
        rt_id = rt.id if hasattr(rt, "id") else line.get("room_type_id")
        room = line.get("room")
        if room is not None and hasattr(room, "id"):
            room_id = room.id
        elif room is not None:
            room_id = room
        else:
            room_id = line.get("room_id")
        payload.append(
            {
                "room_type_id": int(rt_id),
                "quantity": int(line["quantity"]),
                "room_id": room_id,
            }
        )
    return payload


def _db_lines(reservation) -> list[dict]:
    """DB-shaped line dicts for a reservation (no extra queries)."""
    return [
        {"room_type_id": ln.room_type_id, "quantity": ln.quantity, "room_id": ln.room_id}
        for ln in reservation.lines.all()
    ]


def _touches_dates(fields) -> bool:
    return "check_in_date" in fields or "check_out_date" in fields


# --- RESERVATIONS-AUTO-ROOM: automatic / manual room assignment --------------


def _total_persons_create(fields, occupants) -> int:
    """Total persons for a create (mirrors ``_enforce_capacity``): 1 primary +
    named adult companions + children when companions are supplied, else the
    legacy ``adults + children`` counts."""
    children = int(fields.get("children") or 0)
    if occupants:
        return 1 + len(occupants) + children
    return int(fields.get("adults") or 1) + children


def _total_persons_update(reservation, occupants, fields) -> int:
    """Total persons for an update (mirrors ``_enforce_capacity_update``)."""
    children = int(fields.get("children", reservation.children) or 0)
    if occupants is not None:
        return 1 + len(occupants) + children
    existing = reservation.occupants.count()
    if existing:
        return 1 + existing + children
    return int(fields.get("adults", reservation.adults) or 1) + children


def _validate_manual_assignment(lines) -> None:
    """Validate manual room assignment: every line MUST pin a specific room, and
    a request-pinned floor must match the room's floor.

    The room itself (hotel + type + bookable + quantity 1) is already validated
    by the write serializer; its availability is enforced by ``ensure_can_book``.
    The backend never silently swaps a conflicting room for another one.
    """
    for line in lines:
        room = line.get("room")
        if room is None:
            raise DRFValidationError(
                {"room": "A specific room is required in manual assignment mode."}
            )
        floor = line.get("floor")
        if floor is not None:
            floor_id = floor.pk if hasattr(floor, "pk") else floor
            if getattr(room, "floor_id", None) != floor_id:
                raise RoomAssignmentConflict(
                    {"room": room.id, "reason": "room_floor_mismatch"}
                )


def _assign_rooms_automatically(
    hotel, lines, check_in, check_out, *, total_persons, exclude_reservation_id=None
) -> None:
    """Deterministically assign a specific room to every ``quantity == 1`` line
    (RESERVATIONS-AUTO-ROOM). Mutates ``line["room"]`` in place.

    A client-provided room is ALWAYS discarded first (security: the client must
    not be able to pin a room in automatic mode). ``min_capacity`` is passed only
    for a single-line reservation — where the one room holds everyone — so a
    multi-room reservation (capacity already enforced across all rooms) is never
    wrongly rejected. Rooms picked earlier in the same request are excluded so
    two lines never receive the same room. Raises ``no_room_available`` (a clean
    no-availability error) when a line has no matching room, failing the save.
    """
    used: set[int] = set()
    single_line = len(lines) == 1
    for line in lines:
        line["room"] = None  # never honour a client-pinned room in auto mode
        if int(line["quantity"]) != 1:
            # A specific room cannot be pinned to a multi-room line (one FK);
            # it stays unassigned — ``ensure_can_book`` already guaranteed the
            # unassigned quantity fits.
            continue
        room = AvailabilityService.pick_available_room(
            hotel,
            room_type=line["room_type"],
            check_in=check_in,
            check_out=check_out,
            floor=line.get("floor"),
            min_capacity=total_persons if single_line else None,
            exclude_room_ids=used,
            exclude_reservation_id=exclude_reservation_id,
        )
        if room is None:
            raise NoAvailability(
                {
                    "room_type": line["room_type"].id,
                    "room_type_name": getattr(line["room_type"], "name", None),
                    "reason": "no_room_available",
                }
            )
        line["room"] = room
        used.add(room.id)


# --- RESERVATIONS-FORM-REWORK helpers ---------------------------------------


def _apply_primary_guest_snapshot(fields) -> None:
    """Freeze the structured snapshot from a linked ``primary_guest`` (create).

    Only fills snapshot fields that the caller left empty — an explicitly
    provided snapshot value always wins — so the snapshot is captured faithfully
    once at booking time. Mutates ``fields`` in place. No-op without a guest.
    """
    guest = fields.get("primary_guest")
    if guest is None:
        return
    for snap_field, guest_field in _PRIMARY_GUEST_SNAPSHOT_MAP.items():
        if not fields.get(snap_field):
            fields[snap_field] = getattr(guest, guest_field, "") or ""
    if not fields.get("primary_guest_date_of_birth") and getattr(
        guest, "date_of_birth", None
    ):
        fields["primary_guest_date_of_birth"] = guest.date_of_birth


def _create_occupants(hotel, reservation, occupants) -> None:
    """Create adult-companion rows. Links an existing guest when provided;
    otherwise stores the structured identity inline (no Guest row is forced)."""
    if not occupants:
        return
    for occ in occupants:
        ReservationOccupant.objects.create(
            hotel=hotel,
            reservation=reservation,
            guest=occ.get("guest"),
            first_name=occ.get("first_name", "") or "",
            last_name=occ.get("last_name", "") or "",
            father_name=occ.get("father_name", "") or "",
            mother_name=occ.get("mother_name", "") or "",
            national_id=occ.get("national_id", "") or "",
            nationality=occ.get("nationality", "") or "",
            date_of_birth=occ.get("date_of_birth"),
            relationship=occ.get("relationship", "") or "",
        )


def _capacity_of_lines(lines) -> int:
    """Sum ``quantity * room_type.max_capacity`` over resolved serializer lines."""
    return sum(
        int(line["quantity"]) * int(line["room_type"].max_capacity)
        for line in lines
    )


def _enforce_capacity(lines, fields, occupants) -> None:
    """Raise unless total persons fit the selected rooms (create path).

    Total persons = 1 primary + adult companions + children when companions are
    supplied; otherwise the legacy ``adults + children`` counts. Raises a clean
    validation error (same envelope/style as the serializer capacity check).
    """
    capacity = _capacity_of_lines(lines)
    children = int(fields.get("children") or 0)
    if occupants:
        total_persons = 1 + len(occupants) + children
    else:
        total_persons = int(fields.get("adults") or 1) + children
    _raise_if_over_capacity(total_persons, capacity)


def _enforce_capacity_update(reservation, lines, occupants, fields) -> None:
    """Raise unless total persons fit the selected rooms (update path).

    Uses the effective lines (new ones if provided, else the reservation's
    current lines) and the effective person counts (new occupants if provided,
    else the reservation's current occupants; falling back to ``adults`` only
    when there are no named companions at all).
    """
    if lines is not None:
        capacity = _capacity_of_lines(lines)
    else:
        capacity = sum(
            rl.quantity * rl.room_type.max_capacity
            for rl in reservation.lines.select_related("room_type").all()
        )
    children = int(fields.get("children", reservation.children) or 0)
    if occupants is not None:
        total_persons = 1 + len(occupants) + children
    else:
        existing_occupants = reservation.occupants.count()
        if existing_occupants:
            total_persons = 1 + existing_occupants + children
        else:
            total_persons = int(fields.get("adults", reservation.adults) or 1) + children
    _raise_if_over_capacity(total_persons, capacity)


def _raise_if_over_capacity(total_persons, capacity) -> None:
    if total_persons > capacity:
        raise DRFValidationError(
            {
                "occupants": (
                    "Total persons exceed the maximum capacity of the "
                    "selected rooms."
                )
            }
        )


def has_in_house_stay(reservation) -> bool:
    """True when a stay created from this reservation is currently in-house.

    Post-check-in the STAY is the source of truth (documented decision) —
    operational changes travel through the front desk, never the booking.
    """
    from apps.stays.models import Stay, StayStatus

    return Stay.objects.filter(
        reservation=reservation, status=StayStatus.IN_HOUSE
    ).exists()


def has_any_stay(reservation) -> bool:
    """True when the reservation has ANY related stay — in-house OR already
    checked-out (Finance-F1, §27/§33).

    A pre-arrival concept (a fresh deposit, a date/room/line edit) is only valid
    while the booking has NEVER produced a stay. The moment a stay exists the
    money and inventory live on the stay/folio, so a NEW reservation deposit
    would open an ORPHAN pre-arrival folio (inflating paid / negative remaining)
    and a date/room edit would silently diverge from the stay. This broadens
    ``has_in_house_stay`` to also catch a checked-out booking whose reservation is
    still CONFIRMED and whose stay folio is CLOSED. A single ``exists`` query — no
    prefetch assumption, safe on the un-prefetched view/service paths.
    """
    from apps.stays.models import Stay

    return Stay.objects.filter(reservation=reservation).exists()


def latest_stay(reservation):
    """The most recent Stay derived from this reservation, or ``None``.

    Uses the reverse ``stays`` relation (prefetched by the reservation list/detail
    querysets, so this adds no query there). "Most recent" = highest pk, i.e. the
    last stay row created for the booking — this lets a read serializer expose a
    single ``stay_status`` (in_house / checked_out / cancelled) that distinguishes
    an in-house guest, a departed guest, and a booking that never checked in
    (``None``), which the boolean ``has_in_house_stay`` alone cannot.
    """
    stays = list(reservation.stays.all())
    if not stays:
        return None
    return max(stays, key=lambda s: s.id)


def reservation_financials(reservation, *, hotel=None, include_folio_balance=False) -> dict:
    """Derive a reservation's money summary — a READ-ONLY view, never stored.

    Design (RESERVATIONS-FORM-UX-CORRECTION §26/§31/§35, office decision — there
    is NO pricing/tax engine in this repo, so none is invented):

    - ``reservation_total`` = ``Σ money(room_type.base_rate × nights × quantity)``
      over the reservation's room lines. ``base_rate`` is a reference value that
      may be ``NULL``; a line without one is UNPRICED — it contributes nothing and
      flags the whole reservation as not fully priced (``is_priced=False``), so the
      UI can honestly show "not priced" rather than a fabricated total.
    - ``nightly_rate`` = ``Σ money(base_rate × quantity)`` over priced lines.
    - ``paid`` = ``Σ`` POSTED ``Payment.amount`` (already the base/reservation
      currency equivalent — §29) across the reservation's folio(s). Deposits taken
      before check-in AND payments on the reused stay folio are all counted, since
      they hang off the same reservation-linked folio ledger (invariant #1).
    - ``remaining`` = ``money(total − paid)`` — DERIVED, never a stored second
      balance (§31).
    - ``payment_status`` ∈ {unpaid, partial, paid}, derived from paid vs total.

    ``currency`` is the reservation/base currency (the hotel default), matching the
    folio currency. Pass ``hotel`` to avoid an FK hit per row in list rendering.
    All money is :class:`~decimal.Decimal` via ``money()``. Returns a plain dict of
    Decimals/None (+ metadata); serialization to strings is the caller's job.
    """
    from apps.finance.models import PostingStatus
    from apps.finance.services import ZERO, money

    hotel = hotel or reservation.hotel
    settings_obj = getattr(hotel, "settings", None)
    currency = (getattr(settings_obj, "default_currency", "") or "") or "USD"

    nights = reservation.nights
    unpriced = False
    priced_present = False
    nightly = ZERO
    total = ZERO
    for line in reservation.lines.all():
        rate = line.room_type.base_rate
        qty = int(line.quantity or 0)
        if rate is None:
            unpriced = True
            continue
        priced_present = True
        rate = money(rate)
        nightly += rate * qty
        total += rate * qty * nights
    is_priced = priced_present and not unpriced
    nightly = money(nightly) if is_priced else None
    total = money(total) if is_priced else None

    # RESERVATIONS-FINAL-CLOSURE §1 — once the reservation has produced a STAY, the
    # money lives on the stay's folio (invariant #1: the reused folio). A
    # reservation-level paid/remaining/status would compare the ROOM total against
    # folio payments that ALSO include in-stay charges (services, F&B) — a
    # misleading figure that contradicts the central source of truth. So the
    # account is reported as "moved to folio": the derived reservation-level money
    # (paid/remaining/status) is suppressed, and the REAL folio balance is surfaced
    # instead. The folio balance is only computed when explicitly requested
    # (``include_folio_balance``) so the list render never pays a per-card
    # folio-charge query. ``reservation.stays`` is prefetched on the list/detail
    # paths, so ``has_stay`` costs no extra query there.
    has_stay = any(True for _ in reservation.stays.all())
    if has_stay:
        folio_balance = None
        if include_folio_balance:
            from apps.finance.services import folio_balance as _folio_balance

            bal = ZERO
            for folio in reservation.folios.all():
                bal += _folio_balance(folio)["balance"]
            folio_balance = money(bal)
        return {
            "currency": currency,
            "nights": nights,
            "nightly_rate": nightly,
            "reservation_total": total,
            "paid": None,
            "remaining": None,
            "payment_status": None,
            "is_priced": is_priced,
            "has_stay": True,
            "folio_balance": folio_balance,
        }

    paid = ZERO
    for folio in reservation.folios.all():
        for payment in folio.payments.all():
            if payment.status == PostingStatus.POSTED:
                paid += payment.amount
    paid = money(paid)

    remaining = money(total - paid) if total is not None else None
    if paid <= ZERO:
        payment_status = "unpaid"
    elif total is None:
        # Money received but the total is unknown (unpriced) — honestly partial.
        payment_status = "partial"
    elif paid >= total:
        payment_status = "paid"
    else:
        payment_status = "partial"

    return {
        "currency": currency,
        "nights": nights,
        "nightly_rate": nightly,
        "reservation_total": total,
        "paid": paid,
        "remaining": remaining,
        "payment_status": payment_status,
        "is_priced": is_priced,
        "has_stay": False,
        "folio_balance": None,
    }
