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
    InvalidSubscriptionTransition,
    TrialAlreadyUsed,
)

from .models import (
    LIVE_STATUSES,
    BillingCycle,
    HotelSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
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
    """
    if hotel_has_used_trial(hotel):
        raise TrialAlreadyUsed()
    if get_current_subscription(hotel) is not None:
        raise ConflictingSubscription()

    effective_days = trial_days if trial_days is not None else plan.trial_days
    now = timezone.now()
    return HotelSubscription.objects.create(
        hotel=hotel,
        plan=plan,
        status=SubscriptionStatus.TRIAL,
        starts_at=now,
        trial_ends_at=now + timedelta(days=effective_days),
        notes=notes,
    )


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

    return HotelSubscription.objects.create(
        hotel=hotel,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        starts_at=start,
        ends_at=ends_at,
        notes=notes,
    )


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
    return _terminate(sub, SubscriptionStatus.CANCELLED)


@transaction.atomic
def expire_subscription(sub: HotelSubscription) -> HotelSubscription:
    """Mark a subscription expired. Only a live subscription can expire."""
    if not sub.is_live:
        raise InvalidSubscriptionTransition()
    return _terminate(sub, SubscriptionStatus.EXPIRED)
