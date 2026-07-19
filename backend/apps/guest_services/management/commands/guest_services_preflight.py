"""``guest_services_preflight`` — a READ-ONLY pre-release reporter (P11).

Reports POTENTIAL data conditions relevant to the guest extra-services flow and
STOPS. It writes NOTHING: no migration, no FIN-F2 constraint, no dedup, no
cleanup, no data change. It NEVER reads live catalog rates and prints NO guest
names / documents / amounts — only neutral ids and counts.

It reports three conditions (exiting NON-ZERO when any is found, like the stays
``check_missing_stay_rates`` precheck):

1. FIN-F2 structural gap — a reservation that holds BOTH an OPEN stay folio AND
   an OPEN reservation-only folio (the gap the finance code guards at runtime;
   the FIN-F2 constraint / migration M3 is deliberately EXCLUDED from this task).
2. Legacy unlinked ROOM charges — a POSTED ``ChargeType.ROOM`` charge with a NULL
   ``room_night`` (an unlinked room charge that predates the room-night key).
3. Orphan / broken guest-service financial links — a POSTED
   ``guest_extra_service`` charge with NO ``GuestServicePosting``, or a
   ``GuestServicePosting`` whose underlying charge is VOIDED.

Usage::

    python manage.py guest_services_preflight            # all hotels
    python manage.py guest_services_preflight --hotel 3  # one hotel
"""
from __future__ import annotations

import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "READ-ONLY report of FIN-F2 / legacy unlinked ROOM room_night / orphan "
        "guest-service financial-link conditions; writes nothing, exits non-zero "
        "if any condition is found."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hotel",
            type=int,
            default=None,
            help="Limit the report to a single hotel id (default: all hotels).",
        )

    def handle(self, *args, **options):
        from apps.finance.constants import ChargeSource
        from apps.finance.models import (
            ChargeType,
            Folio,
            FolioCharge,
            FolioStatus,
            PostingStatus,
        )
        from apps.guest_services.models import GuestServicePosting

        hotel_id = options.get("hotel")

        def _scope(qs, field="hotel_id"):
            return qs.filter(**{field: hotel_id}) if hotel_id is not None else qs

        findings = 0

        # 1) FIN-F2: reservations with an OPEN stay folio AND an OPEN reservation
        #    -only folio at the same time.
        open_stay_res_ids = set(
            _scope(
                Folio.objects.filter(
                    status=FolioStatus.OPEN,
                    stay__isnull=False,
                    reservation__isnull=False,
                )
            ).values_list("reservation_id", flat=True)
        )
        fin_f2 = (
            _scope(
                Folio.objects.filter(
                    status=FolioStatus.OPEN,
                    stay__isnull=True,
                    reservation__isnull=False,
                )
            )
            .filter(reservation_id__in=open_stay_res_ids)
            .values_list("reservation_id", flat=True)
            .distinct()
        )
        fin_f2_ids = sorted(set(fin_f2))
        if fin_f2_ids:
            findings += len(fin_f2_ids)
            self.stdout.write(
                f"FIN-F2 gap: {len(fin_f2_ids)} reservation(s) with BOTH an open "
                f"stay folio and an open reservation-only folio: {fin_f2_ids}"
            )

        # 2) Legacy unlinked ROOM charges (posted ROOM charge, room_night NULL).
        unlinked = _scope(
            FolioCharge.objects.filter(
                type=ChargeType.ROOM,
                status=PostingStatus.POSTED,
                room_night__isnull=True,
            )
        )
        unlinked_count = unlinked.count()
        if unlinked_count:
            findings += unlinked_count
            sample = list(unlinked.values_list("id", flat=True)[:20])
            self.stdout.write(
                f"Legacy unlinked ROOM charges (room_night IS NULL): "
                f"{unlinked_count}; sample charge ids: {sample}"
            )

        # 3a) Orphan guest-service charges (posted guest_extra_service charge with
        #     NO GuestServicePosting). The charge -> posting reverse accessor is
        #     deliberately DISABLED (``related_name="+"`` — the no-FK rule), so this
        #     inverts the query via the set of linked charge ids instead.
        linked_charge_ids = GuestServicePosting.objects.values_list(
            "folio_charge_id", flat=True
        )
        orphan_charges = _scope(
            FolioCharge.objects.filter(
                source=ChargeSource.GUEST_EXTRA_SERVICE,
                status=PostingStatus.POSTED,
            ).exclude(id__in=linked_charge_ids)
        )
        orphan_count = orphan_charges.count()
        if orphan_count:
            findings += orphan_count
            sample = list(orphan_charges.values_list("id", flat=True)[:20])
            self.stdout.write(
                f"Orphan guest-service charges (no GuestServicePosting): "
                f"{orphan_count}; sample charge ids: {sample}"
            )

        # 3b) Postings pointing at a VOIDED charge (financial link went stale).
        voided_link = _scope(
            GuestServicePosting.objects.filter(
                folio_charge__status=PostingStatus.VOIDED
            )
        )
        voided_link_count = voided_link.count()
        if voided_link_count:
            findings += voided_link_count
            sample = list(voided_link.values_list("id", flat=True)[:20])
            self.stdout.write(
                f"Guest-service postings on a VOIDED charge: {voided_link_count}; "
                f"sample posting ids: {sample}"
            )

        scope = f"hotel {hotel_id}" if hotel_id is not None else "all hotels"
        summary = (
            f"guest_services preflight ({scope}): {findings} potential "
            f"condition(s) found. No data was changed (read-only)."
        )
        if findings:
            self.stderr.write(self.style.WARNING(summary))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS(summary))
