"""Celery application for Funduqii.

The app is configured from Django settings (the ``CELERY_`` namespace) and
autodiscovers ``tasks.py`` modules. The scheduled work is defined statically in
``CELERY_BEAT_SCHEDULE`` (settings) and runs via ``celery -A config beat``
alongside the worker. Current operational task: hourly reservation-draft TTL
cleanup (``reservations.cleanup_reservation_drafts``). Other domains
(emails, notifications, reports, image processing, backups) are not wired yet.
"""
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("funduqii")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
