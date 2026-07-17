"""Hotel-initiated subscription change requests (§8.5).

The ONLY hotel-driven entry into the otherwise platform-owner-driven subscription
lifecycle. A hotel submits a request (new subscription / renewal / upgrade); the
platform owner reviews it in TWO steps — accept, then execute. Executing calls
the existing lifecycle service in :mod:`services` (activate / renew / change
plan), so every guarantee (single live subscription, plan snapshot,
grandfathering, events) is preserved and never re-implemented here.

Owner decisions baked in (Round 4):
- Branches are out of scope (room + user limits only).
- Two-step review (under_review -> accepted -> executed).
- Downgrades are NOT a hotel-initiated kind — only new / renewal / UPGRADE.
- Executing sets a FRESH cycle from the execution moment (no proration/carry-over).

Every state change runs in a transaction and re-validates server-side. The
frontend never decides eligibility; the backend does, at submit AND at execute.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.exceptions import (
    InvalidSubscriptionRequestTransition,
    PlanNotAvailableForRequest,
    SubscriptionRequestConflict,
    SubscriptionRequestNotAllowed,
    SubscriptionRequestReasonRequired,
)

from .enforcement import effective_subscription
from .models import (
    OPEN_REQUEST_STATUSES,
    ChangeRequestKind,
    ChangeRequestStatus,
    SubscriptionChangeRequest,
    SubscriptionPlan,
    SubscriptionStatus,
)

# Only a paid, live subscription can be renewed. A TRIAL is converted to paid by
# the owner (or upgraded via a plan change) — never "renewed" — so allowing a
# renewal request on a trial would create an accepted request that cannot be
# executed (renew_subscription rejects a trial). Keep this in sync with the
# renewal precondition and can_request_renewal below.
RENEWABLE_STATUSES = (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE)
from .services import (
    _CYCLE_DAYS,
    _classify_change,
    _record_platform_event,
    activate_subscription,
    change_subscription_plan,
    record_platform_payment,
    renew_subscription,
    subscription_terms,
)


# --- Per-hotel plan availability (§8.4) --------------------------------------


def _plan_state(plan: SubscriptionPlan, live_sub, current_terms):
    """Classify a plan for THIS hotel: (state, requestable, implied_kind).

    States: ``current`` (the hotel's live plan), ``upgradeable`` (an upgrade the
    hotel can request), ``available`` (no live subscription -> newly
    subscribable) or ``unavailable`` (a downgrade/lateral move, which is not a
    hotel-initiated kind). Hidden (non-public) plans are never surfaced except
    when they are the hotel's own current plan (handled first).
    """
    if live_sub is not None and plan.id == live_sub.plan_id:
        return "current", False, None
    if not plan.is_active or not plan.is_public:
        return "unavailable", False, None
    if live_sub is None:
        return "available", True, ChangeRequestKind.NEW_SUBSCRIPTION
    if _classify_change(current_terms, plan) == "upgrade":
        return "upgradeable", True, ChangeRequestKind.PLAN_CHANGE
    # Same capacity/price or a downgrade — owner-handled, not self-service.
    return "unavailable", False, None


def available_plans_for_hotel(hotel):
    """Return ``(rows, live_sub)`` where each row is ``{plan, state, requestable,
    request_kind}`` for the hotel's plan grid.

    Only active + public plans are considered, plus the hotel's own current plan
    (so it always shows even if it was later hidden/deactivated). No hidden plan
    is ever leaked to a hotel that is not already on it.
    """
    live_sub = effective_subscription(hotel)
    current_terms = subscription_terms(live_sub) if live_sub is not None else None
    plans = list(
        SubscriptionPlan.objects.filter(is_active=True, is_public=True).order_by(
            "sort_order", "name"
        )
    )
    if live_sub is not None and not any(p.id == live_sub.plan_id for p in plans):
        plans.append(live_sub.plan)
    rows = []
    for plan in plans:
        state, requestable, kind = _plan_state(plan, live_sub, current_terms)
        rows.append(
            {
                "plan": plan,
                "state": state,
                "requestable": requestable,
                "request_kind": kind,
            }
        )
    return rows, live_sub


def can_request_renewal(live_sub) -> bool:
    """A renewal can be requested only for a live, PAID (active/past_due)
    subscription. A trial is not renewable (see RENEWABLE_STATUSES)."""
    return live_sub is not None and live_sub.status in RENEWABLE_STATUSES


# --- Server-side validation (submit AND execute) -----------------------------


def _validate_kind_precondition(kind: str, live_sub) -> None:
    """The hotel's live-subscription state must match the request kind."""
    if kind == ChangeRequestKind.NEW_SUBSCRIPTION and live_sub is not None:
        raise SubscriptionRequestNotAllowed(
            "This hotel already has a live subscription."
        )
    if kind == ChangeRequestKind.PLAN_CHANGE and live_sub is None:
        raise SubscriptionRequestNotAllowed(
            "This hotel has no live subscription to change."
        )
    if kind == ChangeRequestKind.RENEWAL and (
        live_sub is None or live_sub.status not in RENEWABLE_STATUSES
    ):
        # A trial (or no subscription) cannot be renewed — it is converted to
        # paid by the owner or upgraded via a plan change instead.
        raise SubscriptionRequestNotAllowed(
            "Only an active or past-due subscription can be renewed."
        )


