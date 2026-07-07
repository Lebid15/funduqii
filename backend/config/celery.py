"""Celery application for Funduqii.

Foundation only (Phase 1.5): the app is configured from Django settings (the
``CELERY_`` namespace) and autodiscovers ``tasks.py`` modules. No operational
tasks (emails, notifications, reports, expiries, image processing, backups)
exist yet — only a trivial health task.
"""
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("funduqii")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
