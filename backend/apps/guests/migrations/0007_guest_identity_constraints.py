"""Swap the guest-identity uniqueness constraints onto the NORMALIZED keys.

Runs only after ``0006`` has recomputed every key and proven there are no
national-id collisions. A RunPython pre-check first guarantees there are no
PHONE or DOCUMENT duplicates either, so the ``AddConstraint`` steps raise a clean
PII-masked error instead of a raw IntegrityError.

Constraints after this migration (all partial, portable on SQLite + PostgreSQL):
  - ``unique_guest_document_normalized_per_hotel`` — (hotel, document_type,
    document_number_normalized) where the normalized number is non-empty. Keeps
    ``document_type`` (passport stays a normal passport row). Replaces the raw
    ``unique_guest_document_per_hotel`` from ``0001``.
  - ``unique_guest_national_id_per_hotel`` — unchanged here; LIFETIME uniqueness
    (not is_active-scoped).
  - ``unique_guest_phone_per_hotel_active`` — (hotel, phone_normalized) where the
    phone is non-empty AND ``is_active=True``: a deactivated guest never blocks
    reusing a phone for a live profile.

reverse: constraint add/remove operations reverse automatically (restoring the
raw document constraint); the pre-check reverses to a noop.
"""
import re

from django.db import migrations, models
from django.db.models import Count


def _mask(value):
    s = (value or "").strip()
    if not s:
        return "∅"
    if len(s) <= 2:
        return "••"
    return "••••" + s[-2:]


def _precheck(apps, schema_editor):
    Guest = apps.get_model("guests", "Guest")

    # Phone dimension mirrors the ACTIVE-scoped constraint.
    phone_dups = (
        Guest.objects.filter(is_active=True)
        .exclude(phone_normalized="")
        .values("hotel_id", "phone_normalized")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .order_by()
    )
    # Document dimension mirrors the LIFETIME constraint (all rows, any state).
    doc_dups = (
        Guest.objects.exclude(document_number_normalized="")
        .values("hotel_id", "document_type", "document_number_normalized")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .order_by()
    )

    problems = []
    for row in phone_dups:
        problems.append(
            f"  [phone] hotel={row['hotel_id']} "
            f"phone={_mask(row['phone_normalized'])} count={row['n']}"
        )
    for row in doc_dups:
        problems.append(
            f"  [document] hotel={row['hotel_id']} "
            f"type={row['document_type'] or '∅'} "
            f"number={_mask(row['document_number_normalized'])} count={row['n']}"
        )
    if problems:
        raise RuntimeError(
            "Guest identity migration 0007 STOPPED — duplicates would violate the "
            "new uniqueness constraints. No constraint was added. De-duplicate "
            "these first (never auto-merged):\n" + "\n".join(problems)
        )


class Migration(migrations.Migration):

    dependencies = [
        ("guests", "0006_recompute_guest_identity_keys"),
    ]

    operations = [
        migrations.RunPython(_precheck, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="guest",
            name="unique_guest_document_per_hotel",
        ),
        migrations.AddConstraint(
            model_name="guest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("document_number_normalized", ""), _negated=True),
                fields=("hotel", "document_type", "document_number_normalized"),
                name="unique_guest_document_normalized_per_hotel",
            ),
        ),
        migrations.AddConstraint(
            model_name="guest",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("is_active", True),
                    models.Q(("phone_normalized", ""), _negated=True),
                ),
                fields=("hotel", "phone_normalized"),
                name="unique_guest_phone_per_hotel_active",
            ),
        ),
    ]
