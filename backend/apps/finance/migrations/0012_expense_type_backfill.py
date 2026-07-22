# EXPENSES-CLOSURE — data migration (forward-only, reversible, no row loss).
#
# Seeds a per-hotel set of ExpenseType rows from the seven canonical legacy
# ``ExpenseCategory`` values, then backfills every existing Expense's
# ``expense_type`` from its legacy ``category`` string. Runs for every hotel
# that has any Expense row, so migration 0013 can safely enforce NOT NULL.
#
# Reverse simply nulls ``expense_type`` back out (the seeded rows are dropped by
# reversing 0011's CreateModel); no expense row is ever deleted or mutated
# beyond this FK.
from django.db import migrations

#: legacy category value -> the English name used to seed/lookup the type.
LEGACY_LABELS = {
    "operations": "Operations",
    "maintenance": "Maintenance",
    "supplies": "Supplies",
    "marketing": "Marketing",
    "salary": "Salary",
    "utilities": "Utilities",
    "other": "Other",
}


def _normalize(name: str) -> str:
    """Same canonical form as models.normalize_expense_type_name (inlined so the
    migration never imports app code that may drift)."""
    return " ".join((name or "").split()).lower()


def seed_and_backfill(apps, schema_editor):
    ExpenseType = apps.get_model("finance", "ExpenseType")
    Expense = apps.get_model("finance", "Expense")
    Hotel = apps.get_model("tenancy", "Hotel")
    db = schema_editor.connection.alias

    # Seed the canonical catalogue for EVERY hotel — not only those that already
    # have expenses. A hotel with no expense history would otherwise start with
    # an EMPTY type list, and an `expenses.create`-only user could never record
    # an expense (the type is required) until someone with `manage_types` added
    # one. The union with the expense-owning hotels keeps the backfill complete
    # even if a row somehow references a hotel row that is gone.
    hotel_ids = set(Hotel.objects.using(db).values_list("id", flat=True))
    hotel_ids |= set(
        Expense.objects.using(db).values_list("hotel_id", flat=True).distinct()
    )
    for hotel_id in sorted(hotel_ids):
        # Seed the canonical types for this hotel (idempotent on normalized name).
        type_id_by_value = {}
        for value, label in LEGACY_LABELS.items():
            obj, _ = ExpenseType.objects.using(db).get_or_create(
                hotel_id=hotel_id,
                name_normalized=_normalize(label),
                defaults={"name": label, "is_active": True},
            )
            type_id_by_value[value] = obj.id
        # Backfill each category with one bulk UPDATE, then a catch-all for any
        # blank/unknown legacy value -> the "Other" type. Only touches NULLs.
        for value, type_id in type_id_by_value.items():
            Expense.objects.using(db).filter(
                hotel_id=hotel_id, category=value, expense_type__isnull=True
            ).update(expense_type_id=type_id)
        Expense.objects.using(db).filter(
            hotel_id=hotel_id, expense_type__isnull=True
        ).update(expense_type_id=type_id_by_value["other"])


def unbackfill(apps, schema_editor):
    Expense = apps.get_model("finance", "Expense")
    db = schema_editor.connection.alias
    Expense.objects.using(db).update(expense_type=None)


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0011_expense_type_fx_attachment_idempotency"),
        ("tenancy", "0003_hotel_status_changed_at_hotel_status_changed_by_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_and_backfill, unbackfill),
    ]
