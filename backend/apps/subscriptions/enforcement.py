"""Central subscription/suspension enforcement (Phase 16).

ONE backend chokepoint decides whether a hotel may perform important write
operations. Every hotel app's write guard calls :func:`ensure_hotel_operational`
and the public booking switch calls :func:`subscription_blocks_writes` — the
frontend only mirrors the result, it is never the protection.

Rules (documented decisions):
- ``hotel.status == suspended``  → :class:`HotelSuspended` (``hotel_suspended``).
  Suspension wins over subscription state in error reporting.
- A hotel WITH subscription history but WITHOUT an effectively-live
  subscription → :class:`SubscriptionInactive` (``subscription_inactive``).
  "Effectively live" is time-aware because no background job flips statuses:
  a live-status subscription (trial/active/past_due) whose effective end
  (``trial_ends_at`` for trials, ``ends_at`` otherwise) has passed no longer
  counts.
- A hotel with NO subscription records at all is NOT blocked: it has not been
  onboarded to billing yet (legacy/dev/setup tenants). Restriction begins with
  the subscription lifecycle — "after the trial ends", per the phase order.
- Blocking restricts WRITES only. Reads (lists, reports, notifications,
  settings) stay available, and no data is ever deleted.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.common.exceptions import HotelSuspended, SubscriptionInactive
from apps.tenancy.models import HotelStatus

from .models import LIVE_STATUSES, HotelSubscription, SubscriptionStatus

#: Window (days) in which an active subscription counts as "expiring soon".
EXPIRING_SOON_DAYS = 14


def _effective_end(sub: HotelSubscription):
    """The moment a live subscription stops being binding."""
    if sub.status == SubscriptionStatus.TRIAL:
        return sub.trial_ends_at or sub.ends_at
    return sub.ends_at


def effective_status(sub: HotelSubscription, now=None) -> str:
    """The DATE-DERIVED status of a subscription.

    A stored ``trial``/``active``/``past_due`` whose effective end has passed is
    reported as ``expired`` even though no background job rewrote the column.
    Terminal stored statuses (expired/cancelled) are returned as-is. This is the
    single truth every list, counter and banner should display — never the raw
    ``status`` column alone.
    """
    now = now or timezone.now()
    if sub.status in LIVE_STATUSES:
        end = _effective_end(sub)
        if end is not None and end <= now:
            return SubscriptionStatus.EXPIRED
    return sub.status


def effectively_live_q(now=None):
    """A ``Q`` matching subscriptions that are live AND unexpired (time-aware).

    The queryset form of :func:`effective_subscription`, shared by the batch
    block check and the platform counters so "effective" means one thing.
    """
    now = now or timezone.now()
    open_ended = Q(ends_at__isnull=True) | Q(ends_at__gt=now)
    return (
        Q(status=SubscriptionStatus.TRIAL)
        & (Q(trial_ends_at__gt=now) | (Q(trial_ends_at__isnull=True) & open_ended))
    ) | (
        Q(status__in=(SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE))
        & open_ended
    )


def effective_subscription(hotel) -> HotelSubscription | None:
    """The hotel's live AND unexpired subscription, if any (time-aware)."""
    now = timezone.now()
    for sub in (
        HotelSubscription.objects.filter(hotel=hotel, status__in=list(LIVE_STATUSES))
        .select_related("plan")
        .order_by("-created_at")
    ):
        end = _effective_end(sub)
        if end is None or end > now:
            return sub
    return None


def subscription_blocks_writes(hotel) -> bool:
    """True when important writes must be refused for subscription reasons."""
    if effective_subscription(hotel) is not None:
        return False
    # Never-onboarded hotels are not blocked (documented decision).
    return HotelSubscription.objects.filter(hotel=hotel).exists()


def subscription_blocked_hotel_ids(hotel_ids) -> set[int]:
    """Batch form of :func:`subscription_blocks_writes` (Phase 17).

    Answers "which of these hotels are write-blocked?" in TWO queries instead
    of two per hotel — used by list endpoints (e.g. the public hotel list)
    to avoid an N+1 pattern. The rule is IDENTICAL to the per-hotel check:
    blocked = has subscription history AND no effectively-live subscription
    (time-aware, mirroring ``_effective_end``).
    """
    hotel_ids = list(hotel_ids)
    if not hotel_ids:
        return set()
    now = timezone.now()
    with_history = set(
        HotelSubscription.objects.filter(hotel_id__in=hotel_ids)
        .values_list("hotel_id", flat=True)
        .distinct()
    )
    live = set(
        HotelSubscription.objects.filter(hotel_id__in=hotel_ids)
        .filter(effectively_live_q(now))
        .values_list("hotel_id", flat=True)
        .distinct()
    )
    return with_history - live


def ensure_hotel_operational(hotel) -> None:
    """Raise the correct restriction error for important write operations.

    ``hotel_suspended`` when the hotel is suspended (that wins), otherwise
    ``subscription_inactive`` when the subscription no longer permits writes.
    """
    if hotel.status == HotelStatus.SUSPENDED:
        raise HotelSuspended()
    if subscription_blocks_writes(hotel):
        raise SubscriptionInactive()


def subscription_state(hotel) -> dict:
    """The hotel console's view of its own billing state (read-only, safe).

    Powers the Phase 16 banners: active / expiring soon / expired / suspended.
    Exposes no platform internals — only what the hotel needs to understand
    why operations may be restricted.
    """
    now = timezone.now()
    live = effective_subscription(hotel)
    has_history = HotelSubscription.objects.filter(hotel=hotel).exists()
    suspended = hotel.status == HotelStatus.SUSPENDED

    state = {
        "has_subscription": has_history,
        "status": live.status if live else None,
        "effective_status": (
            effective_status(live, now)
            if live is not None
            else (SubscriptionStatus.EXPIRED if has_history else None)
        ),
        "plan_name": live.plan.name if live else None,
        # §8.3 current-subscription card: the live subscription's own dates
        # (read straight from the model — never invented). starts_at/trial_ends_at
        # are null when there is no live subscription or the field is unset (a
        # paid subscription has no trial_ends_at). The days_left calc is
        # unchanged; these are display-only additions.
        "starts_at": (
            live.starts_at.isoformat() if live and live.starts_at else None
        ),
        "trial_ends_at": (
            live.trial_ends_at.isoformat() if live and live.trial_ends_at else None
        ),
        "ends_at": None,
        "days_left": None,
        "expiring_soon": False,
        "expired": has_history and live is None,
        "suspended": suspended,
        "write_blocked": suspended or (has_history and live is None),
        "blocked_reason": (
            "hotel_suspended"
            if suspended
            else ("subscription_inactive" if has_history and live is None else None)
        ),
    }
    if live is not None:
        end = _effective_end(live)
        if end is not None:
            state["ends_at"] = end.isoformat()
            state["days_left"] = max(0, (end - now).days)
            state["expiring_soon"] = end <= now + timedelta(days=EXPIRING_SOON_DAYS)
    return state
