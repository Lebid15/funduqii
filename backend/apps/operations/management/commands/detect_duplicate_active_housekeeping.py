"""Read-only preflight: detect rooms holding MORE THAN ONE active housekeeping
task BEFORE applying operations migration ``0003``.

Migration ``0003`` adds a partial-unique constraint
(``uniq_active_housekeeping_task_per_room``) that permits at most ONE ACTIVE
cleaning task per ``(hotel, room)``. This command scans for existing violations
so an operator runs it BEFORE ``migrate`` and STOPS if any are reported.

The migration itself performs NO automatic de-duplication: if duplicates
survive, PostgreSQL rejects the ``AddConstraint`` and NOTHING is changed. This
command is how the operator discovers that condition up front instead of hitting
a hard migrate failure — the resolution is always a manual, human decision
(never an auto-cancel / auto-delete / auto-select).

ACTIVE = pending / assigned / in_progress / awaiting_inspection (mirrors
``apps.operations.services.ACTIVE_HK_STATUSES``). Tasks with a NULL room
(historical, after room deletion via SET_NULL) are NOT constrained and NOT
reported.

Output carries only internal ids / task numbers / statuses (an operator report,
no guest PII). The command WRITES NOTHING and exits non-zero when any duplicate
group is found (0 when clean).

Usage::

    python manage.py detect_duplicate_active_housekeeping            # all hotels
    python manage.py detect_duplicate_active_housekeeping --hotel 12 # one hotel
"""
from __future__ import annotations

import sys

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.operations.models import HousekeepingTask
from apps.operations.services import ACTIVE_HK_STATUSES


class Command(BaseCommand):
    help = (
        "Read-only preflight that reports rooms with more than one ACTIVE "
        "housekeeping task (would violate uniq_active_housekeeping_task_per_room). "
        "Writes nothing; exits non-zero on duplicates."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hotel",
            type=int,
            default=None,
            help="Limit the scan to a single hotel id (default: all hotels).",
        )

    def handle(self, *args, **options):
        hotel_id = options.get("hotel")

        # Mirror the constraint scope exactly: ACTIVE statuses, room IS NOT NULL.
        base = HousekeepingTask.objects.filter(
            status__in=ACTIVE_HK_STATUSES, room__isnull=False
        )
        if hotel_id is not None:
            base = base.filter(hotel_id=hotel_id)

        dup_groups = (
            base.values("hotel_id", "room_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .order_by("hotel_id", "room_id")
        )

        duplicates = 0
        for group in dup_groups:
            duplicates += 1
            offenders = (
                base.filter(
                    hotel_id=group["hotel_id"], room_id=group["room_id"]
                )
                .order_by("id")
                .values_list("id", "task_number", "status")
            )
            rendered = ", ".join(
                f"#{tid}({num}:{st})" for tid, num, st in offenders
            )
            self.stdout.write(
                f"hotel={group['hotel_id']} room={group['room_id']} "
                f"active_tasks={group['n']} tasks=[{rendered}]"
            )

        if duplicates:
            self.stdout.write(
                self.style.ERROR(
                    f"\nSTOP: {duplicates} room(s) hold more than one ACTIVE "
                    "housekeeping task. Do NOT run migration 0003 - resolve each "
                    "room to a single active task manually (never auto-merged); "
                    "nothing was changed."
                )
            )
            sys.exit(1)

        self.stdout.write(
            self.style.SUCCESS(
                "No rooms with more than one active housekeeping task detected."
            )
        )
