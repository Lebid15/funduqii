"""Guests API views (Phase 7 + final closure), mounted under /api/v1/hotel/.

Scoped to the caller's hotel and guarded by ``guests.*`` permissions. A
suspended hotel is read-only.

Final closure additions:
- ``guests/directory/`` — the guests-SECTION list: only guests with at least
  one REAL stay (in-house or checked-out), with derived stats. The plain
  ``guests/`` list keeps serving reservation/check-in pickers unchanged.
- ``guests/<pk>/profile/`` — the central read-only profile: identity, flags,
  derived stats and the full stay history with view-only links.
- VIP / block / unblock endpoints behind their own permissions.
- Deleting is HARDENED: any operational trace (stay, folio, lost & found)
  deactivates instead of deleting, and the response says which one happened.
"""
from __future__ import annotations

from django.db.models import Count, Exists, OuterRef, Q
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import DefaultPagination
from apps.notifications.models import ActivityEvent
from apps.rbac.permissions import HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.reservations.models import Reservation, ReservationDocument
from apps.stays.models import Stay
from apps.subscriptions.enforcement import ensure_hotel_operational

from .models import Guest
from .normalize import normalize_id, normalize_phone
from .serializers import (
    GuestBlockSerializer,
    GuestChangeLogSerializer,
    GuestDocumentSerializer,
    GuestReservationHistorySerializer,
    GuestSerializer,
    GuestStayHistorySerializer,
    GuestUnblockSerializer,
    GuestVipSerializer,
    can_view_sensitive,
)
from .services import (
    REAL_STAY_STATUSES,
    block_guest,
    deactivate_or_delete,
    mask_document,
    record_guest_updated,
    set_vip,
    unblock_guest,
)

CanView = HasHotelPermission("guests.view")
CanUpdate = HasHotelPermission("guests.update")
CanDelete = HasHotelPermission("guests.delete")
CanMarkVip = HasHotelPermission("guests.mark_vip")
CanBlock = HasHotelPermission("guests.block")
# Reused as-is for the guest-documents endpoint: the EXISTING reservation
# document access control is required IN ADDITION to ``guests.view`` (no new
# permission is introduced).
CanViewReservationDocuments = HasHotelPermission("reservation_documents.view")


def _guard_write(request: Request) -> None:
    # Phase 16: ONE central rule decides operational writes — suspended
    # hotels AND hotels without an active subscription are refused here
    # (hotel_suspended / subscription_inactive). Reads are never blocked.
    ensure_hotel_operational(request.hotel)


def _real_stays(guest):
    """The guest's REAL stays (any role, cancelled excluded), prefetched."""
    return [
        link.stay
        for link in guest.stay_links.all()
        if link.stay.status in REAL_STAY_STATUSES
    ]


def _current_unit_summary(stay) -> dict:
    """A compact CURRENT-UNIT descriptor for one in-house stay's room.

    The card renders ``<unit type> <unit number> — <floor>`` (e.g.
    "الغرفة 101 — الطابق الأرضي"). This repo has NO unit-KIND choices enum
    (room/suite/wing/chalet): the registered unit type is the FREE-TEXT
    ``RoomType.name``, returned AS-IS (``room_type_name``). The floor label is
    ``Floor.name`` with ``Floor.number`` as a fallback code.

    Owner minimal-scope rule: return ONLY the four fields the card consumes and
    NO other stay/room details —

    * ``room_number`` — ``Room.number`` (the unit number).
    * ``room_type_name`` — ``RoomType.name`` free text (the registered type).
    * ``floor_name`` — ``Floor.name`` (the floor label).
    * ``floor_number`` — ``Floor.number`` or ``None`` (fallback for the label).

    ``room``/``floor``/``room_type`` are read off the PREFETCHED objects (see the
    directory and profile prefetch chains ``stay_links__stay__room__room_type`` /
    ``...__floor``) — no per-row query. ``Room.floor`` / ``Room.room_type`` are
    non-null FKs, so both are always present.
    """
    room = stay.room
    room_type = room.room_type
    floor = room.floor
    return {
        "room_number": room.number,
        # FREE TEXT — no unit-kind enum exists (see docstring / owner decision).
        "room_type_name": room_type.name,
        "floor_name": floor.name,
        "floor_number": floor.number or None,
    }


