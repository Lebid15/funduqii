"""Validation for expense attachments (EXPENSES-CLOSURE).

Defense in depth for a PRIVATE internal financial document, mirroring
``apps/reservations/document_validators.py``: we check the extension, the
declared content type, the byte size, AND the file's magic bytes. SVG and every
other markup / executable / unknown type are rejected because the signature
sniff never matches them. No Pillow / external dependency — a light signature
sniff is enough to confirm the format and block spoofed uploads.

Limits come from settings (``EXPENSE_ATTACH_*``), overridable per environment.
These are plain callables usable as Django ``validators=[...]`` on a FileField
and reusable from the upload serializer/endpoint.
"""
from __future__ import annotations

from django.conf import settings

from apps.common.exceptions import InvalidMediaFile


def _sniff_attachment_kind(header: bytes) -> str | None:
    """Return a normalized format from magic bytes, or None if unrecognized.

    Covers the raster images we allow plus PDF. SVG (an XML text format) has no
    binary signature here and is therefore rejected, as is anything else.
    """
    if header[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    if header[:5] == b"%PDF-":
        return "pdf"
    return None


def _extension_of(file) -> str:
    name = (getattr(file, "name", "") or "").lower()
    return name.rsplit(".", 1)[-1] if "." in name else ""


def validate_attachment_extension(file) -> None:
    """Reject a file whose extension is not in the allowlist."""
    if _extension_of(file) not in settings.EXPENSE_ATTACH_ALLOWED_EXTENSIONS:
        raise InvalidMediaFile(
            {
                "reason": "extension",
                "allowed": list(settings.EXPENSE_ATTACH_ALLOWED_EXTENSIONS),
            }
        )


def validate_attachment_size(file) -> None:
    """Reject a file larger than ``EXPENSE_ATTACH_MAX_BYTES``."""
    size = getattr(file, "size", 0) or 0
    limit = settings.EXPENSE_ATTACH_MAX_BYTES
    if size > limit:
        raise InvalidMediaFile({"reason": "size", "max_bytes": limit})


def validate_attachment_signature(file) -> None:
    """Reject a file whose magic bytes are not an allowed image or PDF.

    Also enforces the declared content-type allowlist (when present) and, most
    importantly, sniffs the leading bytes so a spoofed extension / content type
    cannot smuggle in SVG or any other unexpected format.
    """
    content_type = getattr(file, "content_type", "") or ""
    if content_type and content_type not in settings.EXPENSE_ATTACH_ALLOWED_CONTENT_TYPES:
        raise InvalidMediaFile({"reason": "content_type"})

    try:
        file.seek(0)
        header = file.read(12)
    finally:
        try:
            file.seek(0)
        except (ValueError, OSError):  # pragma: no cover - defensive
            pass
    if _sniff_attachment_kind(header) is None:
        raise InvalidMediaFile({"reason": "signature"})


def validate_expense_attachment(file) -> None:
    """Run the full extension + content-type + size + signature check, or raise.

    Convenience entry point (reused by the upload serializer/endpoint). Raises
    :class:`InvalidMediaFile` (400) with a specific ``details.reason`` so the UI
    can show the right translated message.
    """
    validate_attachment_extension(file)
    validate_attachment_size(file)
    validate_attachment_signature(file)