def _validate_plan_target(kind: str, requested_plan, live_sub) -> None:
    """The requested plan must be a valid target for the kind (upgrades only for
    a plan change; downgrades/laterals are never hotel-initiated). A hidden
    (non-public) plan is never a valid hotel-initiated target — matching the
    availability grid, which never surfaces one."""
    if kind == ChangeRequestKind.RENEWAL:
        return  # renewal keeps the same plan
    if requested_plan is None:
        raise PlanNotAvailableForRequest("A target plan is required.")
    if not requested_plan.is_active or not requested_plan.is_public:
        raise PlanNotAvailableForRequest()
    if kind == ChangeRequestKind.NEW_SUBSCRIPTION:
        return
    # PLAN_CHANGE — must be a real upgrade over the current plan.
    if live_sub is not None and requested_plan.id == live_sub.plan_id:
        raise PlanNotAvailableForRequest("This is already the current plan.")
    current_terms = subscription_terms(live_sub) if live_sub is not None else {}
    if _classify_change(current_terms, requested_plan) != "upgrade":
        raise PlanNotAvailableForRequest(
            "Only an upgrade can be requested; contact the platform to downgrade."
        )


# --- Lifecycle ---------------------------------------------------------------


@transaction.atomic
def submit_change_request(
    hotel,
    *,
    kind: str,
    requested_plan: SubscriptionPlan | None = None,
    hotel_note: str = "",
    requested_by=None,
) -> SubscriptionChangeRequest:
    """Create a hotel-initiated request (status ``under_review``).

    Raises :class:`SubscriptionRequestConflict` if the hotel already has an open
    request, or the precondition/plan-target errors when the request is not valid
    for the hotel's current state.
    """
    if SubscriptionChangeRequest.objects.filter(
        hotel=hotel, status__in=list(OPEN_REQUEST_STATUSES)
    ).exists():
        raise SubscriptionRequestConflict()

    live_sub = effective_subscription(hotel)
    _validate_kind_precondition(kind, live_sub)
    _validate_plan_target(kind, requested_plan, live_sub)
    if kind == ChangeRequestKind.RENEWAL:
        requested_plan = None  # renewal never changes the plan

    try:
        req = SubscriptionChangeRequest.objects.create(
            hotel=hotel,
            kind=kind,
            requested_plan=requested_plan,
            current_subscription=live_sub,
            hotel_note=(hotel_note or "").strip(),
            requested_by=requested_by,
            status=ChangeRequestStatus.UNDER_REVIEW,
        )
    except IntegrityError:
        # A concurrent submit won the single-open-request slot first.
        raise SubscriptionRequestConflict()

    _record_platform_event(
        hotel,
        event_type="subscription.request_submitted",
        title=f"Subscription request submitted ({req.get_kind_display()})",
        message=(
            f"Requested plan: {requested_plan.name}." if requested_plan else "Renewal."
        ),
        actor=requested_by,
        related_object=req,
        metadata={
            "request_id": req.id,
            "kind": req.kind,
            "requested_plan": requested_plan.name if requested_plan else None,
            "status": req.status,
        },
    )
    return req


@transaction.atomic
def accept_change_request(
    req: SubscriptionChangeRequest, *, actor=None
) -> SubscriptionChangeRequest:
    """Owner accepts an ``under_review`` request (does NOT apply it yet).

    ``admin_note`` is deliberately NOT set here: it is a hotel-facing field
    reserved for the mandatory REJECTION reason, so acceptance never writes to a
    field the hotel reads."""
    req = SubscriptionChangeRequest.objects.select_for_update().get(pk=req.pk)
    if req.status != ChangeRequestStatus.UNDER_REVIEW:
        raise InvalidSubscriptionRequestTransition()
    req.status = ChangeRequestStatus.ACCEPTED
    req.decided_by = actor
    req.decided_at = timezone.now()
    req.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    _record_platform_event(
        req.hotel,
        event_type="subscription.request_accepted",
        title="Subscription request accepted",
        message="The platform owner accepted your request; it will be applied shortly.",
        actor=actor,
        related_object=req,
        metadata={"request_id": req.id, "kind": req.kind, "status": req.status},
    )
    return req


@transaction.atomic
def reject_change_request(
    req: SubscriptionChangeRequest, *, actor=None, reason: str
) -> SubscriptionChangeRequest:
    """Owner rejects an ``under_review`` request. A reason is mandatory."""
    reason = (reason or "").strip()
    if not reason:
        raise SubscriptionRequestReasonRequired()
    req = SubscriptionChangeRequest.objects.select_for_update().get(pk=req.pk)
    if req.status != ChangeRequestStatus.UNDER_REVIEW:
        raise InvalidSubscriptionRequestTransition()
    req.status = ChangeRequestStatus.REJECTED
    req.decided_by = actor
    req.decided_at = timezone.now()
    req.admin_note = reason
    req.save(
        update_fields=["status", "decided_by", "decided_at", "admin_note", "updated_at"]
    )
    _record_platform_event(
        req.hotel,
        event_type="subscription.request_rejected",
        title="Subscription request rejected",
        message=reason,
        actor=actor,
        related_object=req,
        metadata={"request_id": req.id, "kind": req.kind, "status": req.status},
    )
    return req