def _stats(stays: list) -> dict:
    """Derived stats — never stored: counts, nights, first/last, residency.

    ``current_units_count`` = the number of DISTINCT current (in-house) units the
    guest occupies right now (0 for a non-resident). ``current_unit`` carries the
    single-unit summary ONLY when the guest occupies exactly one current unit; for
    zero or for more than one it is ``None`` (the card shows the count instead).
    """
    count = len(stays)
    nights = sum(s.nights for s in stays)
    in_house = [s for s in stays if s.status == "in_house"]
    ordered = sorted(stays, key=lambda s: (s.planned_check_in_date, s.id))
    current = in_house[0] if in_house else None
    # Distinct current units — DB guarantees one in-house stay per room, so this
    # equals the count of in-house stays, but counting distinct room ids is
    # robust regardless.
    current_units_count = len({s.room_id for s in in_house})
    current_unit = (
        _current_unit_summary(current) if current_units_count == 1 else None
    )
    return {
        "stays_count": count,
        "nights_total": nights,
        "first_stay_date": str(ordered[0].planned_check_in_date) if ordered else None,
        "last_stay_date": str(ordered[-1].planned_check_in_date) if ordered else None,
        "is_repeat": count > 1,
        "is_resident": current is not None,
        "current_room_number": current.room.number if current else None,
        "current_units_count": current_units_count,
        "current_unit": current_unit,
    }


class _GuestScopedMixin:
    def get_permissions(self):
        method = self.request.method
        if method in ("PUT", "PATCH"):
            return [CanUpdate()]
        if method == "DELETE":
            return [CanDelete()]
        return [CanView()]


def _guest_search_q(search: str, request: Request) -> Q:
    """Build the guest-search filter for the plain list and the directory.

    Name / phone / email keep their operational SUBSTRING search. The national
    ID is matched EXACTLY on its normalized key only (U-10) — never a substring,
    so it can never be reconstructed digit-by-digit. The document-number
    SUBSTRING search is a reconstruction oracle for a MASKED number, so it is
    gated behind ``guests.view_sensitive_data`` (Decision 5 / U-09 / S3): a basic
    viewer cannot progressively rebuild a masked document number. Both lists
    still MASK the returned values per permission — this only governs which
    guests a search term can surface.
    """
    cond = (
        Q(full_name__icontains=search)
        | Q(phone__icontains=search)
        | Q(email__icontains=search)
    )
    national_id_key = normalize_id(search)
    if national_id_key:
        cond |= Q(national_id_normalized=national_id_key)
    if can_view_sensitive(request):
        cond |= Q(document_number__icontains=search)
    return cond


class GuestListView(generics.ListAPIView):
    """The PLAIN guest list — reservation/check-in pickers depend on it.

    LIST-ONLY (Decision 9): there is deliberately NO create endpoint here. A
    Guest is created ONLY through the central identity service (wired in a later
    wave), so a ``POST`` to this route is ``405 Method Not Allowed`` and the API
    can never mint an orphan Guest. GET behavior is unchanged (all active guests,
    no stay requirement)."""

    serializer_class = GuestSerializer

    def get_permissions(self):
        return [CanView()]

    def get_queryset(self):
        qs = Guest.objects.filter(hotel=self.request.hotel)
        params = self.request.query_params
        is_active = params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        search = params.get("search")
        if search:
            qs = qs.filter(_guest_search_q(search, self.request))
        return qs.distinct()


