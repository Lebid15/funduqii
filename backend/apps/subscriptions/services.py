"""Subscription lifecycle services — the backend source of truth for billing state.

Rules enforced here (not in views, so every caller is protected):
- A hotel may hold at most ONE live (trial/active/past_due) subscription.
- The free trial is granted only ONCE per hotel — the first time — and is never
  re-granted automatically after it ends.
- Status changes go through explicit, auditable transitions.
- Every subscription captures a PLAN SNAPSHOT (grandfathering): a running
  subscription reads its terms from the snapshot, never from the live plan.

Every state change runs inside a transaction. No external calls are made.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.exceptions import (
    ConflictingSubscription,
    DuplicatePaymentReference,
    InvalidAmount,
    InvalidSubscriptionTransition,
    TrialAlreadyUsed,
    VoidReasonRequired,
)

from .models import (
    LIVE_STATUSES,
    BillingCycle,
    HotelSubscription,
    PlatformSubscriptionPayment,
    SubscriptionPlan,
    SubscriptionStatus,
)

#: Stable event vocabulary emitted for the platform + the NOTIFICATIONS module.
#: This is the CONTRACT the (next) notifications closure consumes — do not
#: rename without updating that consumer. Hotel-scoped ``subscription.*`` events
#: are emitted live via ``record_activity`` (category ``system`` -> the hotel's
#: managers). The ``plan.*`` catalog events and the time-based reminders
#: (``subscription.trial_will_end`` / ``subscription.ending_soon``) are
#: catalog/scheduler concerns with no per-hotel recipient today: their NAMES and
#: payload shape are fixed here so the notifications module can wire them, but
#: no scheduler is added this round.
SUBSCRIPTION_EVENT_TYPES = (
    # Catalog (platform-level; no per-hotel recipient — contract only)
    "plan.created",
    "plan.updated",
    "plan.activated",
    "plan.deactivated",
    # Hotel-scoped subscription lifecycle (emitted live)
    "subscription.trial_started",
    "subscription.activated",
    "subscription.renewed",
    "subscription.extended",
    "subscription.plan_changed",
    "subscription.cancelled",
    "subscription.expired",
    "subscription.reactivated",
    "subscription.payment_recorded",
    "subscription.payment_voided",
    # Reserved for the notifications module (time-based; no scheduler yet)
    "subscription.restricted",
    "subscription.trial_will_end",
    "subscription.ending_soon",
)


def _record_platform_event(hotel, *, event_type: str, title: str, message="",
                           actor=None, related_object=None, metadata=None) -> None:
    """Phase 16: surface a platform action inside the hotel's activity feed.

    Lazy import (Phase 14 pattern). Category `system` -> the hotel's managers
    only. No external channel of any kind exists. ``metadata`` carries the
    event contract fields (subscription id, old/new plan, statuses, period,
    reason, payment reference) — scrubbed of secrets by the notifications layer.
    """
    from apps.notifications.services import notify_platform_owners, record_activity

    # Hotel side: the hotel's managers see it (category `system`).
    record_activity(
        hotel,
        event_type=event_type,
        title=title,
        message=message,
        actor=actor,
        related_object=related_object,
        metadata=metadata or {},
    )
    # Platform side (notifications closure): a SEPARATE platform-scoped event so
    # the platform owner is notified of every subscription lifecycle change. The
    # link opens the hotel inside the owner panel. Distinct transitions each
    # notify (the subscription services already guard against double
    # transitions), so no static dedup_key is used here.
    notify_platform_owners(
        event_type=event_type,
        title=title,
        message=message,
        hotel=hotel,
        related_url=f"/platform/hotels/{hotel.id}",
        metadata=metadata or {},
        actor=actor,
    )


# Paid-subscription default lengths by billing cycle (custom => open-ended
# unless an explicit end date is supplied by the caller).
_CYCLE_DAYS = {
    BillingCycle.MONTHLY: 30,
    BillingCycle.YEARLY: 365,
}


# --- Plan snapshot (grandfathering) ------------------------------------------


def build_plan_snapshot(plan: SubscriptionPlan) -> dict:
    """Freeze a plan's terms onto a subscription at the moment it begins.

    Decimals are stored as strings (JSON-safe, no float drift). Read back with
    :func:`subscription_terms`.
    """
    return {
        "plan_id": plan.id,
        "plan_name": plan.name,
        "billing_cycle": plan.billing_cycle,
        "price": str(plan.price),
        "price_yearly": (
            str(plan.price_yearly) if plan.price_yearly is not None else None
        ),
        "currency": plan.currency,
        "room_limit": plan.room_limit,
        "user_limit": plan.user_limit,
        "feature_codes": list(plan.feature_codes or []),
        "max_public_bookings_per_month": plan.max_public_bookings_per_month,
        "trial_days": plan.trial_days,
        "captured_at": timezone.now().isoformat(),
    }


def subscription_terms(sub: HotelSubscription) -> dict:
    """The EFFECTIVE terms of a subscription: its frozen snapshot when present,
    else a live-plan fallback for legacy rows created before snapshots (the
    migration backfills those, so the fallback is only a safety net)."""
    if sub.plan_snapshot:
        return sub.plan_snapshot
    return build_plan_snapshot(sub.plan)


def get_current_subscription(hotel) -> HotelSubscription | None:
    """Return the hotel's single live subscription, if any."""
    return (
        HotelSubscription.objects.filter(hotel=hotel, status__in=list(LIVE_STATUSES))
        .select_related("plan")
        .first()
    )


