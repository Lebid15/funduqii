"""Celery tasks for the reservations app.

Autodiscovered by ``config/celery.py`` (``app.autodiscover_tasks()``).

Scheduling: the periodic sweep is registered in ``CELERY_BEAT_SCHEDULE``
(``config/settings/base.py``) and runs HOURLY. In production it is dispatched by
a Celery Beat process started ALONGSIDE the worker::

    celery -A config worker -l info
    celery -A config beat   -l info

No secrets and no host-specific configuration live here; the broker/timezone come
from the standard ``CELERY_*`` settings.
"""
from __future__ import annotations

from celery import shared_task

from apps.reservations.services import expire_stale_reservation_drafts


@shared_task(name="reservations.cleanup_reservation_drafts")
def cleanup_reservation_drafts() -> int:
    """Expire OPEN reservation drafts whose TTL has lapsed (Round 3 §7.3).

    Thin wrapper over :func:`apps.reservations.services.expire_stale_reservation_drafts`
    — the SAME core the ``cleanup_reservation_drafts`` management command calls.
    Marks stale OPEN drafts as ``expired`` across ALL hotels; idempotent, no delete,
    no number reuse, no touch to final Reservations, and no folio/payment/availability
    side effect. Returns the number of drafts expired.
    """
    return expire_stale_reservation_drafts()
