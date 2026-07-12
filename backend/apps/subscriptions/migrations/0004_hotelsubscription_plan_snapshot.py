"""Add ``plan_snapshot`` to HotelSubscription and backfill from the live plan.

Grandfathering (subscriptions final closure): a running subscription must read
its terms (price/limits/features) from a FROZEN snapshot, not from the live
plan — so editing a plan never changes an existing subscriber retroactively.

This migration is deliberately the ONLY one this round:
- additive + safe: the field is Nullable first,
- backfill copies every existing subscription's CURRENT plan into the snapshot,
  so applying it changes nothing a subscriber was already reading,
- no data is deleted; the reverse simply clears the snapshots.
"""
from __future__ import annotations

from django.db import migrations, models


def _plan_terms(plan) -> dict:
    return {
        "plan_id": plan.id,
        "plan_name": plan.name,
        "billing_cycle": plan.billing_cycle,
        "price": str(plan.price),
        "price_yearly": (
            str(plan.price_yearly) if plan.price_yearly is not None else None
        ),
        "currency": plan.currency,
        "room_limit": plan.room_limit,
        "user_limit": plan.user_limit,
        "feature_codes": list(plan.feature_codes or []),
        "max_public_bookings_per_month": plan.max_public_bookings_per_month,
        "trial_days": plan.trial_days,
    }


def backfill_snapshots(apps, schema_editor):
    HotelSubscription = apps.get_model("subscriptions", "HotelSubscription")
    qs = HotelSubscription.objects.select_related("plan").filter(
        plan_snapshot__isnull=True
    )
    for sub in qs.iterator():
        sub.plan_snapshot = _plan_terms(sub.plan)
        sub.save(update_fields=["plan_snapshot"])


def clear_snapshots(apps, schema_editor):
    HotelSubscription = apps.get_model("subscriptions", "HotelSubscription")
    HotelSubscription.objects.update(plan_snapshot=None)


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0003_hotelsubscription_hotel_subsc_hotel_i_6f5968_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="hotelsubscription",
            name="plan_snapshot",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_snapshots, clear_snapshots),
    ]