def _lock_current_subscription(hotel) -> HotelSubscription | None:
    """Row-lock the hotel's live subscription for the current transaction so
    concurrent lifecycle actions (renew / change plan / reactivate) serialize.

    On PostgreSQL (prod) ``select_for_update`` blocks the second writer until
    the first commits; on SQLite (dev/tests) it is a no-op, so the single-live
    DB constraint remains the ultimate guarantee.
    """
    return (
        HotelSubscription.objects.select_for_update()
        .filter(hotel=hotel, status__in=list(LIVE_STATUSES))
        .select_related("plan")
        .first()
    )


def hotel_has_used_trial(hotel) -> bool:
    """True if the hotel has ever been granted a trial (even an expired one).

    A trial is identifiable by a set ``trial_ends_at``; it survives expiry and
    cancellation, so the one-time rule holds forever.
    """
    return HotelSubscription.objects.filter(
        hotel=hotel, trial_ends_at__isnull=False
    ).exists()


@transaction.atomic
def start_trial(
    hotel,
    plan: SubscriptionPlan,
    *,
    trial_days: int | None = None,
    notes: str = "",
) -> HotelSubscription:
    """Grant the one-time free trial to a hotel.

    Raises :class:`TrialAlreadyUsed` if the hotel already consumed its trial, or
    :class:`ConflictingSubscription` if it already has a live subscription.

    Phase 16 tightening (per the phase order): the free trial can ONLY be the
    hotel's FIRST subscription — a hotel with any previous subscription
    (paid, expired or cancelled) is refused even if it never had a trial.
    """
    if hotel_has_used_trial(hotel):
        raise TrialAlreadyUsed()
    if get_current_subscription(hotel) is not None:
        raise ConflictingSubscription()
    if HotelSubscription.objects.filter(hotel=hotel).exists():
        raise TrialAlreadyUsed(
            "The free trial can only be granted as the hotel's first subscription."
        )

    effective_days = trial_days if trial_days is not None else plan.trial_days
    now = timezone.now()
    try:
        sub = HotelSubscription.objects.create(
            hotel=hotel,
            plan=plan,
            status=SubscriptionStatus.TRIAL,
            starts_at=now,
            trial_ends_at=now + timedelta(days=effective_days),
            plan_snapshot=build_plan_snapshot(plan),
            notes=notes,
        )
    except IntegrityError:
        # A concurrent activation won the single-live slot first.
        raise ConflictingSubscription()
    _record_platform_event(
        hotel,
        event_type="subscription.trial_started",
        title=f"Free trial started on plan {plan.name}",
        message=f"Trial ends {sub.trial_ends_at:%Y-%m-%d}.",
        related_object=sub,
        metadata={
            "subscription_id": sub.id,
            "new_plan": plan.name,
            "new_status": sub.status,
            "trial_ends_at": sub.trial_ends_at.isoformat(),
        },
    )
    return sub


