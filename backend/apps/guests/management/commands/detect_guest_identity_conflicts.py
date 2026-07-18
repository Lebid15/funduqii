"""Read-only preflight: detect guest-identity conflicts the NEW folding creates.

Run this BEFORE applying the guests identity migrations. It re-simulates the new
canonicalization (fold non-Latin digits, uppercase, alphanumeric-only for
ids/documents; E.164-style key for phones) directly from each active guest's RAW
fields, then groups by the three identity dimensions and reports any group with
more than one guest — plus any national-id vs national-id-document mismatch
(Decision 3). Output is PII-masked; the command WRITES, MERGES and DELETES
NOTHING and exits non-zero when any conflict is found (0 when clean).

Usage::

    python manage.py detect_guest_identity_conflicts            # all hotels
    python manage.py detect_guest_identity_conflicts --hotel 12 # one hotel
"""
from __future__ import annotations

import sys
from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.guests.models import Guest
from apps.guests.normalize import (
    normalize_document,
    normalize_id,
    normalize_phone,
)


def _mask(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return "∅"
    if len(s) <= 2:
        return "••"
    return "••••" + s[-2:]


class Command(BaseCommand):
    help = (
        "Read-only preflight that reports guest-identity conflicts the new "
        "normalization would create. Writes nothing; exits non-zero on conflicts."
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

        groups_nid: dict[tuple, list] = defaultdict(list)
        groups_doc: dict[tuple, list] = defaultdict(list)
        groups_phone: dict[tuple, list] = defaultdict(list)
        decision3: list[tuple] = []

        qs = Guest.objects.filter(is_active=True)
        if hotel_id is not None:
            qs = qs.filter(hotel_id=hotel_id)
        qs = qs.only(
            "id",
            "hotel_id",
            "phone",
            "national_id",
            "document_type",
            "document_number",
        )

        for g in qs.iterator():
            phone_key = normalize_phone(g.phone)
            doc_key = normalize_document(g.document_number)

            # Effective national id mirrors the migration's Decision-3 backfill.
            eff_nid_raw = g.national_id
            if g.document_type == "national_id" and (g.document_number or "").strip():
                current_nid_key = normalize_id(g.national_id)
                if not (g.national_id or "").strip():
                    eff_nid_raw = g.document_number
                elif current_nid_key == doc_key:
                    eff_nid_raw = g.national_id
                else:
                    decision3.append(
                        (g.hotel_id, g.id, g.national_id, g.document_number)
                    )
            nid_key = normalize_id(eff_nid_raw)

            if nid_key:
                groups_nid[(g.hotel_id, nid_key)].append(g.id)
            if doc_key:
                groups_doc[(g.hotel_id, g.document_type, doc_key)].append(g.id)
            if phone_key:
                groups_phone[(g.hotel_id, phone_key)].append(g.id)

        conflicts = 0

        def _emit_group(label, key_render, groups):
            nonlocal conflicts
            reported = False
            for key, ids in sorted(groups.items()):
                if len(ids) <= 1:
                    continue
                if not reported:
                    self.stdout.write(f"\n[{label}] duplicate identity groups:")
                    reported = True
                conflicts += 1
                joined = ",".join(str(i) for i in sorted(ids))
                self.stdout.write(f"  {key_render(key)} guests=[{joined}]")

        _emit_group(
            "national_id",
            lambda k: f"hotel={k[0]} national_id={_mask(k[1])}",
            groups_nid,
        )
        _emit_group(
            "document",
            lambda k: f"hotel={k[0]} type={k[1] or '∅'} number={_mask(k[2])}",
            groups_doc,
        )
        _emit_group(
            "phone",
            lambda k: f"hotel={k[0]} phone={_mask(k[1])}",
            groups_phone,
        )

        if decision3:
            self.stdout.write(
                "\n[national_id vs document] mismatched national-id identities "
                "(would STOP migration 0006):"
            )
            for hotel_id_, guest_id, nid_raw, doc_raw in decision3:
                conflicts += 1
                self.stdout.write(
                    f"  hotel={hotel_id_} guest={guest_id} "
                    f"national_id={_mask(nid_raw)} document_number={_mask(doc_raw)}"
                )

        if conflicts:
            self.stdout.write(
                self.style.ERROR(
                    f"\n{conflicts} conflict group(s) found. Resolve them manually "
                    "before migrating — nothing was changed."
                )
            )
            sys.exit(1)

        self.stdout.write(
            self.style.SUCCESS("No guest-identity conflicts detected.")
        )