class GuestDirectoryView(generics.ListAPIView):
    """The guests-SECTION list: only guests who actually stayed (>= 1 real
    stay), each row carrying derived stats. Stats come from ONE prefetch —
    no per-row queries."""

    def get_permissions(self):
        return [CanView()]

    def get_queryset(self):
        from apps.reservations.models import BLOCKING_STATUSES
        from apps.shifts.services import get_business_date

        # Card support: ``has_upcoming`` = the guest holds a future/active booking as
        # PRIMARY guest — an ACTIVE (blocking) reservation whose window has not yet
        # departed (check-out on/after the hotel business date). Computed once via an
        # ``Exists()`` subquery on the directory queryset (no per-row query / N+1),
        # mirroring the profile's ``upcoming_reservations`` definition exactly so the
        # card badge and the profile can never disagree.
        business_date = get_business_date(self.request.hotel)
        upcoming = Reservation.objects.filter(
            hotel=self.request.hotel,
            primary_guest_id=OuterRef("pk"),
            status__in=BLOCKING_STATUSES,
            check_out_date__gte=business_date,
        )
        qs = (
            Guest.objects.filter(hotel=self.request.hotel)
            .annotate(
                real_stay_count=Count(
                    "stay_links",
                    filter=Q(stay_links__stay__status__in=REAL_STAY_STATUSES),
                ),
                has_upcoming=Exists(upcoming),
            )
            .filter(real_stay_count__gte=1)
            # Prefetch the whole current-unit chain in ONE batched pass per level
            # (room -> room_type / floor) so ``_current_unit_summary`` reads them
            # off the cache with no per-row query (N+1). The deep FK paths also
            # cover the shallower ``stay_links__stay__room`` used by the stats.
            .prefetch_related(
                "stay_links__stay__room__room_type",
                "stay_links__stay__room__floor",
            )
        )
        params = self.request.query_params
        is_active = params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        search = params.get("search")
        if search:
            qs = qs.filter(_guest_search_q(search, self.request)).distinct()
        # Explicit ordering: ``.annotate(Count(...))`` drops the model Meta
        # ordering, so DRF pagination would emit UnorderedObjectListWarning and
        # page inconsistently. Order by the same keys as Meta.
        return qs.order_by("full_name", "id")

    def list(self, request: Request, *args, **kwargs) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        sensitive = can_view_sensitive(request)
        rows = []
        for guest in page:
            stats = _stats(_real_stays(guest))
            # ``needs_review`` = blocked AND still holds a future/active booking — a
            # human must reconcile the block with the pending arrival. Same rule as
            # the profile's ``needs_review`` (is_blocked AND upcoming).
            needs_review = guest.is_blocked and guest.has_upcoming
            rows.append(
                {
                    "id": guest.id,
                    "full_name": guest.full_name,
                    "phone": guest.phone,
                    "nationality": guest.nationality,
                    "document_type": guest.document_type,
                    "document_number": (
                        guest.document_number
                        if sensitive
                        else mask_document(guest.document_number)
                    ),
                    "is_active": guest.is_active,
                    "is_vip": guest.is_vip,
                    "is_blocked": guest.is_blocked,
                    "has_upcoming": guest.has_upcoming,
                    "needs_review": needs_review,
                    **stats,
                }
            )
        return self.get_paginated_response(rows)