@transaction.atomic
def activate_subscription(
    hotel,
    plan: SubscriptionPlan,
    *,
    starts_at=None,
    ends_at=None,
    notes: str = "",
    _event: str = "subscription.activated",
) -> HotelSubscription:
    """Manually activate a paid subscription for a hotel.

    If the hotel currently holds a live subscription (e.g. a running trial), it
    is cancelled first so there is never more than one live subscription — this
    is the trial->paid upgrade path. The subscription freezes the plan snapshot.
    """
    current = _lock_current_subscription(hotel)
    old_status = current.status if current is not None else None
    if current is not None:
        _terminate(current, SubscriptionStatus.CANCELLED)

    now = timezone.now()
    start = starts_at or now
    if ends_at is None:
        cycle_days = _CYCLE_DAYS.get(plan.billing_cycle)
        ends_at = start + timedelta(days=cycle_days) if cycle_days else None

    try:
        sub = HotelSubscription.objects.create(
            hotel=hotel,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            starts_at=start,
            ends_at=ends_at,
            plan_snapshot=build_plan_snapshot(plan),
            notes=notes,
        )
    except IntegrityError:
        # Concurrent activation already holds the single-live slot.
        raise ConflictingSubscription()
    _record_platform_event(
        hotel,
        event_type=_event,
        title=f"Subscription activated on plan {plan.name}",
        message=(f"Valid until {ends_at:%Y-%m-%d}." if ends_at else ""),
        related_object=sub,
        metadata={
            "subscription_id": sub.id,
            "new_plan": plan.name,
            "old_status": old_status,
            "new_status": sub.status,
            "ends_at": ends_at.isoformat() if ends_at else None,
        },
    )
    return sub


@transaction.atomic
def reactivate_subscription(
    hotel,
    plan: SubscriptionPlan,
    *,
    starts_at=None,
    ends_at=None,
    notes: str = "",
) -> HotelSubscription:
    """Explicitly revive billing for a hotel whose subscription has ENDED.

    Terminal subscriptions are never flipped back to active in place — a NEW
    subscription is created with a fresh snapshot while the old row is preserved
    for history. Requires prior subscription history and no live subscription.
    """
    if get_current_subscription(hotel) is not None:
        raise ConflictingSubscription()
    if not HotelSubscription.objects.filter(hotel=hotel).exists():
        # Nothing to reactivate — the first subscription uses activate/trial.
        raise InvalidSubscriptionTransition()
    return activate_subscription(
        hotel,
        plan,
        starts_at=starts_at,
        ends_at=ends_at,
        notes=notes,
        _event="subscription.reactivated",
    )


def _classify_change(old_terms: dict, new_plan: SubscriptionPlan) -> str:
    """upgrade / downgrade / lateral_change — by room limit first, then price.

    ``None`` room_limit means UNLIMITED (ranks highest).
    """
    def rank(limit):
        return float("inf") if limit is None else limit

    old_rooms = rank(old_terms.get("room_limit"))
    new_rooms = rank(new_plan.room_limit)
    if new_rooms > old_rooms:
        return "upgrade"
    if new_rooms < old_rooms:
        return "downgrade"
    # Same room capacity -> decide by price.
    from decimal import Decimal

    old_price = Decimal(str(old_terms.get("price") or "0"))
    if new_plan.price > old_price:
        return "upgrade"
    if new_plan.price < old_price:
        return "downgrade"
    return "lateral_change"


