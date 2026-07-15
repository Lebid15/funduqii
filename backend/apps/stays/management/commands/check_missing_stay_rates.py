"""``check_missing_stay_rates`` — a READ-ONLY pre-release audit (STAYS
rate-integrity remediation, item 4).

Lists every IN_HOUSE stay that lacks full POSITIVE-rate coverage for its DUE
nights — a rate gap that would block posting / checkout / daily close — and exits
NON-ZERO when any gap exists.

Safety: it NEVER reads live ``RoomType`` rates, never auto-fixes anything, and
prints NO guest names or documents (only hotel id, stay id, planned dates, and the
specific uncovered night dates).

Usage::

    python manage.py check_missing_stay_rates            # all hotels
    python manage.py check_missing_stay_rates --hotel 3  # one hotel
"""
from __future__ import annotations

import sys

from django.core.management.base import BaseCommand

from apps.stays.models import Stay, StayStatus
from apps.stays.rate_periods import uncovered_billable_nights


class Command(BaseCommand):
    help = (
        "Audit IN_HOUSE stays for room nights lacking a positive agreed rate; "
        "exit non-zero if any stay has a coverage gap."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hotel",
            type=int,
            default=None,
            help="Limit the audit to a single hotel id (default: all hotels).",
        )

    def handle(self, *args, **options):
        qs = (
            Stay.objects.filter(status=StayStatus.IN_HOUSE)
            .select_related("hotel", "hotel__settings")
            .prefetch_related("rate_periods")
            .order_by("hotel_id", "id")
        )
        hotel_id = options.get("hotel")
        if hotel_id is not None:
            qs = qs.filter(hotel_id=hotel_id)

        total_stays = 0
        flagged = 0
        for stay in qs:
            total_stays += 1
            gaps = uncovered_billable_nights(stay)
            if not gaps:
                continue
            flagged += 1
            nights = ", ".join(n.isoformat() for n in gaps)
            self.stdout.write(
                f"hotel={stay.hotel_id} stay={stay.id} "
                f"check_in={stay.planned_check_in_date} "
                f"check_out={stay.planned_check_out_date} "
                f"uncovered_nights=[{nights}]"
            )

        summary = (
            f"Checked {total_stays} in-house stay(s); "
            f"{flagged} with missing positive-rate coverage."
        )
        if flagged:
            self.stderr.write(self.style.ERROR(summary))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS(summary))
