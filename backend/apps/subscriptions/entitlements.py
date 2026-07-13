"""Central subscription ENTITLEMENT gate (subscriptions final closure).

Distinct from :mod:`enforcement`, which answers "may this hotel write at all?"
(active subscription vs suspended). This module answers the SEPARATE question
"is the hotel within its plan's limits / does its plan include a feature?" and
is evaluated AFTER the operational gate and the RBAC permission check:

    1. enforcement.ensure_hotel_operational  -> subscription is live
    2. HasHotelPermission                     -> the user may act (RBAC)
    3. entitlements.check_*_quota / feature   -> the plan allows the resource

Limits read from the subscription's frozen SNAPSHOT (grandfathering), never the
live plan. Existing resources are always kept — the gate only blocks NEW ones.
There are NO hard-coded plan names anywhere here.
"""
from __future__ import annotations

from django.utils import timezone

from apps.common.exceptions import (
    PublicBookingLimitReached,
    RoomLimitReached,
    StaffLimitReached,
)

from .enforcement import _effective_end, effective_subscription
from .models import LIVE_STATUSES, HotelSubscription
from .services import subscription_terms

#: The only feature codes the platform recognises. Feature ENFORCEMENT across
#: sections is deferred (no proven safe map yet); this list backs validation and
#: display. Adding a code here does not gate a section by itself.
OFFICIAL_FEATURES = (
    "restaurant_cafe",
    "advanced_reports",
    "public_booking",
)

#: A usage at or above this fraction of the limit is "nearing".
NEARING_FRACTION = 0.8


# --- Usage counts (single source; reuse existing definitions) ----------------


def room_usage(hotel) -> int:
    """Rooms that count against the plan: non-archived rooms (matches the rooms
    board summary definition — archived rooms never count)."""
    from apps.rooms.models import Room, RoomStatus

    return Room.objects.filter(hotel=hotel).exclude(status=RoomStatus.ARCHIVED).count()


def staff_usage(hotel) -> int:
    """Staff that count against the plan: ACTIVE hotel memberships (managers and
    staff, including the primary manager). Deactivated/deleted never count —
    matches the owner panel's ``staff_count``."""
    return hotel.memberships.filter(is_active=True).count()


def public_booking_usage(hotel) -> int:
    """Public-website bookings CREATED in the hotel's current local month,
    excluding cancelled/expired (non-consumed) ones."""
    from apps.reservations.models import ReservationSource, ReservationStatus
    from apps.shifts.services import get_business_date

    day = get_business_date(hotel)
    from apps.reservations.models import Reservation

    return (
        Reservation.objects.filter(
            hotel=hotel,
            source=ReservationSource.PUBLIC_WEBSITE,
            created_at__year=day.year,
            created_at__month=day.month,
        )
        .exclude(
            status__in=(ReservationStatus.CANCELLED, ReservationStatus.EXPIRED)
        )
        .count()
    )


def usage_state(current: int, limit) -> str:
    """normal | nearing_limit | limit_reached | over_limit. ``limit=None`` means
    unlimited -> always ``normal``."""
    if limit is None:
        return "normal"
    if current > limit:
        return "over_limit"
    if current >= limit:
        return "limit_reached"
    if limit > 0 and current >= NEARING_FRACTION * limit:
        return "nearing_limit"
    return "normal"


# --- Quota gates (block-new, grandfather-existing; row-locked) ----------------


def _locked_effective_subscription(hotel) -> HotelSubscription | None:
    """Row-lock the hotel's live subscriptions and return the effective
    (unexpired) one, so a concurrent create serialises on the same row.

    Must be called inside a transaction (the resource-create path provides it).
    On SQLite ``select_for_update`` is a no-op; on PostgreSQL it blocks the
    second writer until the first commits, so two concurrent creates at the last
    slot cannot both pass.
    """
    now = timezone.now()
    for sub in (
        HotelSubscription.objects.select_for_update()
        .filter(hotel=hotel, status__in=list(LIVE_STATUSES))
        .select_related("plan")
        .order_by("-created_at")
    ):
        end = _effective_end(sub)
        if end is None or end > now:
            return sub
    return None


