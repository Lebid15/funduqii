"""Image upload validation for hotel media (Phase 4).

Defense in depth: we check the extension, the declared content type, AND the
file's magic bytes, and we reject SVG outright (no executable/markup images).
No Pillow dependency — a light signature sniff is enough to confirm the raster
format and block spoofed uploads. Size limits are per media kind.
"""
from __future__ import annotations

from django.conf import settings

from apps.common.exceptions import InvalidMediaFile
from apps.hotels.models import MediaKind

_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def max_bytes_for_kind(kind: str) -> int:
    if kind == MediaKind.LOGO:
        return settings.HOTEL_MEDIA_LOGO_MAX_BYTES
    if kind == MediaKind.COVER:
        return settings.HOTEL_MEDIA_COVER_MAX_BYTES
    return settings.HOTEL_MEDIA_GALLERY_MAX_BYTES


def _sniff_image_kind(header: bytes) -> str | None:
    """Return a normalized format from magic bytes, or None if unrecognized."""
    if header[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None


def validate_image_upload(file, kind: str) -> None:
    """Validate an uploaded image for the given media kind, or raise.

    Raises :class:`InvalidMediaFile` (400) with a specific ``details.reason`` so
    the UI can show the right translated message.
    """
    name = (getattr(file, "name", "") or "").lower()
    extension = name.rsplit(".", 1)[-1] if "." in name else ""

    if extension not in settings.HOTEL_MEDIA_ALLOWED_EXTENSIONS:
        raise InvalidMediaFile(
            {"reason": "extension", "allowed": settings.HOTEL_MEDIA_ALLOWED_EXTENSIONS}
        )

    content_type = getattr(file, "content_type", "") or ""
    if content_type and content_type not in _ALLOWED_CONTENT_TYPES:
        raise InvalidMediaFile({"reason": "content_type"})

    size = getattr(file, "size", 0) or 0
    limit = max_bytes_for_kind(kind)
    if size > limit:
        raise InvalidMediaFile({"reason": "size", "max_bytes": limit})

    # Magic-byte sniff (also rejects SVG/markup, which never matches).
    try:
        file.seek(0)
        header = file.read(12)
    finally:
        file.seek(0)
    if _sniff_image_kind(header) is None:
        raise InvalidMediaFile({"reason": "signature"})
