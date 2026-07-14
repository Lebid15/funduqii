"""Secure serving + upload API for reservation guest documents (PKG 5).

This is the serving/upload layer on top of the private storage + validation
foundation (``document_storage.py`` / ``document_validators.py`` / the
``ReservationDocument`` model). It is kept OUT of the big ``views.py`` on
purpose — everything here is about the STRICTLY PRIVATE identity documents and
their guardrails:

- **Tenant isolation on every endpoint.** A document is always resolved with
  ``hotel=request.hotel`` (or, on the token path, its hotel is bound into the
  signed token). A user of hotel A can never read hotel B's document even with
  a guessed id — the lookup 404s.
- **No public/static path.** The bytes are only ever served by
  :class:`ReservationDocumentStreamView` (``FileResponse``, ``inline``,
  ``no-store``). ``PRIVATE_MEDIA_ROOT`` is never routed through
  ``config/urls.py``'s ``static()``.
- **Short-lived signed URLs.** So a plain ``<img>`` / PDF viewer can fetch the
  file without carrying an ``Authorization`` header, the mint endpoint issues an
  HMAC token (``django.core.signing`` over ``SECRET_KEY``) bound to
  ``(doc id, side, hotel)`` and valid for :data:`STREAM_TOKEN_MAX_AGE` seconds.
  The stream view accepts either that token OR a normal authenticated caller.

Endpoints (mounted under ``/api/v1/hotel/`` — see ``urls.py``)::

    GET   reservations/<reservation_id>/documents/        list   (view)
    POST  reservations/<reservation_id>/documents/        upload (upload)
    PATCH reservations/documents/<doc_id>/                replace(replace)
    PUT   reservations/documents/<doc_id>/                replace(replace)
    GET   reservations/documents/<doc_id>/<side>/url/     mint   (view)
    GET   reservations/documents/<doc_id>/<side>/         stream (view | token)
"""
from __future__ import annotations

import mimetypes
import os

from django.core import signing
from django.http import FileResponse, Http404
from django.urls import reverse

from rest_framework import serializers, status
from rest_framework.exceptions import NotAuthenticated
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import InvalidMediaFile, PermissionDenied, UserInactive
from apps.rbac.permissions import HasHotelPermission
from apps.rbac.services import has_hotel_permission
from apps.subscriptions.enforcement import ensure_hotel_operational
from apps.tenancy.context import resolve_hotel_context

from .document_validators import validate_reservation_document
from .models import Reservation, ReservationDocument, ReservationOccupant
from .serializers import (
    ReservationDocumentReadSerializer,
    ReservationDocumentWriteSerializer,
)

# Permission classes for the ``reservation_documents`` RBAC section. ``view``
# gates listing/streaming/minting, ``upload`` gates creating, ``replace`` gates
# overwriting an existing document's file(s) — deliberately never bundled.
CanViewDocuments = HasHotelPermission("reservation_documents.view")
CanUploadDocuments = HasHotelPermission("reservation_documents.upload")
CanReplaceDocuments = HasHotelPermission("reservation_documents.replace")

# Signed short-lived stream token. ``django.core.signing`` derives an HMAC key
# from ``settings.SECRET_KEY`` (+ this salt), so the token is UNFORGEABLE by a
# client. The payload binds the exact ``(doc, side, hotel)`` so a token minted
# for one document/side/hotel can never be replayed for another. ``max_age`` on
# the read side enforces the short lifetime (a stale token is rejected).
STREAM_TOKEN_SALT = "reservations.document.stream.v1"
STREAM_TOKEN_MAX_AGE = 300  # seconds (5 minutes)

# Only two sides exist; anything else 404s (never a partial/traversal path).
_SIDE_FIELDS = {"front": "front_file", "back": "back_file"}

# Content-Type is derived from the STORED file extension (which is itself from
# the validated allowlist). An explicit map avoids platform-dependent
# ``mimetypes`` gaps (e.g. webp on Windows) before falling back.
_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def _content_type_for(name: str) -> str:
    ext = os.path.splitext(name or "")[1].lower()
    if ext in _CONTENT_TYPES:
        return _CONTENT_TYPES[ext]
    guessed, _ = mimetypes.guess_type(name or "")
    return guessed or "application/octet-stream"


def _resolve_occupant(request: Request, reservation: Reservation, occupant_id):
    """Resolve an optional occupant id, scoped to THIS reservation and hotel.

    Returns ``None`` when no occupant is supplied. A supplied id that does not
    belong to this reservation (and hotel) is rejected with a clean 400 — a
    document can never be linked to another reservation's / hotel's occupant.
    """
    if not occupant_id:
        return None
    occupant = ReservationOccupant.objects.filter(
        pk=occupant_id, reservation=reservation, hotel=request.hotel
    ).first()
    if occupant is None:
        raise serializers.ValidationError(
            {"occupant": "The occupant does not belong to this reservation."}
        )
    return occupant