def check_room_quota(hotel, *, count: int = 1) -> None:
    """Raise :class:`RoomLimitReached` if creating ``count`` more rooms would
    exceed the plan's ``room_limit``. No limit (``None``) or no effective
    subscription (the operational gate governs that case) -> allowed.

    ``count`` defaults to 1, and ``usage + 1 > limit`` is exactly the old
    ``usage >= limit`` gate, so the single-room create path is unchanged. Bulk
    creates pass the full batch size so N rooms are checked as one unit."""
    sub = _locked_effective_subscription(hotel)
    if sub is None:
        return
    limit = subscription_terms(sub).get("room_limit")
    if limit is None:
        return
    usage = room_usage(hotel)
    if usage + count > limit:
        raise RoomLimitReached(
            {"limit": limit, "usage": usage, "requested": count}
        )


def check_staff_quota(hotel) -> None:
    """Raise :class:`StaffLimitReached` if creating one more active staff member
    would exceed the plan's ``user_limit``."""
    sub = _locked_effective_subscription(hotel)
    if sub is None:
        return
    limit = subscription_terms(sub).get("user_limit")
    if limit is None:
        return
    usage = staff_usage(hotel)
    if usage >= limit:
        raise StaffLimitReached({"limit": limit, "usage": usage})


def check_public_booking_quota(hotel) -> None:
    """Raise :class:`PublicBookingLimitReached` if the monthly public-booking
    allowance is already reached."""
    sub = _locked_effective_subscription(hotel)
    if sub is None:
        return
    limit = subscription_terms(sub).get("max_public_bookings_per_month")
    if limit is None:
        return
    usage = public_booking_usage(hotel)
    if usage >= limit:
        raise PublicBookingLimitReached({"limit": limit, "usage": usage})


# --- Features -----------------------------------------------------------------


def normalize_feature_codes(codes) -> list[str]:
    """Lower-case, trim, de-duplicate; keep only recognised official codes."""
    seen: list[str] = []
    for raw in codes or []:
        code = str(raw).strip().lower()
        if code in OFFICIAL_FEATURES and code not in seen:
            seen.append(code)
    return seen


def has_subscription_feature(hotel, code: str) -> bool:
    """True when the hotel's EFFECTIVE subscription plan includes ``code``.

    No live subscription -> ``False``. Section enforcement by feature is
    deferred, so no existing section is gated on this yet (legacy-safe): the
    helper backs display and future opt-in gating only.
    """
    sub = effective_subscription(hotel)
    if sub is None:
        return False
    code = (code or "").strip().lower()
    return code in normalize_feature_codes(subscription_terms(sub).get("feature_codes"))


# --- Display summaries --------------------------------------------------------


def _dimension(usage: int, limit) -> dict:
    return {
        "usage": usage,
        "limit": limit,
        "remaining": (None if limit is None else max(0, limit - usage)),
        "state": usage_state(usage, limit),
    }


def entitlement_summary(hotel) -> dict:
    """Usage vs limits for rooms, staff and public bookings + the feature list —
    the read model behind both the hotel page and the owner panel."""
    sub = effective_subscription(hotel)
    terms = subscription_terms(sub) if sub is not None else {}
    return {
        "rooms": _dimension(room_usage(hotel), terms.get("room_limit")),
        "staff": _dimension(staff_usage(hotel), terms.get("user_limit")),
        "public_bookings": _dimension(
            public_booking_usage(hotel), terms.get("max_public_bookings_per_month")
        ),
        "features": normalize_feature_codes(terms.get("feature_codes")),
    }


def effective_subscription_state(hotel) -> dict:
    """The ONE rich subscription state: the banner state (enforcement) enriched
    with the frozen terms and the usage/limits summary. Used by the hotel page,
    the owner panel and their serializers."""
    from .enforcement import subscription_state

    from .models import PlatformSubscriptionPayment

    state = dict(subscription_state(hotel))
    sub = effective_subscription(hotel)
    state["terms"] = subscription_terms(sub) if sub is not None else None
    state["entitlements"] = entitlement_summary(hotel)
    # The hotel's own billing history, read-only and SAFE (no recorded_by email,
    # no void reason) — enough to show "what did we pay" on the hotel page.
    state["payments"] = [
        {
            "amount": str(p.amount),
            "currency": p.currency,
            "method": p.method,
            "received_at": p.received_at.isoformat(),
            "is_voided": p.is_voided,
        }
        for p in PlatformSubscriptionPayment.objects.filter(hotel=hotel).order_by(
            "-received_at", "-id"
        )[:20]
    ]
    return state

