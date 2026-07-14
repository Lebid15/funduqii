"""Reservations & availability API URLs (mounted under /api/v1/hotel/)."""
from django.urls import path

from .document_views import (
    ReservationDocumentListCreateView,
    ReservationDocumentReplaceView,
    ReservationDocumentSignedUrlView,
    ReservationDocumentStreamView,
)
from .views import (
    AvailabilityCalendarView,
    AvailabilityView,
    ReservationCancelView,
    ReservationNoShowView,
    ReservationConfirmView,
    ReservationDetailView,
    ReservationFinancialSummaryView,
    ReservationHoldView,
    ReservationListCreateView,
    ReservationLogsView,
    ReservationOverviewView,
    ReservationPaymentCreateView,
    RoomAvailabilityView,
)

app_name = "reservations"

urlpatterns = [
    path(
        "reservations/",
        ReservationListCreateView.as_view(),
        name="reservation-list",
    ),
    path(
        "reservations/overview/",
        ReservationOverviewView.as_view(),
        name="reservation-overview",
    ),
    path(
        "reservations/room-availability/",
        RoomAvailabilityView.as_view(),
        name="reservation-room-availability",
    ),
    path(
        "reservations/<int:pk>/",
        ReservationDetailView.as_view(),
        name="reservation-detail",
    ),
    path(
        "reservations/<int:pk>/confirm/",
        ReservationConfirmView.as_view(),
        name="reservation-confirm",
    ),
    path(
        "reservations/<int:pk>/cancel/",
        ReservationCancelView.as_view(),
        name="reservation-cancel",
    ),
    path(
        "reservations/<int:pk>/no-show/",
        ReservationNoShowView.as_view(),
        name="reservation-no-show",
    ),
    path(
        "reservations/<int:pk>/hold/",
        ReservationHoldView.as_view(),
        name="reservation-hold",
    ),
    # §27 pre-arrival deposit on a future/held/confirmed reservation (no stay yet).
    path(
        "reservations/<int:pk>/payments/",
        ReservationPaymentCreateView.as_view(),
        name="reservation-payments",
    ),
    # §26/§31/§35/§39 derived financial summary for the details/edit screen.
    path(
        "reservations/<int:pk>/financial-summary/",
        ReservationFinancialSummaryView.as_view(),
        name="reservation-financial-summary",
    ),
    path(
        "reservations/<int:pk>/logs/",
        ReservationLogsView.as_view(),
        name="reservation-logs",
    ),
    # --- Guest documents (PKG 5: secure serving + upload) -------------------
    # List (view) + upload (upload), scoped to a reservation of request.hotel.
    path(
        "reservations/<int:reservation_id>/documents/",
        ReservationDocumentListCreateView.as_view(),
        name="reservation-document-list",
    ),
    # Replace (replace) a document's file(s) / metadata. ``documents`` is a
    # literal segment, so this never collides with ``reservations/<int:pk>/``.
    path(
        "reservations/documents/<int:doc_id>/",
        ReservationDocumentReplaceView.as_view(),
        name="reservation-document-detail",
    ),
    # Mint a short-lived signed URL for a side (front|back) — must precede the
    # bare stream route (distinct depth, but declared first for clarity).
    path(
        "reservations/documents/<int:doc_id>/<str:side>/url/",
        ReservationDocumentSignedUrlView.as_view(),
        name="reservation-document-signed-url",
    ),
    # Stream the raw bytes (session/JWT OR a valid signed ?token=).
    path(
        "reservations/documents/<int:doc_id>/<str:side>/",
        ReservationDocumentStreamView.as_view(),
        name="reservation-document-stream",
    ),
    path("availability/", AvailabilityView.as_view(), name="availability"),
    path(
        "availability/calendar/",
        AvailabilityCalendarView.as_view(),
        name="availability-calendar",
    ),
]
