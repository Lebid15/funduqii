"""Private storage for reservation guest documents (RESERVATIONS-FORM-REWORK).

These files are guest identity documents (national ID / passport / residence /
visa / marriage contract / ...) and are STRICTLY PRIVATE. They are stored under
``settings.PRIVATE_MEDIA_ROOT``, which is OUTSIDE ``MEDIA_ROOT`` and is NEVER
routed through ``config/urls.py``'s ``static()`` (nor WhiteNoise). The only
sanctioned way to read them is an authenticated, permission-checked streaming
view (a later pass) — there is no public URL for these files.

The ``upload_to`` callable produces an OPAQUE, PII-free path::

    reservations/<hotel_id>/<reservation_id>/<uuid4hex><ext>

- The on-disk basename is a random ``uuid4().hex`` — the original filename
  (which may carry the guest's name) is discarded, so nothing on disk leaks
  identity.
- ``<ext>`` is derived from the uploaded name but constrained to the allowlist
  (:data:`settings.RESERVATION_DOC_ALLOWED_EXTENSIONS`); an unknown / absent
  extension falls back to ``.bin`` so a crafted name can never inject path
  separators or traversal sequences.
- ``hotel_id`` / ``reservation_id`` are read from the model instance and coerced
  to ints, so no caller-controlled string can escape the per-tenant tree.
"""
from __future__ import annotations

import os
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateDocumentStorage(FileSystemStorage):
    """A ``FileSystemStorage`` bound to ``settings.PRIVATE_MEDIA_ROOT``.

    The location is resolved from settings on every instantiation (so it stays
    correct across environments and is overridable in tests via
    ``override_settings``). ``base_url`` is ``None`` on purpose: these files are
    never addressable by a URL, so ``url()`` will raise if ever called.

    ``deconstruct`` returns the bare class path with no arguments so migrations
    NEVER bake in an environment-specific absolute path — the location is always
    re-resolved from settings at runtime.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", str(settings.PRIVATE_MEDIA_ROOT))
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        return ("apps.reservations.document_storage.PrivateDocumentStorage", [], {})


# The single shared storage instance referenced by the model FileFields.
private_document_storage = PrivateDocumentStorage()


def _as_int(value) -> int:
    """Coerce an id-like value to int, defaulting to 0 (e.g. unsaved instance)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_ext(filename: str) -> str:
    """Return a leading-dot extension from the allowlist, else ``.bin``.

    The incoming name is only ever trusted for the extension text; the result
    is always one of the allowed extensions (lower-cased) so a crafted name can
    never inject separators or traversal sequences into the stored path.
    """
    ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
    allowed = {e.lower() for e in settings.RESERVATION_DOC_ALLOWED_EXTENSIONS}
    if ext in allowed:
        return f".{ext}"
    return ".bin"


def reservation_document_upload_to(instance, filename: str) -> str:
    """Opaque, tenant-namespaced upload path for a reservation-document file.

    ``instance`` is a ``ReservationDocument``. ``hotel_id`` / ``reservation_id``
    are read defensively and coerced to ints; the basename is a fresh
    ``uuid4().hex`` — no original filename, no PII.
    """
    hotel_id = _as_int(getattr(instance, "hotel_id", None))
    reservation_id = _as_int(getattr(instance, "reservation_id", None))
    ext = _safe_ext(filename)
    return f"reservations/{hotel_id}/{reservation_id}/{uuid.uuid4().hex}{ext}"