class GuestDetailView(_GuestScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GuestSerializer

    def get_queryset(self):
        return Guest.objects.filter(hotel=self.request.hotel)

    def perform_update(self, serializer):
        _guard_write(self.request)
        old = {
            "full_name": serializer.instance.full_name,
            "phone": serializer.instance.phone,
            # SEC-F1 / U-06: national_id is a first-class identity field and a
            # change to it MUST be audited. It is captured here (and compared +
            # logged MASKED in record_guest_updated) so an edit is never silent.
            "national_id": serializer.instance.national_id,
            "document_type": serializer.instance.document_type,
            "document_number": serializer.instance.document_number,
        }
        guest = serializer.save(updated_by=self.request.user)
        record_guest_updated(guest, old_values=old, user=self.request.user)

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        _guard_write(request)
        guest = self.get_object()
        result = deactivate_or_delete(guest, user=request.user)
        if result == "deactivated":
            guest.refresh_from_db()
            return Response(
                {
                    "result": "deactivated",
                    "guest": GuestSerializer(
                        guest, context={"request": request}
                    ).data,
                }
            )
        return Response({"result": "deleted"})


class GuestProfileView(APIView):
    """The central, READ-ONLY guest profile: identity + flags + derived stats
    + the full stay history with view-only links. Nothing operational can be
    changed from here."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request, pk: int) -> Response:
        from apps.reservations.models import BLOCKING_STATUSES
        from apps.shifts.services import get_business_date

        guest = generics.get_object_or_404(
            Guest.objects.filter(hotel=request.hotel).prefetch_related(
                "stay_links__stay__room__room_type",
                # ``_stats`` -> ``_current_unit_summary`` reads ``room.floor`` for
                # the shared ``current_unit`` summary; prefetch it here too so the
                # profile stays N+1-free.
                "stay_links__stay__room__floor",
                "stay_links__stay__reservation",
                "stay_links__stay__folios",
                "reservations",
            ),
            pk=pk,
        )
        sensitive = can_view_sensitive(request)
        can_see_block_reason = has_hotel_permission(
            request.user, request.hotel, "guests.block"
        )

        # U-15: the guest's UPCOMING reservations — a booking they hold as
        # primary guest that is still ACTIVE (blocking status) and has not yet
        # departed (check-out on/after the hotel business date). Filtered in
        # Python over the single ``reservations`` prefetch (no per-row query).
        business_date = get_business_date(request.hotel)
        upcoming_reservations = sorted(
            (
                res
                for res in guest.reservations.all()
                if res.status in BLOCKING_STATUSES
                and res.check_out_date >= business_date
            ),
            key=lambda res: (res.check_in_date, res.id),
        )
        # S5: a blocked guest who still holds an active/future booking needs a
        # human to reconcile the block with the pending arrival.
        needs_review = guest.is_blocked and bool(upcoming_reservations)

        all_stays = sorted(
            (link.stay for link in guest.stay_links.all()),
            key=lambda s: (s.planned_check_in_date, s.id),
            reverse=True,
        )
        real = [s for s in all_stays if s.status in REAL_STAY_STATUSES]
        stats = _stats(real)
        current = next((s for s in real if s.status == "in_house"), None)

        def _folio_of(stay):
            folios = list(stay.folios.all())
            open_first = sorted(
                folios, key=lambda f: (f.status != "open", -f.id)
            )
            return open_first[0] if open_first else None

        history = []
        for stay in all_stays:
            folio = _folio_of(stay)
            history.append(
                {
                    "stay_id": stay.id,
                    "status": stay.status,
                    "is_current": stay.status == "in_house",
                    "reservation_id": stay.reservation_id,
                    "reservation_number": (
                        stay.reservation.reservation_number
                        if stay.reservation_id
                        else None
                    ),
                    "room_number": stay.room.number,
                    "room_type_name": stay.room.room_type.name,
                    "check_in_date": str(stay.planned_check_in_date),
                    "check_out_date": str(stay.planned_check_out_date),
                    "actual_check_out_at": (
                        stay.actual_check_out_at.isoformat()
                        if stay.actual_check_out_at
                        else None
                    ),
                    "nights": stay.nights,
                    "folio_id": folio.id if folio else None,
                    "folio_number": folio.folio_number if folio else None,
                    "folio_status": folio.status if folio else None,
                }
            )

        current_folio = _folio_of(current) if current else None
        payload = {
            "id": guest.id,
            "full_name": guest.full_name,
            "phone": guest.phone,
            "email": guest.email,
            "nationality": guest.nationality,
            "gender": guest.gender,
            # S5: date_of_birth and address are sensitive personal data — mask
            # them fail-closed for callers without ``guests.view_sensitive_data``
            # (same gate as document_number). A present value is fully hidden
            # ("••••"); an absent value stays absent so nothing is invented.
            "date_of_birth": (
                (str(guest.date_of_birth) if guest.date_of_birth else None)
                if sensitive
                else ("••••" if guest.date_of_birth else None)
            ),
            "document_type": guest.document_type,
            "document_number": (
                guest.document_number
                if sensitive
                else mask_document(guest.document_number)
            ),
            "address": (
                guest.address
                if sensitive
                else ("••••" if guest.address else "")
            ),
            "notes": guest.notes,
            "is_active": guest.is_active,
            "is_vip": guest.is_vip,
            "vip_marked_at": (
                guest.vip_marked_at.isoformat() if guest.vip_marked_at else None
            ),
            "vip_marked_by": (
                guest.vip_marked_by.email if guest.vip_marked_by_id else None
            ),
            "is_blocked": guest.is_blocked,
            "blocked_at": guest.blocked_at.isoformat() if guest.blocked_at else None,
            "blocked_by": guest.blocked_by.email if guest.blocked_by_id else None,
            # The reason is sensitive: only block-permission holders see it.
            "block_reason": guest.block_reason if can_see_block_reason else None,
            "needs_review": needs_review,
            "upcoming_reservations": [
                {
                    "reservation_id": res.id,
                    "reservation_number": res.reservation_number,
                    "status": res.status,
                    "booking_kind": res.booking_kind,
                    "check_in_date": str(res.check_in_date),
                    "check_out_date": str(res.check_out_date),
                }
                for res in upcoming_reservations
            ],
            **stats,
            "current": (
                {
                    "stay_id": current.id,
                    "room_number": current.room.number,
                    "reservation_id": current.reservation_id,
                    "reservation_number": (
                        current.reservation.reservation_number
                        if current.reservation_id
                        else None
                    ),
                    "folio_id": current_folio.id if current_folio else None,
                    "folio_number": (
                        current_folio.folio_number if current_folio else None
                    ),
                    "folio_status": current_folio.status if current_folio else None,
                }
                if current
                else None
            ),
            "stays": history,
            "created_at": guest.created_at.isoformat(),
            "updated_at": guest.updated_at.isoformat(),
            "created_by": guest.created_by.email if guest.created_by_id else None,
            "updated_by": guest.updated_by.email if guest.updated_by_id else None,
        }
        return Response(payload)


class GuestVipView(APIView):
    def get_permissions(self):
        return [CanMarkVip()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        guest = generics.get_object_or_404(Guest, pk=pk, hotel=request.hotel)
        serializer = GuestVipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guest = set_vip(guest, vip=serializer.validated_data["vip"], user=request.user)
        return Response(GuestSerializer(guest, context={"request": request}).data)


class GuestBlockView(APIView):
    def get_permissions(self):
        return [CanBlock()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        guest = generics.get_object_or_404(Guest, pk=pk, hotel=request.hotel)
        serializer = GuestBlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guest = block_guest(
            guest, reason=serializer.validated_data["reason"], user=request.user
        )
        return Response(GuestSerializer(guest, context={"request": request}).data)


class GuestUnblockView(APIView):
    def get_permissions(self):
        return [CanBlock()]

    def post(self, request: Request, pk: int) -> Response:
        _guard_write(request)
        guest = generics.get_object_or_404(Guest, pk=pk, hotel=request.hotel)
        serializer = GuestUnblockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        guest = unblock_guest(
            guest, note=serializer.validated_data.get("note", ""), user=request.user
        )
        return Response(GuestSerializer(guest, context={"request": request}).data)


class GuestLookupView(APIView):
    """Exact-match guest lookup for the reservation form — hotel-scoped and
    read-only, behind ``guests.view``.

    Query params ``national_id`` and/or ``phone`` are normalized the SAME way
    the stored keys are, then matched EXACTLY against ``national_id_normalized``
    / ``phone_normalized`` (OR when both are given, so a match on either surfaces
    a possible duplicate). Returns ``{"results": [...]}`` — empty when nothing
    matches. Each result is the guest serialized (``national_id`` masked per
    ``guests.view_sensitive_data``) plus ``is_blocked`` / ``is_vip`` so the UI
    can warn."""

    def get_permissions(self):
        return [CanView()]

    def get(self, request: Request) -> Response:
        from django.db.models import Q

        national_id = normalize_id(request.query_params.get("national_id", ""))
        phone = normalize_phone(request.query_params.get("phone", ""))

        # No usable identifier ⇒ never scan the whole directory; empty result.
        if not national_id and not phone:
            return Response({"results": []})

        lookup = Q()
        if national_id:
            lookup |= Q(national_id_normalized=national_id)
        if phone:
            lookup |= Q(phone_normalized=phone)

        matches = (
            Guest.objects.filter(hotel=request.hotel).filter(lookup).distinct()
        )
        results = []
        for guest in matches:
            data = GuestSerializer(guest, context={"request": request}).data
            # is_blocked / is_vip are already serialized (read-only); set them
            # explicitly so the contract holds even if the serializer changes.
            data["is_blocked"] = guest.is_blocked
            data["is_vip"] = guest.is_vip
            results.append(data)
        return Response({"results": results})


# --------------------------------------------------------------------------- #
# GAP-1 read-only profile sub-resources (paginated)                           #
# EXEC-GUESTS-CLOSURE-01 / W3b — Decision 11. Four READ-ONLY, hotel-scoped,    #
# permission-scoped, paginated ListAPIViews that back the profile modals with  #
# real data. GET only; a guest of another hotel resolves to 404; every query   #
# is scoped to ``hotel=request.hotel``; sensitive fields reuse the existing    #
# masking gates. No route-guard / RBAC / file-service change — pure reuse.     #
# --------------------------------------------------------------------------- #


class _GuestSubResourceView(generics.ListAPIView):
    """Shared base: resolve the guest under ``hotel=request.hotel`` (404 for
    another hotel's guest) and require ``guests.view``. Reads are never blocked
    by the suspended-hotel guard (that guard is for writes only)."""

    pagination_class = DefaultPagination

    def get_permissions(self):
        return [CanView()]

    def get_guest(self) -> Guest:
        # Tenant isolation: another hotel's guest (or a missing one) is a 404.
        return generics.get_object_or_404(
            Guest, pk=self.kwargs["pk"], hotel=self.request.hotel
        )


class GuestStaysView(_GuestSubResourceView):
    """GET ``guests/<pk>/stays/`` — the guest's stay history, newest first.

    Scope = every stay the guest is attached to (any role), matching the
    profile's ``stay_links`` definition. Paginated by ``DefaultPagination``.
    """

    serializer_class = GuestStayHistorySerializer

    def get_queryset(self):
        guest = self.get_guest()
        return (
            Stay.objects.filter(hotel=self.request.hotel, guests__guest=guest)
            .select_related("room__room_type", "reservation")
            .prefetch_related("folios")
            .order_by("-planned_check_in_date", "-id")
        )


class GuestReservationsView(_GuestSubResourceView):
    """GET ``guests/<pk>/reservations/`` — the guest's reservation history.

    Scope = bookings the guest holds as the PRIMARY guest
    (``Reservation.primary_guest``), matching the profile's reservations
    concept. Past / current / upcoming are all included; newest arrival first.
    """

    serializer_class = GuestReservationHistorySerializer

    def get_queryset(self):
        guest = self.get_guest()
        return Reservation.objects.filter(
            hotel=self.request.hotel, primary_guest=guest
        ).order_by("-check_in_date", "-id")


class GuestDocumentsView(_GuestSubResourceView):
    """GET ``guests/<pk>/documents/`` — the guest's identity documents.

    "Guest documents" is RESOLVED from the EXISTING ``ReservationDocument``
    mechanism (there is no separate guest-document store): the aggregate of

      * documents whose named occupant IS this guest
        (``occupant.guest == guest``), plus
      * whole-reservation / primary-guest documents (``occupant IS NULL``) on a
        reservation whose ``primary_guest`` IS this guest.

    All hotel-scoped. Access requires ``guests.view`` AND the existing
    ``reservation_documents.view`` — and the image bytes still flow only through
    the existing signed-URL mint + protected stream endpoints (surfaced as
    ``front_url`` / ``back_url``). The identity ``number`` is masked unless the
    caller holds ``guests.view_sensitive_data``.
    """

    serializer_class = GuestDocumentSerializer

    def get_permissions(self):
        # AND-composition: DRF requires every listed permission to pass, and
        # each raises PermissionDenied on failure — so this enforces BOTH the
        # guests read AND the reservation-document read control.
        return [CanView(), CanViewReservationDocuments()]

    def get_queryset(self):
        guest = self.get_guest()
        return (
            ReservationDocument.objects.filter(hotel=self.request.hotel)
            .filter(
                Q(occupant__guest=guest)
                | Q(occupant__isnull=True, reservation__primary_guest=guest)
            )
            .select_related("reservation", "occupant")
            .order_by("-created_at", "-id")
            .distinct()
        )


class GuestChangeLogView(_GuestSubResourceView):
    """GET ``guests/<pk>/change-log/`` — the guest's change-log / audit history
    (created / updated / vip / blocked / unblocked / reactivated / deactivated),
    newest first, read from the existing ``ActivityEvent`` store.

    Sensitive identity values are already masked at record time and stay masked.
    The BLOCK REASON / unblock note (the ``guest.blocked`` / ``guest.unblocked``
    message) stays gated behind ``guests.block`` — mirrors the profile.
    """

    serializer_class = GuestChangeLogSerializer

    def get_queryset(self):
        guest = self.get_guest()
        # ``related_object_*`` pins the events to THIS guest only; the hotel
        # filter is the tenant boundary. ``related_object_type="Guest"`` excludes
        # reservation-document events (which are category=guest but not about the
        # Guest row itself).
        return ActivityEvent.objects.filter(
            hotel=self.request.hotel,
            related_object_type="Guest",
            related_object_id=guest.id,
        ).order_by("-occurred_at", "-id")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        # Computed ONCE for the page (not per row): does the caller hold
        # ``guests.block`` and may therefore see the block reason / unblock note.
        ctx["can_see_block_reason"] = has_hotel_permission(
            self.request.user, self.request.hotel, "guests.block"
        )
        return ctx
