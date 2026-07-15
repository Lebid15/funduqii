"""Central StayRatePeriod service (STAYS rate-integrity remediation — item 8).

The ONLY place ``StayRatePeriod`` rows are created or modified. Every write — the
check-in booking period, an extension (default / override), a shorten trim, and
legacy rate remediation — routes through here. Views and serializers NEVER write
``StayRatePeriod`` directly.

Each mutation runs inside ``transaction.atomic`` and:
  * locks the ``Stay`` row first (``of=("self",)`` — PG-safe over the nullable
    ``reservation`` join);
  * validates the rate (strictly ``> 0``, or ``NULL`` only for a booking snapshot
    that itself means "unpriced -> must be remediated" — NEVER a free night);
  * validates the currency (non-empty and == the stay/folio currency for a priced
    period, and consistent across the stay's periods);
  * rejects any OVERLAP with an existing period (``[s,e)`` intersects ``[s',e')``
    iff ``s < e'`` and ``s' < e``);
  * is idempotent (a period already at ``(stay, start_date)`` is returned as-is).
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import (
    InvalidFinanceOperation,
    InvalidStayChange,
    PermissionDenied,
    RatePeriodConflict,
    RatePeriodCoversPostedNight,
    RatePeriodOverlap,
)

from .models import Stay, StayRatePeriod, StayRatePeriodSource, StayStatus

# The precise pricing authorisation (registry-backed). Used by an extension
# OVERRIDE and by legacy remediation — never bundled into extend/finance.
RATE_OVERRIDE_PERMISSION = "stays.rate_override"


# --- small helpers -----------------------------------------------------------


def _default_currency(hotel) -> str:
    settings_obj = getattr(hotel, "settings", None)
    return (getattr(settings_obj, "default_currency", "") or "") or "USD"


def stay_currency(stay) -> str:
    """The canonical currency for a stay's rate periods = its folio currency
    (created at check-in), falling back to the hotel default before a folio
    exists. Every priced period must carry exactly this currency."""
    from apps.finance.models import Folio

    folio = (
        Folio.objects.filter(hotel=stay.hotel, stay=stay).order_by("id").first()
    )
    if folio is not None and folio.currency:
        return folio.currency
    return _default_currency(stay.hotel)


def _money(value):
    from apps.finance.services import money

    return money(value)


def _is_positive(value) -> bool:
    from apps.finance.services import ZERO, money

    return money(value) > ZERO


def _may_override_rate(user, hotel) -> bool:
    from apps.rbac.services import has_hotel_permission

    return bool(has_hotel_permission(user, hotel, RATE_OVERRIDE_PERMISSION))


def _arrival_date(stay):
    """The stay's hotel-local arrival date (mirrors the finance billing window)."""
    from zoneinfo import ZoneInfo

    from apps.shifts.services import _hotel_timezone

    if stay.actual_check_in_at is None:
        return stay.planned_check_in_date
    try:
        return timezone.localtime(
            stay.actual_check_in_at, ZoneInfo(_hotel_timezone(stay.hotel))
        ).date()
    except (KeyError, ValueError):
        return stay.planned_check_in_date


# --- validation --------------------------------------------------------------


def _validate_rate(nightly_rate, *, allow_null):
    if nightly_rate is None:
        if not allow_null:
            raise InvalidStayChange({"reason": "nightly_rate_required"})
        return None
    if not _is_positive(nightly_rate):
        raise InvalidStayChange({"reason": "nightly_rate_not_positive"})
    return _money(nightly_rate)