@transaction.atomic
def cancel_change_request(
    req: SubscriptionChangeRequest, *, actor=None, by_hotel: bool = False
) -> SubscriptionChangeRequest:
    """Cancel an open request.

    A hotel may cancel only its OWN ``under_review`` request; the owner may
    cancel any open request (``under_review`` or ``accepted``, e.g. to back out
    of an acceptance before executing it).
    """
    req = SubscriptionChangeRequest.objects.select_for_update().get(pk=req.pk)
    if by_hotel:
        if req.status != ChangeRequestStatus.UNDER_REVIEW:
            raise InvalidSubscriptionRequestTransition()
    else:
        if req.status not in OPEN_REQUEST_STATUSES:
            raise InvalidSubscriptionRequestTransition()
    req.status = ChangeRequestStatus.CANCELLED
    fields = ["status", "updated_at"]
    if not by_hotel and actor is not None:
        req.decided_by = actor
        req.decided_at = timezone.now()
        fields += ["decided_by", "decided_at"]
    req.save(update_fields=fields)
    _record_platform_event(
        req.hotel,
        event_type="subscription.request_cancelled",
        title="Subscription request cancelled",
        message="The request was cancelled by the hotel." if by_hotel
        else "The request was cancelled by the platform owner.",
        actor=actor,
        related_object=req,
        metadata={
            "request_id": req.id,
            "kind": req.kind,
            "status": req.status,
            "by_hotel": by_hotel,
        },
    )
    return req


@transaction.atomic
def execute_change_request(
    req: SubscriptionChangeRequest,
    *,
    actor=None,
    payment: dict | None = None,
    notes: str = "",
):
    """Apply an ``accepted`` request via the matching lifecycle service.

    Re-validates the kind precondition and plan target UNDER LOCK against the
    hotel's CURRENT state — a plan deactivated (or a subscription that changed)
    between accept and execute is caught here, never blindly applied. Sets a
    FRESH cycle from the execution moment (owner decision). Returns
    ``(request, subscription)``.
    """
    # Lock the request row. Only ``hotel`` (non-null) is joined here: PostgreSQL
    # forbids SELECT ... FOR UPDATE across the nullable ``requested_plan`` outer
    # join, so that plan is loaded lazily below instead.
    req = (
        SubscriptionChangeRequest.objects.select_for_update()
        .select_related("hotel")
        .get(pk=req.pk)
    )
    if req.status != ChangeRequestStatus.ACCEPTED:
        raise InvalidSubscriptionRequestTransition()

    hotel = req.hotel
    live_sub = effective_subscription(hotel)
    _validate_kind_precondition(req.kind, live_sub)
    _validate_plan_target(req.kind, req.requested_plan, live_sub)

    if req.kind == ChangeRequestKind.NEW_SUBSCRIPTION:
        sub = activate_subscription(hotel, req.requested_plan, notes=notes)
    elif req.kind == ChangeRequestKind.RENEWAL:
        # Fresh cycle from execution (owner decision): ends_at = now + plan cycle.
        # Note: an early renewal does NOT carry over remaining days — the executed
        # period always starts at the execution moment.
        cycle_days = _CYCLE_DAYS.get(live_sub.plan.billing_cycle) or 30
        sub = renew_subscription(
            live_sub, ends_at=timezone.now() + timedelta(days=cycle_days), notes=notes
        )
    else:  # PLAN_CHANGE
        sub = change_subscription_plan(
            hotel, req.requested_plan, actor=actor, reason="hotel request", notes=notes
        )

    if payment:
        record_platform_payment(
            hotel,
            subscription=sub,
            amount=payment["amount"],
            currency=sub.plan.currency,
            method=payment.get("method") or "manual",
            reference=payment.get("reference", ""),
            recorded_by=actor,
        )

    now = timezone.now()
    req.status = ChangeRequestStatus.EXECUTED
    req.executed_at = now
    req.resulting_subscription = sub
    if req.decided_by_id is None:
        req.decided_by = actor
        req.decided_at = req.decided_at or now
    req.save(
        update_fields=[
            "status",
            "executed_at",
            "resulting_subscription",
            "decided_by",
            "decided_at",
            "updated_at",
        ]
    )
    _record_platform_event(
        hotel,
        event_type="subscription.request_executed",
        title="Subscription request applied",
        message=f"Your subscription request ({req.get_kind_display()}) was applied.",
        actor=actor,
        related_object=req,
        metadata={
            "request_id": req.id,
            "kind": req.kind,
            "status": req.status,
            "subscription_id": sub.id,
            "plan": sub.plan.name,
        },
    )
    return req, sub
