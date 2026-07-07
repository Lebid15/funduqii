"""Hotel media services — safe create/replace/reorder logic (Phase 4).

Rules enforced here (never in the view or serializer):
- The file is validated BEFORE any DB write, so a bad upload never disturbs
  existing media.
- Uploading a new logo/cover deactivates the previous active one inside the same
  transaction, so the "one active per hotel" invariant holds and the old file is
  never removed before the new one is safely stored.
- Gallery uploads are capped at a configurable maximum active count.
"""
from __future__ import annotations

from django.conf import settings
from django.db import transaction

from apps.common.exceptions import MediaLimitReached

from .models import HotelMedia, MediaKind
from .validators import validate_image_upload


def active_gallery_count(hotel) -> int:
    return HotelMedia.objects.filter(
        hotel=hotel, kind=MediaKind.GALLERY, is_active=True
    ).count()


@transaction.atomic
def create_media(*, hotel, kind: str, file, alt_text: str, user) -> HotelMedia:
    # Validate first — raises before touching any existing media.
    validate_image_upload(file, kind)

    if kind in (MediaKind.LOGO, MediaKind.COVER):
        # Deactivate the current active one first so the partial-unique
        # constraint is satisfied when the new active row is created.
        HotelMedia.objects.filter(
            hotel=hotel, kind=kind, is_active=True
        ).update(is_active=False)
    elif kind == MediaKind.GALLERY:
        if active_gallery_count(hotel) >= settings.HOTEL_MEDIA_GALLERY_MAX_COUNT:
            raise MediaLimitReached(
                {"max_count": settings.HOTEL_MEDIA_GALLERY_MAX_COUNT}
            )

    next_order = 0
    if kind == MediaKind.GALLERY:
        last = (
            HotelMedia.objects.filter(hotel=hotel, kind=MediaKind.GALLERY)
            .order_by("-sort_order")
            .first()
        )
        next_order = (last.sort_order + 1) if last else 0

    return HotelMedia.objects.create(
        hotel=hotel,
        kind=kind,
        file=file,
        alt_text=alt_text or "",
        sort_order=next_order,
        is_active=True,
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
    )


@transaction.atomic
def activate_media(media: HotelMedia) -> HotelMedia:
    """Re-activate a logo/cover, deactivating any current active of that kind."""
    if media.kind in (MediaKind.LOGO, MediaKind.COVER):
        HotelMedia.objects.filter(
            hotel=media.hotel, kind=media.kind, is_active=True
        ).exclude(pk=media.pk).update(is_active=False)
    media.is_active = True
    media.save(update_fields=["is_active", "updated_at"])
    return media


def delete_media(media: HotelMedia) -> None:
    """Hard-delete a media row and its stored file."""
    stored = media.file
    media.delete()
    if stored:
        stored.delete(save=False)
