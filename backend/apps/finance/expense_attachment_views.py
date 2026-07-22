"""Secure serving + upload API for expense attachments (EXPENSES-CLOSURE).

The serving/upload layer on top of the private storage + validation foundation
(``expense_storage.py`` / ``expense_validators.py`` / the ``Expense.attachment``
field). Kept OUT of the big ``views.py`` on purpose — everything here is about
the STRICTLY PRIVATE receipt scans and their guardrails:

- **Tenant isolation on every endpoint.** The expense is always resolved with
  ``hotel=request.hotel`` (or, on the token path, its hotel is bound into the
  signed token). A user of hotel A can never read hotel B's attachment.
- **No public/static path.** The bytes are only ever served by
  :class:`ExpenseAttachmentStreamView` (``FileResponse``, ``inline``,
  ``no-store``). ``PRIVATE_MEDIA_ROOT`` is never routed through ``static()``.
- **Short-lived signed URLs.** So a plain ``<img>`` / PDF viewer can fetch the
  file without an ``Authorization`` header, the mint endpoint issues an HMAC
  token (``django.core.signing`` over ``SECRET_KEY``) bound to ``(expense,
  hotel)`` and valid for :data:`STREAM_TOKEN_MAX_AGE` seconds. The stream view
  accepts EITHER that token OR a normal authenticated ``expenses.view`` caller.

Endpoints (mounted under ``/api/v1/hotel/finance/`` — see ``urls.py``)::

    POST   finance/expenses/<pk>/attachment/       upload/replace  (update)
    DELETE finance/expenses/<pk>/attachment/       remove          (update)
    GET    finance/expenses/<pk>/attachment/url/    mint signed url (view)
    GET    finance/expenses/<pk>/attachment/file/   stream          (view | token)
"""
from __future__ import annotations

import mimetypes
import os

from django.core import signing
from django.http import FileResponse, Http404
from django.urls import reverse
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

from . import services
from .expense_validators import validate_expense_attachment
from .models import Expense

ExpView = HasHotelPermission("expenses.view")
ExpUpdate = HasHotelPermission("expenses.update")

# Signed short-lived stream token bound to (expense, hotel) — UNFORGEABLE by a
# client (HMAC over SECRET_KEY + salt). ``max_age`` enforces the short lifetime.
STREAM_TOKEN_SALT = "finance.expense.attachment.stream.v1"
STREAM_TOKEN_MAX_AGE = 300  # seconds (5 minutes)

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


def _serve_attachment(field_file) -> FileResponse:
    """Stream a private FieldFile inline, never cached, never sniffed."""
    content_type = _content_type_for(field_file.name)
    ext = os.path.splitext(field_file.name or "")[1].lower()
    try:
        handle = field_file.open("rb")
    except (FileNotFoundError, OSError) as exc:
        # The row still references a file that is no longer in storage — answer
        # a clean 404 instead of surfacing a 500 from the storage layer.
        raise Http404() from exc
    response = FileResponse(handle, content_type=content_type)
    # The on-disk name is an opaque uuid; expose a generic, PII-free filename.
    response["Content-Disposition"] = f'inline; filename="receipt{ext}"'
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response


class ExpenseAttachmentView(APIView):
    """Upload/replace (POST, multipart) or remove (DELETE) the single receipt.

    Both mutate the voucher, so both require ``expenses.update`` and run through
    the central service (posted + own open business date; a replaced/removed
    file is deleted so nothing orphans; locked after the day closes)."""

    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        return [ExpUpdate()]

    def post(self, request: Request, pk: int) -> Response:
        ensure_hotel_operational(request.hotel)
        expense = get_object_or_404(Expense, pk=pk, hotel=request.hotel)
        upload = request.FILES.get("file") or request.FILES.get("attachment")
        if upload is None:
            raise InvalidMediaFile({"reason": "no_file"})
        # Defence in depth: validate BEFORE writing anything to storage (the
        # FileField validators run again on save).
        validate_expense_attachment(upload)
        services.set_expense_attachment(expense, upload, user=request.user)
        return Response({"id": expense.id, "has_attachment": True})

    def delete(self, request: Request, pk: int) -> Response:
        ensure_hotel_operational(request.hotel)
        expense = get_object_or_404(Expense, pk=pk, hotel=request.hotel)
        services.remove_expense_attachment(expense, user=request.user)
        return Response({"id": expense.id, "has_attachment": False})


class ExpenseAttachmentSignedUrlView(APIView):
    """Mint a short-lived signed URL for the attachment (hotel-scoped)."""

    def get_permissions(self):
        return [ExpView()]

    def get(self, request: Request, pk: int) -> Response:
        expense = get_object_or_404(Expense, pk=pk, hotel=request.hotel)
        if not expense.attachment:
            raise Http404()
        token = signing.dumps(
            {"expense": expense.id, "hotel": expense.hotel_id},
            salt=STREAM_TOKEN_SALT,
        )
        stream_path = reverse("finance:expense-attachment-stream", kwargs={"pk": expense.id})
        url = request.build_absolute_uri(f"{stream_path}?token={token}")
        return Response({"url": url, "expires_in": STREAM_TOKEN_MAX_AGE})


class ExpenseAttachmentStreamView(APIView):
    """Stream the raw attachment bytes. Authorization accepts EITHER an
    authenticated ``expenses.view`` caller in the matching hotel context, OR a
    valid, unexpired signed ``token`` bound to this exact ``(expense, hotel)``.
    There is no public/static path to these bytes — this view is the only
    reader."""

    permission_classes = [AllowAny]

    def get(self, request: Request, pk: int) -> FileResponse:
        token = request.query_params.get("token")
        if token:
            expense = self._authorize_by_token(token, pk)
        else:
            expense = self._authorize_by_session(request, pk)
        if not expense.attachment:
            raise Http404()
        return _serve_attachment(expense.attachment)

    def _authorize_by_token(self, token: str, pk: int) -> Expense:
        try:
            payload = signing.loads(
                token, salt=STREAM_TOKEN_SALT, max_age=STREAM_TOKEN_MAX_AGE
            )
        except (signing.SignatureExpired, signing.BadSignature) as exc:
            raise PermissionDenied() from exc
        if not isinstance(payload, dict) or payload.get("expense") != pk:
            raise PermissionDenied()
        expense = get_object_or_404(Expense, pk=pk)
        if expense.hotel_id != payload.get("hotel"):
            raise PermissionDenied()
        return expense

    def _authorize_by_session(self, request: Request, pk: int) -> Expense:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise NotAuthenticated()
        if not user.is_active:
            raise UserInactive()
        context = resolve_hotel_context(request, required=True)
        hotel = context.hotel
        if not has_hotel_permission(user, hotel, "expenses.view"):
            raise PermissionDenied()
        return get_object_or_404(Expense, pk=pk, hotel=hotel)
