"""Protect block-log history from a guest hard-delete.

``GuestBlockLog.guest`` moves from CASCADE to PROTECT: a guest that carries any
block-log entry can no longer be hard-deleted out from under its security
history (the delete service already routes such a guest to deactivation). Pure
schema change; reverses automatically to CASCADE.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guests", "0007_guest_identity_constraints"),
    ]

    operations = [
        migrations.AlterField(
            model_name="guestblocklog",
            name="guest",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="block_logs",
                to="guests.guest",
            ),
        ),
    ]