@transaction.atomic
def change_subscription_plan(
    hotel,
    new_plan: SubscriptionPlan,
    *,
    actor=None,
    reason: str = "",
    notes: str = "",
) -> HotelSubscription:
    """Explicitly move a live subscription to a different plan.

    Immediate for both upgrade and downgrade (billing is manual, no proration).
    The old subscription is terminated (history preserved) and a NEW active
    subscription is created with the new plan's snapshot. Existing resources are
    GRANDFATHERED — nothing is deleted or disabled; the entitlement gate simply
    blocks NEW resources above the new limits. Never creates a trial.
    """
    current = _lock_current_subscription(hotel)
    if current is None:
        raise InvalidSubscriptionTransition()
    old_terms = subscription_terms(current)
    old_plan_name = current.plan.name
    change_type = _classify_change(old_terms, new_plan)

    _terminate(current, SubscriptionStatus.CANCELLED)

    now = timezone.now()
    cycle_days = _CYCLE_DAYS.get(new_plan.billing_cycle)
    ends_at = now + timedelta(days=cycle_days) if cycle_days else None
    try:
        new_sub = HotelSubscription.objects.create(
            hotel=hotel,
            plan=new_plan,
            status=SubscriptionStatus.ACTIVE,
            starts_at=now,
            ends_at=ends_at,
            plan_snapshot=build_plan_snapshot(new_plan),
            notes=notes,
        )
    except IntegrityError:
        raise ConflictingSubscription()
    _record_platform_event(
        hotel,
        event_type="subscription.plan_changed",
        title=f"Subscription plan changed to {new_plan.name}",
        message=f"{change_type}: {old_plan_name} -> {new_plan.name}",
        actor=actor,
        related_object=new_sub,
        metadata={
            "subscription_id": new_sub.id,
            "old_plan": old_plan_name,
            "new_plan": new_plan.name,
            "change_type": change_type,
            "reason": reason,
            "new_status": new_sub.status,
            "ends_at": ends_at.isoformat() if ends_at else None,
        },
    )
    return new_sub


def _terminate(sub: HotelSubscription, status: str) -> HotelSubscription:
    now = timezone.now()
    sub.status = status
    if status == SubscriptionStatus.CANCELLED:
        sub.cancelled_at = now
    if sub.ends_at is None or sub.ends_at > now:
        sub.ends_at = now
    sub.save(update_fields=["status", "cancelled_at", "ends_at", "updated_at"])
    return sub


@transaction.atomic
def cancel_subscription(sub: HotelSubscription) -> HotelSubscription:
    """Cancel a subscription. Only a live subscription can be cancelled."""
    sub = HotelSubscription.objects.select_for_update().get(pk=sub.pk)
    if not sub.is_live:
        raise InvalidSubscriptionTransition()
    plan_name = sub.plan.name
    sub = _terminate(sub, SubscriptionStatus.CANCELLED)
    _record_platform_event(
        sub.hotel,
        event_type="subscription.cancelled",
        title=f"Subscription on plan {plan_name} was cancelled",
        related_object=sub,
        metadata={
            "subscription_id": sub.id,
            "old_plan": plan_name,
            "new_status": sub.status,
        },
    )
    return sub


@transaction.atomic
def expire_subscription(sub: HotelSubscription) -> HotelSubscription:
    """Mark a subscription expired. Only a live subscription can expire."""
    sub = HotelSubscription.objects.select_for_update().get(pk=sub.pk)
    if not sub.is_live:
        raise InvalidSubscriptionTransition()
    plan_name = sub.plan.name
    sub = _terminate(sub, SubscriptionStatus.EXPIRED)
    _record_platform_event(
        sub.hotel,
        event_type="subscription.expired",
        title=f"Subscription on plan {plan_name} expired",
        message="Important operations are restricted until a new subscription is activated.",
        related_object=sub,
        metadata={
            "subscription_id": sub.id,
            "old_plan": plan_name,
            "new_status": sub.status,
        },
    )
    return sub


@transaction.atomic
def renew_subscription(
    sub: HotelSubscription,
    *,
    ends_at=None,
    days: int | None = None,
    notes: str = "",
    kind: str = "renew",
) -> HotelSubscription:
    """Extend a subscription's end date (Phase 16). NEVER automatic.

    Renewal applies to a live ACTIVE/PAST_DUE subscription (a trial is upgraded
    via activate, not renewed). Row-locked and re-checked under the lock so a
    concurrent double submit cannot corrupt the state. An explicit ``ends_at``
    is idempotent (the same target twice sets the same date); ``days`` is
    relative, then the plan's billing cycle. ``kind='extend'`` emits the
    ``subscription.extended`` event instead of ``subscription.renewed``.
    """
    sub = HotelSubscription.objects.select_for_update().select_related("plan").get(
        pk=sub.pk
    )
    if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE):
        raise InvalidSubscriptionTransition()

    now = timezone.now()
    base = sub.ends_at if sub.ends_at and sub.ends_at > now else now
    if ends_at is None:
        extend_days = days or _CYCLE_DAYS.get(sub.plan.billing_cycle) or 30
        ends_at = base + timedelta(days=extend_days)
    if ends_at <= now:
        raise InvalidSubscriptionTransition()

    old_ends_at = sub.ends_at
    sub.status = SubscriptionStatus.ACTIVE
    sub.ends_at = ends_at
    if notes:
        sub.notes = f"{sub.notes}\n{notes}".strip()
    sub.save(update_fields=["status", "ends_at", "notes", "updated_at"])
    event_type = (
        "subscription.extended" if kind == "extend" else "subscription.renewed"
    )
    _record_platform_event(
        sub.hotel,
        event_type=event_type,
        title=f"Subscription on plan {sub.plan.name} {kind}ed",
        message=f"Valid until {ends_at:%Y-%m-%d}.",
        related_object=sub,
        metadata={
            "subscription_id": sub.id,
            "new_plan": sub.plan.name,
            "old_period_end": old_ends_at.isoformat() if old_ends_at else None,
            "new_period_end": ends_at.isoformat(),
        },
    )
    return sub


