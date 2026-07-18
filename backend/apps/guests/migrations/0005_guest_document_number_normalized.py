"""Add the canonical ``document_number_normalized`` key column.

Schema-only and fully reversible (reverse = RemoveField). The column lands blank
for every existing row; the data migration ``0006`` recomputes it. The
uniqueness constraint that uses it is added later, in ``0007`` — after ``0006``
has both populated the column and guaranteed there are no collisions — so this
migration can never fail on existing data.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guests", "0004_remove_guest_unique_guest_national_id_per_hotel_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="guest",
            name="document_number_normalized",
            field=models.CharField(
                blank=True, db_index=True, default="", max_length=80
            ),
        ),
    ]
