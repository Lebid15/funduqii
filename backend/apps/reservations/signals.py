"""Signal receivers for the reservations app.

DI-F3: :class:`~apps.reservations.models.ReservationDocument` stores its front /
back images on the PRIVATE document storage. When the row is deleted — directly
or via a CASCADE (e.g. a hotel or reservation delete) — Django removes the DB
record but does NOT delete the underlying file bytes. That would leave orphaned
PII files under ``private_media/``. This ``post_delete`` receiver deletes both
files from storage after the row is gone, so private documents never outlive
their record.
"""
from __future__ import annotations

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ReservationDocument


@receiver(
    post_delete,
    sender=ReservationDocument,
    dispatch_uid="reservations.reservation_document_cleanup_files",
)
def cleanup_reservation_document_files(sender, instance, **kwargs) -> None:
    """Delete the private front/back files when a document row is deleted.

    Guards for empty fields and uses ``field.delete(save=False)`` (the row is
    already gone, so there is nothing to save). Mirrors the delete-on-replace
    pattern already used in ``document_views.py`` so a missing/already-removed
    file is handled gracefully by the storage backend during a cascade.
    """
    for field_name in ("front_file", "back_file"):
        field_file = getattr(instance, field_name, None)
        if field_file:
            field_file.delete(save=False)