# --- Manual platform payments (Phase 16 — NOT a payment gateway) -------------


@transaction.atomic
def record_platform_payment(
    hotel,
    *,
    amount,
    currency: str,
    method: str,
    subscription: HotelSubscription | None = None,
    reference: str = "",
    note: str = "",
    received_at=None,
    recorded_by=None,
) -> PlatformSubscriptionPayment:
    """Record a MANUAL subscription payment (cash/bank transfer/manual note).

    Platform money is fully separate from hotel finance: no Folio, no hotel
    Payment/Invoice, no taxes. Decimal only; void instead of delete. When a
    ``reference`` is supplied it must be unique for the hotel among non-voided
    payments — the hotel row is locked so the check + insert is atomic against
    concurrent same-reference submits.
    """
    if amount is None or amount <= 0:
        raise InvalidAmount()
    if subscription is not None and subscription.hotel_id != hotel.id:
        raise InvalidSubscriptionTransition()

    reference = (reference or "").strip()
    if reference:
        # Lock the hotel row to serialize concurrent same-reference records.
        from apps.tenancy.models import Hotel

        Hotel.objects.select_for_update().filter(pk=hotel.id).first()
        if PlatformSubscriptionPayment.objects.filter(
            hotel=hotel, reference=reference, voided_at__isnull=True
        ).exists():
            raise DuplicatePaymentReference()

    payment = PlatformSubscriptionPayment.objects.create(
        hotel=hotel,
        subscription=subscription,
        amount=amount,
        currency=(currency or "USD").upper(),
        method=method,
        reference=reference,
        note=note,
        received_at=received_at or timezone.now(),
        recorded_by=recorded_by,
    )
    _record_platform_event(
        hotel,
        event_type="subscription.payment_recorded",
        title=f"Subscription payment recorded: {payment.amount} {payment.currency}",
        message=f"Method: {payment.method}." + (f" Ref: {reference}." if reference else ""),
        actor=recorded_by,
        related_object=payment,
        metadata={
            "payment_id": payment.id,
            "subscription_id": subscription.id if subscription else None,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "method": payment.method,
            "payment_reference": reference or None,
        },
    )
    return payment


@transaction.atomic
def void_platform_payment(
    payment: PlatformSubscriptionPayment, *, reason: str, actor=None
) -> PlatformSubscriptionPayment:
    """Void (never delete) a manual platform payment. Idempotent-safe: a
    voided payment cannot be voided again."""
    if not (reason or "").strip():
        raise VoidReasonRequired()
    payment = PlatformSubscriptionPayment.objects.select_for_update().get(
        pk=payment.pk
    )
    if payment.is_voided:
        raise InvalidSubscriptionTransition()
    payment.voided_at = timezone.now()
    payment.void_reason = reason.strip()[:255]
    payment.save(update_fields=["voided_at", "void_reason", "updated_at"])
    _record_platform_event(
        payment.hotel,
        event_type="subscription.payment_voided",
        title=f"Subscription payment voided: {payment.amount} {payment.currency}",
        message=payment.void_reason,
        actor=actor,
        related_object=payment,
        metadata={
            "payment_id": payment.id,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "reason": payment.void_reason,
        },
    )
    return payment