def _audit(request: Request, reservation: Reservation, document, action: str) -> None:
    """Record a light activity event for an upload/replace (Invariant 10)."""
    from apps.notifications.services import record_activity

    label = document.get_doc_type_display() or "document"
    record_activity(
        request.hotel,
        event_type=f"reservation_document.{action}",
        category="guest",
        severity="info",
        title=f"Reservation {reservation.reservation_number} document {action}",
        message=f"{label} · doc#{document.id}",
        actor=request.user,
        related_object=document,
        related_url="/hotel/reservations",
        # A routine, low-value operational event: keep the audit trail but do
        # not fan out notifications (keeps the inbox high-signal).
        notify=False,
    )


def _serve_file(field_file) -> FileResponse:
    """Stream a private FieldFile inline, never cached, never sniffed."""
    content_type = _content_type_for(field_file.name)
    ext = os.path.splitext(field_file.name or "")[1].lower()
    response = FileResponse(field_file.open("rb"), content_type=content_type)
    # Show inline in a viewer; the on-disk name is an opaque uuid so we expose a
    # generic, PII-free filename only.
    response["Content-Disposition"] = f'inline; filename="document{ext}"'
    # These are private identity documents — never store them anywhere.
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    # SEC-F3: the signed stream URL carries a short-lived token in ``?token=``.
    # A no-referrer policy stops that token from leaking to third parties via the
    # Referer header if the inline document ever loads/links external resources.
    response["Referrer-Policy"] = "no-referrer"
    return response


class ReservationDocumentListCreateView(APIView):
    """List a reservation's documents (metadata only) or upload a new one.

    ``GET`` returns :class:`ReservationDocumentReadSerializer` rows (no raw file
    URLs — only ``has_front`` / ``has_back`` booleans). ``POST`` (multipart)
    creates a document with ``doc_type`` / ``number`` / optional ``occupant``
    and at least one of ``front_file`` / ``back_file``; every uploaded file is
    validated for a clean 400 before it is written to private storage.
    """

    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == "POST":
            return [CanUploadDocuments()]
        return [CanViewDocuments()]

    def _get_reservation(self, request: Request, reservation_id: int) -> Reservation:
        # Tenant isolation: the reservation must belong to the caller's hotel or
        # this 404s (no cross-tenant read/write, even with a guessed id).
        return get_object_or_404(Reservation, pk=reservation_id, hotel=request.hotel)

    def get(self, request: Request, reservation_id: int) -> Response:
        reservation = self._get_reservation(request, reservation_id)
        documents = reservation.documents.all()
        return Response(
            ReservationDocumentReadSerializer(
                documents, many=True, context={"request": request}
            ).data
        )

    def post(self, request: Request, reservation_id: int) -> Response:
        ensure_hotel_operational(request.hotel)
        reservation = self._get_reservation(request, reservation_id)

        serializer = ReservationDocumentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meta = serializer.validated_data

        occupant = _resolve_occupant(request, reservation, meta.get("occupant"))

        front = request.FILES.get("front_file")
        back = request.FILES.get("back_file")
        if not front and not back:
            # A dedicated upload with no file is meaningless — reject cleanly.
            raise InvalidMediaFile({"reason": "no_file"})
        # Validate BEFORE anything is written to storage (clean 400 with reason).
        if front is not None:
            validate_reservation_document(front)
        if back is not None:
            validate_reservation_document(back)

        document = ReservationDocument(
            hotel=request.hotel,
            reservation=reservation,
            occupant=occupant,
            doc_type=meta.get("doc_type", ""),
            number=meta.get("number", ""),
            uploaded_by=request.user,
        )
        if front is not None:
            document.front_file = front
        if back is not None:
            document.back_file = back
        document.save()

        _audit(request, reservation, document, "uploaded")
        return Response(
            ReservationDocumentReadSerializer(
                document, context={"request": request}
            ).data,
            status=status.HTTP_201_CREATED,
        )


class ReservationDocumentReplaceView(APIView):
    """Replace a document's file(s) and optionally its number / doc_type.

    Hotel-scoped. On each replaced side the OLD private file is deleted from
    storage first (``FieldFile.delete(save=False)``) so no orphaned file
    lingers, then the new (validated) file is assigned and the row saved.
    """

    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ["patch", "put", "head", "options"]

    def get_permissions(self):
        return [CanReplaceDocuments()]

    def _get_document(self, request: Request, doc_id: int) -> ReservationDocument:
        # Tenant isolation: another hotel's document 404s here.
        return get_object_or_404(ReservationDocument, pk=doc_id, hotel=request.hotel)

    def patch(self, request: Request, doc_id: int) -> Response:
        return self._replace(request, doc_id)

    def put(self, request: Request, doc_id: int) -> Response:
        return self._replace(request, doc_id)

    def _replace(self, request: Request, doc_id: int) -> Response:
        ensure_hotel_operational(request.hotel)
        document = self._get_document(request, doc_id)

        serializer = ReservationDocumentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meta = serializer.validated_data

        # Only touch metadata fields the caller actually sent — the serializer's
        # ``default=""`` must never silently blank an existing value on replace.
        if "occupant" in request.data:
            document.occupant = _resolve_occupant(
                request, document.reservation, meta.get("occupant")
            )
        if "doc_type" in request.data:
            document.doc_type = meta.get("doc_type", "")
        if "number" in request.data:
            document.number = meta.get("number", "")

        front = request.FILES.get("front_file")
        back = request.FILES.get("back_file")
        # Validate BEFORE deleting/overwriting anything.
        if front is not None:
            validate_reservation_document(front)
        if back is not None:
            validate_reservation_document(back)

        # Delete the OLD private file(s) so replaced files never orphan on disk.
        if front is not None:
            if document.front_file:
                document.front_file.delete(save=False)
            document.front_file = front
        if back is not None:
            if document.back_file:
                document.back_file.delete(save=False)
            document.back_file = back

        document.save()
        _audit(request, document.reservation, document, "replaced")
        return Response(
            ReservationDocumentReadSerializer(
                document, context={"request": request}
            ).data
        )


