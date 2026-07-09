"""Subscription lifecycle services — the backend source of truth for billing state.

Rules enforced here (not in views, so every caller is protected):
- A hotel may hold at most ONE live (trial/active/past_due) subscription.
- The free trial is granted only ONCE per hotel — the first time — and is never
  re-granted automatically after it ends.
- Status changes go through explicit, auditable transitions.

Every state change runs inside a transaction. No external calls are made.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import (
    ConflictingSubscription,
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


def _record_platform_event(hotel, *, event_type: str, title: str, message="",
                           actor=None, related_object=None) -> None:
    """Phase 16: surface a platform action inside the hotel's activity feed.

    Lazy import (Phase 14 pattern). Category `system` → the hotel's managers
    only. No external channel of any kind exists.
    """
    from apps.notifications.services import record_activity

    record_activity(
        hotel,
        event_type=event_type,
        title=title,
        message=message,
        actor=actor,
        related_object=related_object,
    )

# Paid-subscription default lengths by billing cycle (custom => open-ended
# unless an explicit end date is supplied by the caller).
_CYCLE_DAYS = {
    BillingCycle.MONTHLY: 30,
    BillingCycle.YEARLY: 365,
}


def get_current_subscription(hotel) -> HotelSubscription | None:
    """Return the hotel's single live subscription, if any."""
    return (
        HotelSubscription.objects.filter(hotel=hotel, status__in=list(LIVE_STATUSES))
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
    sub = HotelSubscription.objects.create(
        hotel=hotel,
        plan=plan,
        status=SubscriptionStatus.TRIAL,
        starts_at=now,
        trial_ends_at=now + timedelta(days=effective_days),
        notes=notes,
    )
    _record_platform_event(
        hotel,
        event_type="subscription.trial_started",
        title=f"Free trial started on plan {plan.name}",
        message=f"Trial ends {sub.trial_ends_at:%Y-%m-%d}.",
        related_object=sub,
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
) -> HotelSubscription:
    """Manually activate a paid subscription for a hotel.

    If the hotel currently holds a live subscription (e.g. a running trial), it
    is cancelled first so there is never more than one live subscription — this
    is the trial→paid upgrade path.
    """
    current = get_current_subscription(hotel)
    if current is not None:
        _terminate(current, SubscriptionStatus.CANCELLED)

    now = timezone.now()
    start = starts_at or now
    if ends_at is None:
        cycle_days = _CYCLE_DAYS.get(plan.billing_cycle)
        ends_at = start + timedelta(days=cycle_days) if cycle_days else None

    sub = HotelSubscription.objects.create(
        hotel=hotel,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        starts_at=start,
        ends_at=ends_at,
        notes=notes,
    )
    _record_platform_event(
        hotel,
        event_type="subscription.activated",
        title=f"Subscription activated on plan {plan.name}",
        message=(f"Valid until {ends_at:%Y-%m-%d}." if ends_at else ""),
        related_object=sub,
    )
    return sub


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
    if not sub.is_live:
        raise InvalidSubscriptionTransition()
    sub = _terminate(sub, SubscriptionStatus.CANCELLED)
    _record_platform_event(
        sub.hotel,
        event_type="subscription.cancelled",
        title=f"Subscription on plan {sub.plan.name} was cancelled",
        related_object=sub,
    )
    return sub


@transaction.atomic
def expire_subscription(sub: HotelSubscription) -> HotelSubscription:
    """Mark a subscription expired. Only a live subscription can expire."""
    if not sub.is_live:
        raise InvalidSubscriptionTransition()
    sub = _terminate(sub, SubscriptionStatus.EXPIRED)
    _record_platform_event(
        sub.hotel,
        event_type="subscription.expired",
        title=f"Subscription on plan {sub.plan.name} expired",
        message="Important operations are restricted until a new subscription is activated.",
        related_object=sub,
    )
    return sub


@transaction.atomic
def renew_subscription(
    sub: HotelSubscription,
    *,
    ends_at=None,
    days: int | None = None,
    notes: str = "",
) -> HotelSubscription:
    """Extend a subscription's end date (Phase 16). NEVER automatic.

    Renewal applies to a live ACTIVE/PAST_DUE subscription (a trial is upgraded
    via activate, not renewed). The extension starts from the later of now and
    the current end so history is never rewritten: an explicit ``ends_at``
    wins, then ``days``, then the plan's billing cycle.
    """
    if sub.status not in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE):
        raise InvalidSubscriptionTransition()

    now = timezone.now()
    base = sub.ends_at if sub.ends_at and sub.ends_at > now else now
    if ends_at is None:
        extend_days = days or _CYCLE_DAYS.get(sub.plan.billing_cycle) or 30
        ends_at = base + timedelta(days=extend_days)
    if ends_at <= now:
        raise InvalidSubscriptionTransition()

    sub.status = SubscriptionStatus.ACTIVE
    sub.ends_at = ends_at
    if notes:
        sub.notes = f"{sub.notes}\n{notes}".strip()
    sub.save(update_fields=["status", "ends_at", "notes", "updated_at"])
    _record_platform_event(
        sub.hotel,
        event_type="subscription.renewed",
        title=f"Subscription on plan {sub.plan.name} renewed",
        message=f"Valid until {ends_at:%Y-%m-%d}.",
        related_object=sub,
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
    Payment/Invoice, no taxes. Decimal only; void instead of delete.
    """
    if amount is None or amount <= 0:
        raise InvalidAmount()
    if subscription is not None and subscription.hotel_id != hotel.id:
        raise InvalidSubscriptionTransition()
    return PlatformSubscriptionPayment.objects.create(
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


@transaction.atomic
def void_platform_payment(
    payment: PlatformSubscriptionPayment, *, reason: str
) -> PlatformSubscriptionPayment:
    """Void (never delete) a manual platform payment. Idempotent-safe: a
    voided payment cannot be voided again."""
    if not (reason or "").strip():
        raise VoidReasonRequired()
    if payment.is_voided:
        raise InvalidSubscriptionTransition()
    payment.voided_at = timezone.now()
    payment.void_reason = reason.strip()[:255]
    payment.save(update_fields=["voided_at", "void_reason", "updated_at"])
    return payment
