"""Daily closing (Phase 12 final closure): add the stored, per-hotel
operational ``business_date`` and backfill it SAFELY.

Backfill rule per hotel:
- if the hotel has a CLOSED daily close: ``latest closed business_date + 1 day``
- otherwise: the current local date in the hotel's timezone.

A read-only PRE-CHECK runs first. Any anomaly that would make the seed
unreliable HALTS the migration with a precise report instead of guessing —
no old financial/operational date is ever touched.
"""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from django.db import migrations, models
from django.utils import timezone


def _local_date(tz_name):
    tz_name = (tz_name or "").strip()
    if tz_name:
        return timezone.now().astimezone(ZoneInfo(tz_name)).date()
    return timezone.localdate()


def backfill_business_date(apps, schema_editor):
    HotelSettings = apps.get_model("hotels", "HotelSettings")
    DailyClose = apps.get_model("shifts", "DailyClose")

    anomalies = []
    plans = []

    for s in HotelSettings.objects.all():
        # 1) timezone must be valid.
        try:
            local = _local_date(s.timezone)
        except Exception:
            anomalies.append((s.hotel_id, "invalid_timezone", repr(s.timezone)))
            continue

        closed = list(
            DailyClose.objects.filter(hotel_id=s.hotel_id, status="closed")
            .order_by("business_date")
            .values_list("business_date", flat=True)
        )
        # 2) a CLOSED day dated in the future is a contradiction.
        future_closed = [d for d in closed if d > local]
        if future_closed:
            anomalies.append((s.hotel_id, "closed_future_date", str(future_closed[-1])))
            continue

        # 3) a DRAFT dated in the future is a contradiction.
        if DailyClose.objects.filter(
            hotel_id=s.hotel_id, status="draft", business_date__gt=local
        ).exists():
            anomalies.append((s.hotel_id, "future_draft", str(local)))
            continue

        if closed:
            latest = closed[-1]
            candidate = latest + datetime.timedelta(days=1)
            # 4) the seed must be strictly AFTER the last closed day.
            if candidate <= latest:
                anomalies.append((s.hotel_id, "candidate_not_after_last_close", str(candidate)))
                continue
        else:
            candidate = local

        plans.append((s.pk, candidate))

    if anomalies:
        raise RuntimeError(
            "business_date backfill HALTED — resolve these hotels first: "
            + repr(anomalies)
        )

    for pk, candidate in plans:
        HotelSettings.objects.filter(pk=pk).update(business_date=candidate)


def noop_reverse(apps, schema_editor):
    # Reverse leaves the (additive) column in place and rewrites no data.
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("hotels", "0004_hotelsettings_cafe_enabled_and_more"),
        ("shifts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="hotelsettings",
            name="business_date",
            field=models.DateField(null=True, blank=True),
        ),
        migrations.RunPython(backfill_business_date, noop_reverse),
    ]
