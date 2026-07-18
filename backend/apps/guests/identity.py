"""Central guest-identity resolution (GUESTS central identity — W2).

This is the ONE service every operational path (reservations, stays, public
booking — wired in W3) calls to turn a caller's identity snapshot (national id /
passport / phone + name fields) into a single canonical :class:`Guest` row for a
hotel. It never lets a caller duplicate, silently merge, overwrite, or bypass a
ban.

Design invariants (owner decisions honored here)
------------------------------------------------
* **Exact normalized matching only.** No ``icontains`` / partial search anywhere.
  Matching is on the index-backed normalized keys (``national_id_normalized``,
  ``document_number_normalized`` for passports, ``phone_normalized``) produced by
  the W1 :mod:`apps.guests.normalize` helpers, so spacing / punctuation /
  non-Latin digits never change the outcome.
* **Phone is canonical (Decision 1).** The identity phone key is the STRICT
  :func:`~apps.guests.normalize.canonical_phone` E.164 value. An uninterpretable
  phone raises a clean DRF ``ValidationError`` — an approximate value is never
  stored. A created guest stores the canonical phone as ``Guest.phone`` so the
  model's ``save()`` derives ``phone_normalized`` == that canonical value, keeping
  the stored key and the search key identical (see the phone note below).
* **Ban fingerprint = national id + passport + canonical phone ONLY
  (Decision 4).** Driving-license / 'other' documents never take part in the ban
  or in identity resolution. The ban is matched on the IDENTITY, not on a linked
  row, which closes the fresh-guest bypass.
* **Conflicts refuse, they never merge.** A strong identifier (national id or
  passport) pointing at guest A while the phone points at a different active
  guest B is a :class:`GuestIdentityConflict` (409) with NO side effects. There
  is no merge path this round.
* **Reuse never overwrites the central record (Decision 2).** A resolved row is
  returned as-is; the only mutation on reuse is reactivating an inactive match
  (which is audited). Enriching stale fields from a caller snapshot is left to a
  later, explicit path.
* **Tenant-scoped always.** Every query is filtered ``hotel=hotel``.

Phone key consistency (why we store the canonical phone)
--------------------------------------------------------
``Guest.save()`` (frozen in W1) computes ``phone_normalized = normalize_phone(
self.phone)`` WITHOUT a country. ``normalize_phone`` is idempotent on an E.164
string (``"+9665551112233"`` -> ``"+9665551112233"``). So if this service stores
the canonical E.164 value in ``Guest.phone`` on create, the derived
``phone_normalized`` equals the canonical search key and reuse-by-phone is exact
and self-consistent. Legacy rows whose ``phone_normalized`` was computed from a
country-less local number are a data-backfill concern owned outside W2 (flagged
to the orchestrator).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework.exceptions import ErrorDetail, ValidationError

from apps.common.exceptions import GuestBlocked, GuestIdentityConflict

from .models import DocumentType, Guest
from .normalize import (
    PhoneNormalizationError,
    canonical_phone,
    normalize_document,
    normalize_id,
    normalize_phone,
)
from .services import record_guest_created, record_guest_reactivated

# --- Classification kinds ---------------------------------------------------
NONE = "none"
SINGLE = "single"
MULTIPLE = "multiple"
CONFLICT = "conflict"

# Fields copied verbatim onto a newly-created central guest. Kept explicit so a
# caller snapshot can never smuggle unexpected columns (e.g. is_blocked, is_vip)
# into the create. Normalized keys are derived by ``Guest.save()``, never here.
_CREATE_TEXT_FIELDS = (
    "full_name",
    "first_name",
    "last_name",
    "father_name",
    "mother_name",
    "nationality",
    "gender",
    "email",
    "address",
)


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


def _hotel_default_phone_country(hotel) -> Optional[str]:
    """The hotel's ISO-3166-1 alpha-2 default phone country (from HotelSettings),
    or ``None`` when there is no settings row or the field is blank. ``None``
    means a LOCAL phone cannot be canonicalized and will raise — never guessed."""
    settings_obj = getattr(hotel, "settings", None)
    return getattr(settings_obj, "default_phone_country", "") or None


def _coerce_guest_id(value) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class NormalizedIdentity:
    """The canonicalized identity keys for one resolution call.

    ``*_raw`` values are the trimmed originals (passed to :func:`search_guests`
    and stored on a new guest); ``*_key`` values are the normalized lookup keys.
    ``canonical_phone`` is the strict E.164 value ("" == no phone).
    """

    national_id_raw: str
    passport_raw: str
    phone_canonical: str
    national_id_key: str
    passport_key: str
    phone_key: str


@dataclass(frozen=True)
class IdentitySearchResult:
    """Which stored guest each identity key resolved to.

    ``national_id_match`` / ``passport_match`` are at most one row each (both keys
    are lifetime-unique per hotel). ``phone_matches`` may hold several rows: the
    phone key is unique only among ACTIVE guests, so inactive rows can share it.
    Rows are ordered active-first.
    """

    national_id_match: Optional[Guest]
    passport_match: Optional[Guest]
    phone_matches: Sequence[Guest]

    @property
    def strong_match(self) -> Optional[Guest]:
        return self.national_id_match or self.passport_match


@dataclass(frozen=True)
class MatchClassification:
    """Deterministic verdict for a search result. ``guest`` is set only for
    :data:`SINGLE` (the row to reuse)."""

    kind: str
    guest: Optional[Guest] = None


# ---------------------------------------------------------------------------
# 1. search_guests — exact, normalized, tenant-scoped lookup
# ---------------------------------------------------------------------------
def search_guests(
    hotel, *, national_id: str = "", passport: str = "", phone: str = ""
) -> IdentitySearchResult:
    """Return the guest(s) each identity key resolves to, EXACT-matched on the
    normalized keys and scoped to ``hotel``.

    * ``national_id`` -> ``national_id_normalized`` (lifetime-unique -> 0/1 row).
    * ``passport`` -> ``document_type='passport'`` + ``document_number_normalized``
      (lifetime-unique per type -> 0/1 row).
    * ``phone`` -> ``phone_normalized`` (0..N rows; active-first). Pass the value
      through :func:`~apps.guests.normalize.normalize_phone`, which is
      identity-preserving on an already-canonical E.164 string, so passing the
      canonical phone here matches rows created by this service.

    Inactive rows ARE included (reuse+reactivate needs them); ``is_active`` on the
    returned rows tells the classifier which are live.
    """
    nid_key = normalize_id(national_id)
    doc_key = normalize_document(passport)
    phone_key = normalize_phone(phone)

    national_id_match = None
    if nid_key:
        national_id_match = Guest.objects.filter(
            hotel=hotel, national_id_normalized=nid_key
        ).first()

    passport_match = None
    if doc_key:
        passport_match = Guest.objects.filter(
            hotel=hotel,
            document_type=DocumentType.PASSPORT,
            document_number_normalized=doc_key,
        ).first()

    phone_matches: Sequence[Guest] = ()
    if phone_key:
        phone_matches = tuple(
            Guest.objects.filter(
                hotel=hotel, phone_normalized=phone_key
            ).order_by("-is_active", "id")
        )

    return IdentitySearchResult(
        national_id_match=national_id_match,
        passport_match=passport_match,
        phone_matches=phone_matches,
    )


# ---------------------------------------------------------------------------
# 2. classify_matches — none | single | multiple | conflict (deterministic)
# ---------------------------------------------------------------------------
def classify_matches(result: IdentitySearchResult) -> MatchClassification:
    """Classify a :class:`IdentitySearchResult`. Pure and deterministic.

    * :data:`CONFLICT` — two DIFFERENT strong identifiers (national id vs
      passport), OR a strong identifier resolving to guest A while the phone
      resolves to a DIFFERENT ACTIVE guest B.
    * :data:`MULTIPLE` — no single row can be chosen (e.g. the phone maps to
      several distinct guests and no strong identifier disambiguates).
    * :data:`SINGLE` — exactly one row to reuse (``guest`` set).
    * :data:`NONE` — nothing matched.
    """
    strong: list[Guest] = []
    if result.national_id_match is not None:
        strong.append(result.national_id_match)
    if result.passport_match is not None:
        strong.append(result.passport_match)
    strong_ids = {g.id for g in strong}

    # Two different strong identifiers point at two different people.
    if len(strong_ids) > 1:
        return MatchClassification(CONFLICT)

    strong_guest = strong[0] if strong else None

    active_phone = [g for g in result.phone_matches if g.is_active]
    active_phone_ids = {g.id for g in active_phone}
    phone_active_guest = active_phone[0] if active_phone else None

    if strong_guest is not None:
        # Strong id wins, but only if the phone (if it points at a LIVE guest)
        # agrees. A live phone owner different from the strong-id guest is a
        # genuine identity clash.
        if phone_active_guest is not None and phone_active_guest.id != strong_guest.id:
            return MatchClassification(CONFLICT)
        return MatchClassification(SINGLE, strong_guest)

    # No strong identifier — resolve by phone.
    if phone_active_guest is not None:
        # phone_normalized is unique among active rows, so this should be a single
        # active guest; guard the impossible-in-DB case defensively.
        if len(active_phone_ids) > 1:
            return MatchClassification(MULTIPLE)
        return MatchClassification(SINGLE, phone_active_guest)

    inactive_matches = [g for g in result.phone_matches if not g.is_active]
    inactive_ids = {g.id for g in inactive_matches}
    if len(inactive_ids) == 1:
        return MatchClassification(SINGLE, inactive_matches[0])
    if len(inactive_ids) > 1:
        return MatchClassification(MULTIPLE)
    return MatchClassification(NONE)


# ---------------------------------------------------------------------------
# 3. ban fingerprint
# ---------------------------------------------------------------------------
def _ban_query(keys: NormalizedIdentity) -> Optional[Q]:
    """Build the ban-fingerprint OR-query from the identity keys, or ``None`` when
    no strong-or-phone identifier is present. Driving-license / 'other' documents
    never contribute (Decision 4)."""
    q = Q()
    present = False
    if keys.national_id_key:
        q |= Q(national_id_normalized=keys.national_id_key)
        present = True
    if keys.passport_key:
        q |= Q(
            document_type=DocumentType.PASSPORT,
            document_number_normalized=keys.passport_key,
        )
        present = True
    if keys.phone_key:
        q |= Q(phone_normalized=keys.phone_key)
        present = True
    return q if present else None


def _ensure_not_banned_by_keys(hotel, keys: NormalizedIdentity) -> None:
    """Raise :class:`GuestBlocked` (carrying NO reason) if any BLOCKED guest in
    this hotel matches the ban fingerprint. Matches the IDENTITY, not a linked
    row — a freshly-typed snapshot for a blocked person cannot slip through."""
    q = _ban_query(keys)
    if q is None:
        return
    if Guest.objects.filter(hotel=hotel, is_blocked=True).filter(q).exists():
        raise GuestBlocked()


def ensure_identity_not_banned(
    hotel,
    *,
    national_id: str = "",
    passport: str = "",
    phone: str = "",
    default_country: Optional[str] = None,
) -> None:
    """Public ban guard: raise :class:`GuestBlocked` when the given identity is
    banned in ``hotel``. Uses the national id + passport + canonical phone
    fingerprint only. An uninterpretable phone contributes nothing (it cannot
    match a canonical stored key) rather than raising — this guard never blocks a
    write on a bad phone; the strict phone validation lives in
    :func:`resolve_or_create_guest`."""
    if default_country is None:
        default_country = _hotel_default_phone_country(hotel)
    try:
        canonical = canonical_phone((phone or "").strip(), default_country=default_country)
    except PhoneNormalizationError:
        canonical = ""
    keys = NormalizedIdentity(
        national_id_raw=(national_id or "").strip(),
        passport_raw=(passport or "").strip(),
        phone_canonical=canonical,
        national_id_key=normalize_id(national_id),
        passport_key=normalize_document(passport),
        phone_key=normalize_phone(canonical),
    )
    _ensure_not_banned_by_keys(hotel, keys)


# ---------------------------------------------------------------------------
# 4. resolve_or_create_guest — the central entry point
# ---------------------------------------------------------------------------
def _normalize_identity(hotel, identity: Mapping) -> NormalizedIdentity:
    """Normalize the caller identity. Raises a clean DRF ``ValidationError`` on an
    uninterpretable phone (Decision 1 — never store an approximation)."""
    national_id_raw = (identity.get("national_id") or "").strip()
    passport_raw = (identity.get("passport") or "").strip()
    phone_raw = (identity.get("phone") or "").strip()
    default_country = _hotel_default_phone_country(hotel)
    try:
        canonical = canonical_phone(phone_raw, default_country=default_country)
    except PhoneNormalizationError:
        raise ValidationError(
            {
                "phone": [
                    ErrorDetail(
                        "This phone number could not be interpreted; enter it in "
                        "international +country form.",
                        code="invalid_phone",
                    )
                ]
            }
        )
    return NormalizedIdentity(
        national_id_raw=national_id_raw,
        passport_raw=passport_raw,
        phone_canonical=canonical,
        national_id_key=normalize_id(national_id_raw),
        passport_key=normalize_document(passport_raw),
        phone_key=normalize_phone(canonical),
    )


def _search(hotel, keys: NormalizedIdentity) -> IdentitySearchResult:
    return search_guests(
        hotel,
        national_id=keys.national_id_raw,
        passport=keys.passport_raw,
        phone=keys.phone_canonical,
    )


def _reuse(guest, *, user, keys: NormalizedIdentity, allow_reactivate: bool):
    """Return the resolved ``guest`` for reuse.

    * A blocked guest re-asserts the ban (:class:`GuestBlocked`) — reuse /
      reactivation NEVER bypasses a block.
    * An inactive guest is reactivated atomically (audited) ONLY when
      ``allow_reactivate`` (the authenticated write paths). The public path never
      reactivates a hotel-deactivated profile and gets ``None`` instead.
    * The central record's stored data is otherwise untouched (Decision 2).
    """
    if guest.is_blocked:
        raise GuestBlocked()
    if guest.is_active:
        return guest
    if not allow_reactivate:
        return None

    locked = Guest.objects.select_for_update().filter(pk=guest.pk).first()
    if locked is None:
        # Vanished between classify and lock — treat as an ambiguous conflict
        # rather than resurrecting a deleted row.
        raise GuestIdentityConflict()
    if locked.is_blocked:
        raise GuestBlocked()
    if locked.is_active:
        return locked

    locked.is_active = True
    locked.updated_by = _actor(user)
    try:
        with transaction.atomic():
            locked.save(update_fields=["is_active", "updated_by", "updated_at"])
    except IntegrityError:
        # The only is_active-scoped constraint is the active phone-uniqueness one:
        # a DIFFERENT active guest now holds this profile's phone, so reactivating
        # it would create two live guests with the same phone. That is a genuine
        # identity conflict, not a duplicate to silently merge. Savepoint rolled
        # back -> no side effects.
        raise GuestIdentityConflict()
    record_guest_reactivated(locked, user=user)
    return locked


def _create(hotel, *, identity: Mapping, keys: NormalizedIdentity, user):
    """Create a new central guest carrying the caller's identity + name fields.
    The normalized keys are derived by ``Guest.save()``. Concurrency-safe: a
    racing insert that trips a unique constraint is refetched, never a 500."""
    fields = {
        name: (identity.get(name) or "").strip() for name in _CREATE_TEXT_FIELDS
    }
    guest = Guest(
        hotel=hotel,
        phone=keys.phone_canonical,  # canonical E.164 -> consistent phone_normalized
        national_id=keys.national_id_raw,
        date_of_birth=identity.get("date_of_birth"),
        no_email=bool(identity.get("no_email", False)),
        created_by=_actor(user),
        updated_by=_actor(user),
        is_active=True,
        **fields,
    )
    if keys.passport_raw:
        guest.document_type = DocumentType.PASSPORT
        guest.document_number = keys.passport_raw

    try:
        with transaction.atomic():  # mandatory savepoint so PG keeps the outer txn
            guest.save()
    except IntegrityError:
        winner = _resolve_race_winner(hotel, keys=keys, user=user)
        if winner is not None:
            return winner
        raise  # not a resolvable identity race — surface the real error
    record_guest_created(guest, user=user)
    return guest


def _resolve_race_winner(hotel, *, keys: NormalizedIdentity, user):
    """After a create IntegrityError, re-run search + classify and honor the
    verdict: reuse a single winner, or raise :class:`GuestIdentityConflict` for a
    conflict/ambiguous outcome. Returns ``None`` only when nothing matched (the
    caller then re-raises the original IntegrityError)."""
    verdict = classify_matches(_search(hotel, keys))
    if verdict.kind == SINGLE and verdict.guest is not None:
        return _reuse(verdict.guest, user=user, keys=keys, allow_reactivate=True)
    if verdict.kind in (CONFLICT, MULTIPLE):
        raise GuestIdentityConflict()
    return None


def resolve_or_create_guest(hotel, *, identity: Mapping, user, allow_create: bool = True):
    """Resolve a caller identity to ONE canonical :class:`Guest` for ``hotel``.

    Parameters
    ----------
    hotel:
        The tenant. Every query is scoped to it.
    identity:
        A mapping. Recognized keys: ``national_id``, ``passport`` (passport
        document number), ``phone`` (raw; canonicalized strictly), an optional
        ``guest_id`` (explicit reuse target — must belong to ``hotel``), and the
        profile fields ``full_name``, ``first_name``, ``last_name``,
        ``father_name``, ``mother_name``, ``nationality``, ``gender``, ``email``,
        ``address``, ``no_email`` and ``date_of_birth``. Unknown keys are ignored.
    user:
        The acting user (recorded as ``created_by`` / ``updated_by`` and audit
        actor). May be an unauthenticated/anonymous user on the public path.
    allow_create:
        ``True`` (authenticated paths) may create a new guest and reactivate an
        inactive match. ``False`` (public path) never creates and never
        reactivates.

    Returns
    -------
    Guest
        The resolved / created / reactivated central guest.
    None
        Only when ``allow_create=False`` AND no LIVE central guest can be linked
        (no match, or the sole match is a hotel-deactivated profile). The caller
        keeps its own snapshot; there is no central guest yet.

    Raises
    ------
    rest_framework.exceptions.ValidationError
        Uninterpretable phone (code ``invalid_phone``) or an unknown
        ``guest_id`` (code ``invalid_guest``).
    GuestBlocked (409, ``guest_blocked``)
        The identity fingerprint (national id / passport / canonical phone) or the
        explicit reuse target is blocked in this hotel. Carries no reason.
    GuestIdentityConflict (409, ``guest_identity_conflict``)
        Strong id vs phone (or strong vs strong) point at different guests, or the
        match is otherwise ambiguous. NO side effects — nothing is created,
        chosen, reactivated, or merged. No merge path this round.
    """
    keys = _normalize_identity(hotel, identity)

    with transaction.atomic():
        # Ban check FIRST, before any create/reuse/reactivate.
        _ensure_not_banned_by_keys(hotel, keys)

        # Explicit reuse target wins over discovery (still ban-re-asserted).
        guest_id = _coerce_guest_id(identity.get("guest_id"))
        if guest_id is not None:
            target = Guest.objects.filter(hotel=hotel, pk=guest_id).first()
            if target is None:
                raise ValidationError(
                    {
                        "guest_id": [
                            ErrorDetail(
                                "No such guest in this hotel.", code="invalid_guest"
                            )
                        ]
                    }
                )
            return _reuse(
                target, user=user, keys=keys, allow_reactivate=allow_create
            )

        verdict = classify_matches(_search(hotel, keys))
        if verdict.kind in (CONFLICT, MULTIPLE):
            raise GuestIdentityConflict()
        if verdict.kind == SINGLE and verdict.guest is not None:
            return _reuse(
                verdict.guest, user=user, keys=keys, allow_reactivate=allow_create
            )

        # NONE.
        if not allow_create:
            return None
        return _create(hotel, identity=identity, keys=keys, user=user)
