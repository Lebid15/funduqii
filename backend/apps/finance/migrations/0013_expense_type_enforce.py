# EXPENSES-CLOSURE — enforce expense_type NOT NULL (forward-only).
#
# Guarded: aborts loudly if the 0012 backfill left ANY Expense without a type,
# so the schema change can never partially apply on real data. Reverse re-opens
# the column to NULL (matches 0011's additive state).
import django.db.models.deletion
from django.db import migrations, models


#: legacy category value -> seeded type name (mirrors 0012; inlined so the
#: migration never imports app code that may drift).
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
    return " ".join((name or "").split()).lower()


def heal_then_assert(apps, schema_editor):
    """Re-run the backfill for any straggler, THEN refuse to enforce on a leftover.

    A row can appear with a NULL type BETWEEN 0012 and 0013 when migrations run
    while the previous release is still serving traffic (rolling deploy). Hard
    failing there would abort the release for a single late row, so we heal it
    idempotently first — and still abort loudly if anything remains, so the
    column is never made NOT NULL while a violation exists.
    """
    ExpenseType = apps.get_model("finance", "ExpenseType")
    Expense = apps.get_model("finance", "Expense")
    db = schema_editor.connection.alias

    straggler_hotels = list(
        Expense.objects.using(db)
        .filter(expense_type__isnull=True)
        .values_list("hotel_id", flat=True)
        .distinct()
    )
    for hotel_id in straggler_hotels:
        type_id_by_value = {}
        for value, label in LEGACY_LABELS.items():
            obj, _ = ExpenseType.objects.using(db).get_or_create(
                hotel_id=hotel_id,
                name_normalized=_normalize(label),
                defaults={"name": label, "is_active": True},
            )
            type_id_by_value[value] = obj.id
        for value, type_id in type_id_by_value.items():
            Expense.objects.using(db).filter(
                hotel_id=hotel_id, category=value, expense_type__isnull=True
            ).update(expense_type_id=type_id)
        Expense.objects.using(db).filter(
            hotel_id=hotel_id, expense_type__isnull=True
        ).update(expense_type_id=type_id_by_value["other"])

    remaining = Expense.objects.using(db).filter(expense_type__isnull=True).count()
    if remaining:
        raise RuntimeError(
            f"EXPENSES-CLOSURE: refusing to enforce NOT NULL — {remaining} "
            f"expense row(s) still have no expense_type (backfill incomplete)."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0012_expense_type_backfill"),
    ]

    operations = [
        migrations.RunPython(heal_then_assert, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="expense",
            name="expense_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="expenses",
                to="finance.expensetype",
            ),
        ),
    ]