def _validate_currency(stay, nightly_rate, currency):
    currency = (currency or "").strip()
    canonical = stay_currency(stay)
    if nightly_rate is not None:
        # A PRICED period MUST carry an explicit, non-empty currency equal to the
        # stay/folio currency (item 7 — no empty-currency leniency).
        if not currency:
            raise InvalidFinanceOperation({"reason": "rate_currency_required"})
        if currency != canonical:
            raise InvalidFinanceOperation(
                {
                    "reason": "rate_currency_mismatch",
                    "rate_currency": currency,
                    "stay_currency": canonical,
                }
            )
        other = (
            StayRatePeriod.objects.filter(stay=stay, nightly_rate__isnull=False)
            .exclude(currency="")
            .exclude(currency=currency)
            .first()
        )
        if other is not None:
            raise InvalidFinanceOperation(
                {
                    "reason": "rate_currency_mismatch",
                    "rate_currency": currency,
                    "existing_currency": other.currency,
                }
            )
        return currency
    # A NULL-rate booking snapshot: normalize to the canonical currency.
    if currency and currency != canonical:
        raise InvalidFinanceOperation(
            {
                "reason": "rate_currency_mismatch",
                "rate_currency": currency,
                "stay_currency": canonical,
            }
        )
    return currency or canonical


def _reject_overlap(stay, start_date, end_date):
    for p in StayRatePeriod.objects.filter(stay=stay):
        if start_date < p.end_date and p.start_date < end_date:
            raise RatePeriodOverlap(
                {
                    "stay": stay.id,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "conflict_period": p.id,
                }
            )


# --- the ONLY create / modify primitives -------------------------------------


@transaction.atomic
def create_rate_period(
    stay,
    *,
    start_date,
    end_date,
    nightly_rate,
    currency,
    source,
    approved_by=None,
    approved_at=None,
    override_reason="",
    allow_null_rate=False,
):
    """Create ONE validated, non-overlapping ``StayRatePeriod`` after locking the
    stay. The ONLY sanctioned insert. Returns ``(period, created)``.

    Idempotent on ``(stay, start_date)`` ONLY for an IDENTICAL re-request: if a
    period already exists at that start date with DIFFERENT (rate / currency /
    end_date / source), a :class:`RatePeriodConflict` is raised instead of a silent
    no-op that would drop the requested change."""
    if end_date <= start_date:
        raise InvalidStayChange({"reason": "rate_period_empty_range"})
    stay = Stay.objects.select_for_update(of=("self",)).get(pk=stay.pk)
    rate = _validate_rate(nightly_rate, allow_null=allow_null_rate)
    currency = _validate_currency(stay, rate, currency)
    existing = StayRatePeriod.objects.filter(
        stay=stay, start_date=start_date
    ).first()
    if existing is not None:
        if (
            existing.nightly_rate == rate
            and existing.currency == currency
            and existing.end_date == end_date
            and existing.source == source
        ):
            return existing, False  # identical -> idempotent
        raise RatePeriodConflict(
            {
                "stay": stay.id,
                "start_date": start_date.isoformat(),
                "existing_period": existing.id,
            }
        )
    _reject_overlap(stay, start_date, end_date)
    period = StayRatePeriod.objects.create(
        hotel=stay.hotel,
        stay=stay,
        start_date=start_date,
        end_date=end_date,
        nightly_rate=rate,
        currency=currency,
        source=source,
        approved_by=approved_by,
        approved_at=approved_at,
        override_reason=override_reason or "",
    )
    return period, True


@transaction.atomic
def trim_rate_periods(stay, new_check_out_date):
    """Move the stay's rate periods to fit within ``[check_in, new_check_out_date)``
    after a SHORTEN — the ONLY sanctioned modify/delete of periods."""
    stay = Stay.objects.select_for_update(of=("self",)).get(pk=stay.pk)
    for period in list(stay.rate_periods.all()):
        if period.start_date >= new_check_out_date:
            period.delete()
        elif period.end_date > new_check_out_date:
            period.end_date = new_check_out_date
            period.save(update_fields=["end_date"])


# --- higher-level flows (all route through create_rate_period) ---------------