class ReservationDocumentSignedUrlView(APIView):
    """Mint a short-lived signed URL for one document side (front|back).

    Hotel-scoped and behind ``reservation_documents.view``. Returns the absolute
    URL of the stream endpoint carrying a ``?token=`` bound to
    ``(doc, side, hotel)`` and valid for :data:`STREAM_TOKEN_MAX_AGE` seconds.
    """

    def get_permissions(self):
        return [CanViewDocuments()]

    def get(self, request: Request, doc_id: int, side: str) -> Response:
        side_field = _SIDE_FIELDS.get(side)
        if side_field is None:
            raise Http404()
        # Tenant isolation: minting is only possible for the caller's own hotel.
        document = get_object_or_404(
            ReservationDocument, pk=doc_id, hotel=request.hotel
        )
        field_file = getattr(document, side_field)
        if not field_file:
            raise Http404()

        token = signing.dumps(
            {"doc": document.id, "side": side, "hotel": document.hotel_id},
            salt=STREAM_TOKEN_SALT,
        )
        stream_path = reverse(
            "reservations:reservation-document-stream",
            kwargs={"doc_id": document.id, "side": side},
        )
        url = request.build_absolute_uri(f"{stream_path}?token={token}")
        return Response({"url": url, "expires_in": STREAM_TOKEN_MAX_AGE})


class ReservationDocumentStreamView(APIView):
    """Stream the raw bytes of one document side (front|back).

    Authorization accepts EITHER:
      (a) an authenticated, active caller holding ``reservation_documents.view``
          in a hotel context that MATCHES the document's hotel, OR
      (b) a valid, unexpired signed ``token`` bound to this exact
          ``(doc, side, hotel)``.

    A mismatched/expired/forged token is rejected (403). There is no public or
    static path to these bytes — this view is the only reader.
    """

    # Opt out of the global "authenticated" default so the token path works for
    # an unauthenticated <img>/viewer fetch; every request is still authorized
    # explicitly below (token OR session), never implicitly.
    permission_classes = [AllowAny]

    def get(self, request: Request, doc_id: int, side: str) -> FileResponse:
        side_field = _SIDE_FIELDS.get(side)
        if side_field is None:
            raise Http404()

        token = request.query_params.get("token")
        if token:
            document = self._authorize_by_token(token, doc_id, side)
        else:
            document = self._authorize_by_session(request, doc_id)

        field_file = getattr(document, side_field)
        if not field_file:
            raise Http404()
        return _serve_file(field_file)

    def _authorize_by_token(
        self, token: str, doc_id: int, side: str
    ) -> ReservationDocument:
        try:
            payload = signing.loads(
                token, salt=STREAM_TOKEN_SALT, max_age=STREAM_TOKEN_MAX_AGE
            )
        except signing.SignatureExpired as exc:
            raise PermissionDenied() from exc
        except signing.BadSignature as exc:
            raise PermissionDenied() from exc
        if not isinstance(payload, dict):
            raise PermissionDenied()
        # The token must be for THIS doc + side (never replayed for another).
        if payload.get("doc") != doc_id or payload.get("side") != side:
            raise PermissionDenied()
        document = get_object_or_404(ReservationDocument, pk=doc_id)
        # And it must be bound to the document's ACTUAL hotel (tenant binding).
        if document.hotel_id != payload.get("hotel"):
            raise PermissionDenied()
        return document

    def _authorize_by_session(
        self, request: Request, doc_id: int
    ) -> ReservationDocument:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise NotAuthenticated()
        if not user.is_active:
            raise UserInactive()
        context = resolve_hotel_context(request, required=True)
        hotel = context.hotel
        if not has_hotel_permission(user, hotel, "reservation_documents.view"):
            raise PermissionDenied()
        # Tenant isolation: another hotel's document 404s here.
        return get_object_or_404(ReservationDocument, pk=doc_id, hotel=hotel)
