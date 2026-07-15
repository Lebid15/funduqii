# STAYS PR #43 — FIX-6 (nightly_rate backfill for pre-existing in-house stays).
#
# Migration 0002 added ``Stay.nightly_rate`` (the per-stay AGREED rate SNAPSHOT
# captured at check-in). Stays that were ALREADY in-house when 0002 ran have it
# NULL, so during the transitional window ``finance.services._stay_room_rate``
# would fall back to the LIVE ``RoomType.base_rate`` for their remaining nights —
# a later base-rate change could then move an in-progress stay's bill, which the
# snapshot exists to prevent.
#
# This data step backfills the snapshot for those stays from their reservation
# line's room type base rate, and ONLY when that rate is priced (> 0). It is:
#   * idempotent   — only NULL snapshots on IN_HOUSE stays are touched;
#   * conservative — unpriced (NULL / <= 0) base rates are left NULL (the night
#                    service already treats a NULL snapshot as "fall back / skip");
#   * reversible   — the reverse is a deliberate no-op (a snapshot is not data we
#                    would want to destroy on a downgrade; 0002's reverse drops
#                    the whole column if the field itself is removed).
from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations

TWO = Decimal("0.01")


def backfill_nightly_rate(apps, schema_editor):
    Stay = apps.get_model("stays", "Stay")
    db = schema_editor.connection.alias
    stays = (
        Stay.objects.using(db)
        .filter(
            status="in_house",
            nightly_rate__isnull=True,
            reservation_line__isnull=False,
        )
        .select_related("reservation_line__room_type")
    )
    for stay in stays.iterator():
        line = stay.reservation_line
        room_type = getattr(line, "room_type", None)
        base_rate = getattr(room_type, "base_rate", None)
        if base_rate is None:
            continue
        rate = Decimal(base_rate).quantize(TWO, rounding=ROUND_HALF_UP)
        if rate <= 0:
            continue
        stay.nightly_rate = rate
        stay.save(update_fields=["nightly_rate"])


def reverse_noop(apps, schema_editor):
    # The backfilled snapshot is intentionally kept on reverse — clearing it would
    # re-open the exact live-rate drift this migration closes.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("stays", "0002_stay_nightly_rate"),
    ]

    operations = [
        migrations.RunPython(backfill_nightly_rate, reverse_noop),
    ]