def create_booking_period(stay, *, reservation_line):
    """The ORIGINAL period at check-in, from the line's BOOKING snapshot (never the
    live catalog rate). A NULL agreed rate is stored as a NULL-rate booking period
    (must be remediated before billing) — never silently priced, never skipped."""
    line = reservation_line
    agreed = getattr(line, "agreed_nightly_rate", None) if line is not None else None
    agreed_currency = (
        getattr(line, "agreed_rate_currency", "") if line is not None else ""
    )
    # FIX E — pass the RAW captured currency (no ``or stay_currency`` fallback): a
    # PRICED snapshot with empty currency must be REJECTED by ``_validate_currency``
    # (item 7), not silently defaulted to the folio currency. An UNPRICED (NULL)
    # snapshot is allowed to be empty and is normalized to the canonical currency.
    period, _created = create_rate_period(
        stay,
        start_date=stay.planned_check_in_date,
        end_date=stay.planned_check_out_date,
        nightly_rate=agreed,
        currency=agreed_currency,
        source=StayRatePeriodSource.BOOKING,
        allow_null_rate=True,
    )
    return period


def create_extension_period(stay, *, old_end, new_end, requested_rate, reason, user):
    """The added window ``[old_end, new_end)`` for an extension.

    Default (no rate, or a rate EQUAL to the default): inherit the latest period's
    rate + currency, ``source="extension"``, no special permission. An explicit
    rate that DIFFERS is an OVERRIDE: it requires ``stays.rate_override`` + a
    non-empty reason + audit, ``source="override"``. The currency NEVER changes
    (inherited from the stay's latest period)."""
    periods = list(stay.rate_periods.all())
    latest = max(periods, key=lambda p: p.end_date, default=None)
    default_rate = latest.nightly_rate if latest is not None else None
    default_currency = latest.currency if latest is not None else stay_currency(stay)

    source = StayRatePeriodSource.EXTENSION
    approved_by = None
    approved_at = None
    override_reason = ""
    final_rate = default_rate

    if requested_rate is not None:
        requested = _money(requested_rate)
        if not _is_positive(requested):
            raise InvalidStayChange({"reason": "nightly_rate_not_positive"})
        is_override = default_rate is None or requested != _money(default_rate)
        if is_override:
            if not _may_override_rate(user, stay.hotel):
                raise PermissionDenied()
            if not (reason or "").strip():
                raise InvalidStayChange({"reason": "override_reason_required"})
            source = StayRatePeriodSource.OVERRIDE
            approved_by = user if getattr(user, "is_authenticated", False) else None
            approved_at = timezone.now()
            override_reason = reason.strip()
        final_rate = requested

    period, _created = create_rate_period(
        stay,
        start_date=old_end,
        end_date=new_end,
        nightly_rate=final_rate,
        currency=default_currency,
        source=source,
        approved_by=approved_by,
        approved_at=approved_at,
        override_reason=override_reason,
        allow_null_rate=(final_rate is None),
    )
    return period


