"""Guest extra-services domain services — the single write path for posting a
catalog service to a stay's folio, plus the read-only folio-directory query.

Money is NEVER mutated here directly: the flow resolves the server-side price/tax
and delegates the ONE ledger write to ``apps.finance.services.add_charge`` (there
is no second ledger, no direct payment). Prices/tax are FROZEN onto the charge's
snapshot columns so a later catalog reprice never alters a posted charge.

Lock order (#9) — adopted from the rest of the codebase (check-in, check-out,
``ensure_stay_folio``, ``post_order_to_folio``, the daily close): lock the STAY
row FIRST (``select_for_update``), re-check ``status == in_house`` under the lock,
THEN ``ensure_stay_folio`` (which re-locks the stay and locks the folio via
``add_charge``). NEVER folio-before-stay — so add-service and check-out serialize
on the same stay row and can never deadlock or lose a charge.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.common.exceptions import (
    CrossTenantReference,
    FolioClosed,
    FolioCurrencyMismatch,
    IdempotencyKeyConflict,
    InvalidAmount,
    PermissionDenied,
    StayNotInHouse,
)
from apps.rbac.services import has_hotel_permission

from .exceptions import GuestServiceInactive, VariablePriceReasonRequired
from .models import GuestServicePosting, PricingMode

ZERO = Decimal("0.00")
#: A safe upper bound on the posted quantity (well within ``FolioCharge.quantity``'s
#: 8-digit / 2-dp column). The amount itself is additionally bounded by finance's
#: ``MONEY_MAX_ABS`` inside ``add_charge``.
QUANTITY_MAX = Decimal("100000")


def _actor(user):
    return user if getattr(user, "is_authenticated", False) else None


# --- Idempotency fingerprint --------------------------------------------------


def build_request_fingerprint(
    service, *, stay_id, quantity, unit_price_override=None, reason=None
) -> str:
    """A stable sha256 hex over ONLY the salient client-supplied request fields —
    ``{stay_id, service_id, quantity (normalized), variable unit_price (only when
    an override is actually applied), reason (trimmed + case-folded)}``. It
    EXCLUDES the server-derived tax_rate/total, so an identical business request
    always produces the same fingerprint and a materially different one differs.

    The variable price is folded in ONLY for a VARIABLE service with an override
    present (for a FIXED service the override is ignored, so it never affects the
    fingerprint)."""
    from apps.finance.services import money

    override = (
        money(unit_price_override)
        if (
            service.pricing_mode == PricingMode.VARIABLE
            and unit_price_override is not None
        )
        else None
    )
    payload = {
        "stay": stay_id,
        "service": service.pk,
        "quantity": str(money(quantity)),
        "unit_price": (str(override) if override is not None else None),
        "reason": (reason or "").strip().casefold(),
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_same_request(posting: GuestServicePosting, fingerprint: str) -> None:
    """Reject a replayed key whose payload fingerprint differs from the stored one
    (a stored/incoming empty fingerprint is treated as unknown and never
    conflicts — same rule as the reservations idempotency path)."""
    stored = posting.request_fingerprint or ""
    if stored and fingerprint and stored != fingerprint:
        raise IdempotencyKeyConflict()


# --- Price / quantity resolution ---------------------------------------------


def _normalize_quantity(quantity) -> Decimal:
    from apps.finance.services import money

    qty = money(quantity)
    if qty <= ZERO:
        raise InvalidAmount({"field": "quantity", "reason": "must_be_positive"})
    if qty > QUANTITY_MAX:
        raise InvalidAmount({"field": "quantity", "reason": "too_large"})
    return qty


def _resolve_unit_price(service, unit_price_override, reason, *, user, hotel) -> Decimal:
    """The SERVER-side unit price for a posting.

    * FIXED service, or VARIABLE with no override -> the catalog ``unit_price``
      (any client-sent price on a FIXED service is IGNORED — the catalog wins).
    * VARIABLE service WITH an override -> the override, but ONLY when the caller
      holds ``finance.charge_create`` (else refuse) and supplies a reason; the
      value is re-validated server-side (non-negative, within ``MONEY_MAX_ABS``).
    """
    from apps.finance.services import MONEY_MAX_ABS, money

    if service.pricing_mode == PricingMode.VARIABLE and unit_price_override is not None:
        if not has_hotel_permission(user, hotel, "finance.charge_create"):
            raise PermissionDenied()
        if not (reason or "").strip():
            raise VariablePriceReasonRequired()
        price = money(unit_price_override)
        if price < ZERO:
            raise InvalidAmount(
                {"field": "unit_price", "reason": "must_not_be_negative"}
            )
        if abs(price) >= MONEY_MAX_ABS:
            raise InvalidAmount({"field": "unit_price", "reason": "amount_too_large"})
        return price
    return money(service.unit_price)


# --- Add-service flow ---------------------------------------------------------


@transaction.atomic
def add_guest_service_to_stay(
    hotel,
    *,
    stay,
    service,
    quantity,
    user,
    idempotency_key,
    request_fingerprint,
    unit_price_override=None,
    reason=None,
) -> GuestServicePosting:
    """Post ONE catalog service to a stay's OPEN folio as a single SERVICE charge,
    atomically and idempotently. Returns the (new or existing) GuestServicePosting.

    Refuses (no side effect) when: the service/stay is cross-tenant, the service is
    inactive, the quantity is non-positive/too large, the stay is not in-house, the
    folio is closed, the service currency differs from the folio currency, a FIXED
    override is attempted without ``finance.charge_create``, or a variable override
    lacks a reason. ``source`` is server-set to ``guest_extra_service``; there is
    NO direct payment on this flow.
    """
    from apps.finance.constants import ChargeSource
    from apps.finance.models import ChargeType, FolioStatus
    from apps.finance.services import add_charge, ensure_stay_folio
    from apps.stays.models import Stay, StayStatus

    # Defensive tenant checks (the view already 404s a cross-hotel id).
    if service.hotel_id != hotel.id:
        raise CrossTenantReference({"field": "service"})
    if stay.hotel_id != hotel.id:
        raise CrossTenantReference({"field": "stay"})
    if not service.is_active:
        raise GuestServiceInactive({"service": service.pk})

    key = (idempotency_key or "").strip()

    # (#5) Fast-path replay — a same-key posting already exists: same fingerprint
    # returns it (create NOTHING), a different fingerprint is a 409 with no side
    # effect. This is an optimization; the post-lock re-check below is the
    # authoritative one under concurrency.
    if key:
        existing = GuestServicePosting.objects.filter(
            hotel=hotel, idempotency_key=key
        ).first()
        if existing is not None:
            _assert_same_request(existing, request_fingerprint)
            return existing

    qty = _normalize_quantity(quantity)

    # (#9) Lock the STAY row FIRST; re-check in-house under the lock. ``of=("self",)``
    # locks only the stays row (``reservation`` is a nullable FK — locking the whole
    # OUTER JOIN is rejected on PostgreSQL); mirrors CheckOutService exactly, so the
    # two serialize on this row.
    locked_stay = (
        Stay.objects.select_for_update(of=("self",)).get(pk=stay.pk)
    )
    if locked_stay.status != StayStatus.IN_HOUSE:
        # Post-checkout / not-in-house guard: no new operational charge after
        # departure (corrections are finance-side void/adjust only).
        raise StayNotInHouse({"stay": locked_stay.pk, "status": locked_stay.status})

    # (#5) Authoritative idempotency re-check UNDER the stay lock: a concurrent
    # same-key request for THIS stay serializes here, so the loser now sees the
    # winner's committed posting and returns it (no second charge).
    if key:
        existing = GuestServicePosting.objects.filter(
            hotel=hotel, idempotency_key=key
        ).first()
        if existing is not None:
            _assert_same_request(existing, request_fingerprint)
            return existing

    # Get-or-create the stay's ONE open folio (locks the stay again + the folio via
    # add_charge). Deposit-folio reuse + the per-stay open-folio guard live here;
    # this flow never creates an orphan folio and never touches the general
    # folio-create contract (P5).
    folio = ensure_stay_folio(locked_stay, user=user)
    if folio.status != FolioStatus.OPEN:
        raise FolioClosed({"folio": folio.id, "status": folio.status})

    # Currency guard (#12): the service and the folio must share a currency — no
    # silent FX conversion. Reject on mismatch.
    svc_currency = (service.currency or "").strip().upper()
    folio_currency = (folio.currency or "").strip().upper()
    if svc_currency != folio_currency:
        raise FolioCurrencyMismatch(
            {
                "reason": "guest_service_currency_mismatch",
                "service_currency": svc_currency,
                "folio_currency": folio.currency,
            }
        )

    unit_price = _resolve_unit_price(
        service, unit_price_override, reason, user=user, hotel=hotel
    )
    tax_rate = service.tax_rate

    charge = add_charge(
        folio,
        charge_type=ChargeType.SERVICE,
        description=service.name,
        quantity=qty,
        unit_amount=unit_price,
        tax_rate=tax_rate,
        source=ChargeSource.GUEST_EXTRA_SERVICE,
        currency_snapshot=svc_currency,
        service_name_snapshot=service.name,
        unit_price_snapshot=unit_price,
        tax_rate_snapshot=tax_rate,
        source_reference=f"guest_service:{service.pk}",
        user=user,
    )

    try:
        # Savepoint so a rare cross-request key collision does not poison the outer
        # transaction. Same-stay same-key concurrency is already handled above; this
        # only fires for a key REUSED across a different request (different stay).
        with transaction.atomic():
            posting = GuestServicePosting.objects.create(
                hotel=hotel,
                stay=locked_stay,
                guest_extra_service=service,
                folio_charge=charge,
                idempotency_key=key,
                request_fingerprint=request_fingerprint,
                created_by=_actor(user),
            )
    except IntegrityError:
        # A posting with this idempotency_key already exists for a DIFFERENT
        # request. Abort with a clean 409 — the outer atomic rolls our charge back
        # too, so there is NO orphan charge and NO lost charge.
        raise IdempotencyKeyConflict()

    return posting


# --- Folio directory (read-only, no N+1) -------------------------------------


def guest_folio_directory_queryset(hotel):
    """A fixed-query queryset of the hotel's IN-HOUSE stays for the folio directory
    (P6), annotated with the service line-item count/total and the folio
    balance/payments — all via correlated Subqueries so adding residents never adds
    a query (no N+1). ``room__floor`` is joined (``select_related``) like the guests
    ``current_unit`` pattern.

    ``service_count`` / ``service_total`` count ONLY charges whose ``source`` is in
    the finance SOURCE allowlist ``SERVICE_LINE_SOURCES`` (guest extra services +
    posted service orders) AND ``status == posted`` (voided rows EXCLUDED) — a
    SOURCE allowlist, NOT ``ChargeType``.
    """
    from django.db.models import (
        Count,
        DecimalField,
        IntegerField,
        OuterRef,
        Subquery,
        Sum,
        Value,
    )
    from django.db.models.functions import Coalesce

    from apps.finance.constants import SERVICE_LINE_SOURCES
    from apps.finance.models import Folio, FolioCharge, FolioStatus, Payment, PostingStatus
    from apps.stays.models import Stay, StayStatus

    # TextChoices members are ``str`` subclasses; pass plain strings to ``__in``.
    service_source_values = sorted(str(s) for s in SERVICE_LINE_SOURCES)
    dec = DecimalField(max_digits=14, decimal_places=2)

    def _stay_charges(**extra):
        return FolioCharge.objects.filter(
            folio__stay=OuterRef("pk"), status=PostingStatus.POSTED, **extra
        ).values("folio__stay")

    service_count_sq = _stay_charges(source__in=service_source_values).annotate(
        c=Count("id")
    ).values("c")
    service_total_sq = _stay_charges(source__in=service_source_values).annotate(
        t=Sum("total_amount")
    ).values("t")
    charges_total_sq = _stay_charges().annotate(t=Sum("total_amount")).values("t")
    payments_total_sq = (
        Payment.objects.filter(
            folio__stay=OuterRef("pk"), status=PostingStatus.POSTED
        )
        .values("folio__stay")
        .annotate(t=Sum("amount"))
        .values("t")
    )
    open_folio = Folio.objects.filter(
        stay=OuterRef("pk"), status=FolioStatus.OPEN
    ).order_by("id")

    return (
        Stay.objects.filter(hotel=hotel, status=StayStatus.IN_HOUSE)
        .select_related(
            "room", "room__room_type", "room__floor", "primary_guest"
        )
        .annotate(
            service_count=Coalesce(
                Subquery(service_count_sq, output_field=IntegerField()), Value(0)
            ),
            service_total=Coalesce(
                Subquery(service_total_sq, output_field=dec),
                Value(ZERO, output_field=dec),
            ),
            charges_total=Coalesce(
                Subquery(charges_total_sq, output_field=dec),
                Value(ZERO, output_field=dec),
            ),
            payments_total=Coalesce(
                Subquery(payments_total_sq, output_field=dec),
                Value(ZERO, output_field=dec),
            ),
            open_folio_status=Subquery(open_folio.values("status")[:1]),
            open_folio_currency=Subquery(open_folio.values("currency")[:1]),
        )
        .order_by("room__number", "id")
    )
