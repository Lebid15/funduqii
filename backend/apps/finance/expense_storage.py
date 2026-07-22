"""Private storage for expense attachments (EXPENSES-CLOSURE).

An expense may carry ONE optional receipt/voucher scan. These files are
INTERNAL financial documents and are STRICTLY PRIVATE — stored under
``settings.PRIVATE_MEDIA_ROOT`` (OUTSIDE ``MEDIA_ROOT``), NEVER routed through
``config/urls.py``'s ``static()`` / WhiteNoise. The only sanctioned way to read
one is an authenticated, ``expenses.view``-gated streaming view; there is no
public URL for these files. Mirrors ``apps.reservations.document_storage``.

The ``upload_to`` callable produces an OPAQUE, PII-free path::

    expenses/<hotel_id>/<expense_id>/<uuid4hex><ext>

- The on-disk basename is a random ``uuid4().hex`` — the original filename is
  discarded, so nothing on disk leaks a vendor/description.
- ``<ext>`` is derived from the uploaded name but constrained to the allowlist
  (:data:`settings.EXPENSE_ATTACH_ALLOWED_EXTENSIONS`); an unknown / absent
  extension falls back to ``.bin`` so a crafted name can never inject path
  separators or traversal sequences.
- ``hotel_id`` / ``expense_id`` are read from the model instance and coerced to
  ints, so no caller-controlled string can escape the per-tenant tree.
"""
from __future__ import annotations

import os
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateExpenseStorage(FileSystemStorage):
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

    def url(self, name):
        """Private files have NO public URL — always raise.

        ``FileSystemStorage.base_url`` silently falls back to
        ``settings.MEDIA_URL`` when it is ``None``, so relying on the ``None``
        alone would hand out a ``/media/...`` link that merely happens not to
        resolve. Raising here makes the documented guarantee REAL: the only way
        to read these bytes is the gated streaming view.
        """
        raise ValueError(
            "Expense attachments are private and have no public URL; serve them "
            "through the permission-gated streaming view."
        )

    def deconstruct(self):
        return ("apps.finance.expense_storage.PrivateExpenseStorage", [], {})


# The single shared storage instance referenced by the model FileField.
private_expense_storage = PrivateExpenseStorage()


def _as_int(value) -> int:
    """Coerce an id-like value to int, defaulting to 0 (e.g. unsaved instance)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_ext(filename: str) -> str:
    """Return a leading-dot extension from the allowlist, else ``.bin``.

    The incoming name is only ever trusted for the extension text; the result is
    always one of the allowed extensions (lower-cased) so a crafted name can
    never inject separators or traversal sequences into the stored path.
    """
    ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
    allowed = {e.lower() for e in settings.EXPENSE_ATTACH_ALLOWED_EXTENSIONS}
    if ext in allowed:
        return f".{ext}"
    return ".bin"


def expense_attachment_upload_to(instance, filename: str) -> str:
    """Opaque, tenant-namespaced upload path for an expense attachment.

    ``instance`` is an ``Expense``. ``hotel_id`` / ``id`` are read defensively
    and coerced to ints; the basename is a fresh ``uuid4().hex`` — no original
    filename, no PII.
    """
    hotel_id = _as_int(getattr(instance, "hotel_id", None))
    expense_id = _as_int(getattr(instance, "id", None))
    ext = _safe_ext(filename)
    return f"expenses/{hotel_id}/{expense_id}/{uuid.uuid4().hex}{ext}"