def _reject_posted_night_in_window(stay, start_date, end_date):
    from apps.finance.models import ChargeType, FolioCharge, PostingStatus

    clash = FolioCharge.objects.filter(
        folio__stay=stay,
        type=ChargeType.ROOM,
        status=PostingStatus.POSTED,
        room_night__gte=start_date,
        room_night__lt=end_date,
    ).exists()
    if clash:
        raise RatePeriodCoversPostedNight(
            {
                "stay": stay.id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
        )


def _clear_unpriced_periods_in_window(stay, start_date, end_date):
    """Remove NULL-rate (unpriced) placeholder periods inside the remediation
    window so the priced period can be created. A NULL period that extends BEYOND
    the window is rejected — widen the window to cover it (never split silently)."""
    for p in StayRatePeriod.objects.filter(stay=stay, nightly_rate__isnull=True):
        if start_date < p.end_date and p.start_date < end_date:  # intersects
            if p.start_date < start_date or p.end_date > end_date:
                raise InvalidStayChange(
                    {
                        "reason": "remediation_window_must_cover_unpriced_period",
                        "period": p.id,
                    }
                )
            p.delete()


@transaction.atomic
def remediate_stay_rate(
    stay, *, start_date, end_date, nightly_rate, currency, reason, user
):
    """Set a POSITIVE agreed rate for an UNBILLED ``[start_date, end_date)`` window
    of a stay that lacked reliable coverage (legacy remediation).

    Rules: requires ``stays.rate_override`` + a non-empty reason; audited
    (``approved_by``/``approved_at``/``override_reason`` + an activity event);
    ``rate > 0``; currency == the stay/folio currency; MUST NOT cover a night that
    already has a POSTED room charge (no back-dating a financial movement — this
    creates a rate period ONLY; the normal posting service later bills). Atomic and
    idempotent."""
    if not _may_override_rate(user, stay.hotel):
        raise PermissionDenied()
    if not (reason or "").strip():
        raise InvalidStayChange({"reason": "remediation_reason_required"})
    reason = reason.strip()
    stay = Stay.objects.select_for_update(of=("self",)).get(pk=stay.pk)
    if end_date <= start_date:
        raise InvalidStayChange({"reason": "rate_period_empty_range"})
    if nightly_rate is None or not _is_positive(nightly_rate):
        raise InvalidStayChange({"reason": "nightly_rate_not_positive"})
    # Never touch an already-billed night.
    _reject_posted_night_in_window(stay, start_date, end_date)
    # Replace any unpriced placeholder the window fills, then create the priced one.
    _clear_unpriced_periods_in_window(stay, start_date, end_date)
    period, created = create_rate_period(
        stay,
        start_date=start_date,
        end_date=end_date,
        nightly_rate=nightly_rate,
        currency=currency,
        source=StayRatePeriodSource.LEGACY_REMEDIATION,
        approved_by=(user if getattr(user, "is_authenticated", False) else None),
        approved_at=timezone.now(),
        override_reason=reason,
    )
    # FIX D — audit ONLY on a real creation; an identical idempotent retry returned
    # the existing period and must NOT emit a duplicate ``stay.rate_remediated``.
    if created:
        from apps.notifications.services import record_activity

        record_activity(
            stay.hotel,
            event_type="stay.rate_remediated",
            category="stay",
            severity="warning",
            title=f"Rate remediation: stay {stay.id}",
            message=(
                f"{start_date} → {end_date} @ {period.nightly_rate} "
                f"{period.currency} · {reason}"
            ),
            actor=user,
            related_object=stay,
            related_url="/hotel/front-desk",
        )
    return period


# --- read helpers ------------------------------------------------------------


def latest_rate_period(stay):
    """The stay's rate period with the max ``end_date`` — the CURRENT rate, the one
    an extension defaults from — or ``None`` when the stay has no period. Reads the
    (preferably prefetched) ``rate_periods`` relation; never the live catalog."""
    periods = list(stay.rate_periods.all())
    if not periods:
        return None
    return max(periods, key=lambda p: p.end_date)


def stay_requires_rate_remediation(stay, *, business_date=None) -> bool:
    """OPERATIONAL flag (not a money amount): ``True`` when any DUE/consumed
    billable night (``arrival <= night < planned_check_out`` AND ``night <
    business_date``) has NO covering period with a POSITIVE rate. Drives the
    front-desk 'needs rate' state and the pre-release check command."""
    from apps.shifts.services import get_business_date

    if business_date is None:
        business_date = get_business_date(stay.hotel)
    periods = list(stay.rate_periods.all())
    night = max(stay.planned_check_in_date, _arrival_date(stay))
    end = stay.planned_check_out_date
    while night < end and night < business_date:
        covered = any(
            p.start_date <= night < p.end_date
            and p.nightly_rate is not None
            and p.nightly_rate > 0
            for p in periods
        )
        if not covered:
            return True
        night = night + timedelta(days=1)
    return False


def uncovered_billable_nights(stay, *, business_date=None) -> list:
    """The specific DUE billable nights (dates) with no positive-rate coverage —
    for the read-only pre-release command. No guest data, no live catalog rate."""
    from apps.shifts.services import get_business_date

    if business_date is None:
        business_date = get_business_date(stay.hotel)
    periods = list(stay.rate_periods.all())
    night = max(stay.planned_check_in_date, _arrival_date(stay))
    end = stay.planned_check_out_date
    gaps = []
    while night < end and night < business_date:
        covered = any(
            p.start_date <= night < p.end_date
            and p.nightly_rate is not None
            and p.nightly_rate > 0
            for p in periods
        )
        if not covered:
            gaps.append(night)
        night = night + timedelta(days=1)
    return gaps
