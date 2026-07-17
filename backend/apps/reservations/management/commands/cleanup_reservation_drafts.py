"""``cleanup_reservation_drafts`` — expire stale reserved reservation numbers
(Round 3 §7.3).

Marks every OPEN :class:`~apps.reservations.models.ReservationDraft` whose
``expires_at`` has passed as ``expired``. The reserved NUMBER is never reused (an
expired draft simply leaves a gap in the per-hotel sequence — the counter is
authoritative and monotonic), so this is a pure state transition with NO data
loss: no draft is deleted and no reservation is touched.

Idempotent: a second run finds nothing left to expire. Runs across all hotels by
default, or a single hotel with ``--hotel``.

Usage::

    python manage.py cleanup_reservation_drafts            # all hotels
    python manage.py cleanup_reservation_drafts --hotel 3  # one hotel
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.reservations.services import expire_stale_reservation_drafts


class Command(BaseCommand):
    help = (
        "Mark OPEN reservation drafts past their expiry as expired "
        "(reserved numbers are never reused; nothing is deleted)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hotel",
            type=int,
            default=None,
            help="Limit the cleanup to a single hotel id (default: all hotels).",
        )

    def handle(self, *args, **options):
        hotel_id = options.get("hotel")
        # Same behaviour as before — the sweep now lives in a reusable service so the
        # scheduled Celery task and this command share ONE implementation.
        expired = expire_stale_reservation_drafts(hotel_id=hotel_id)
        scope = f"hotel {hotel_id}" if hotel_id is not None else "all hotels"
        self.stdout.write(
            self.style.SUCCESS(
                f"Expired {expired} open reservation draft(s) past TTL ({scope})."
            )
        )
