"""Add notification/activity SCOPE (hotel|platform) + optional DEDUP_KEY.

Notifications final closure. This is deliberately the ONLY migration this round:
- ``scope`` on both ActivityEvent and Notification (default ``hotel``), so every
  existing row is backfilled to ``hotel`` by the field default; the RunPython
  step below makes that backfill explicit and idempotent (never guesses any
  historical platform rows). ``hotel`` stays NON-nullable everywhere.
- ``dedup_key`` (nullable) on Notification + a conditional unique constraint so
  a recipient holds at most one notification per key (idempotent re-emits).
Additive + safe: no row deleted, no recipient/actor/event_type changed, no
notification regenerated. Reverse simply drops the new fields/indexes/constraint.
"""
from django.conf import settings
from django.db import migrations, models


def backfill_scope_hotel(apps, schema_editor):
    """Explicitly stamp every legacy row as scope='hotel' (idempotent — the
    field default already does this; this guards against any NULL)."""
    ActivityEvent = apps.get_model("notifications", "ActivityEvent")
    Notification = apps.get_model("notifications", "Notification")
    ActivityEvent.objects.filter(scope__isnull=True).update(scope="hotel")
    ActivityEvent.objects.exclude(scope="platform").update(scope="hotel")
    Notification.objects.filter(scope__isnull=True).update(scope="hotel")
    Notification.objects.exclude(scope="platform").update(scope="hotel")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
        ('tenancy', '0003_hotel_status_changed_at_hotel_status_changed_by_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='activityevent',
            name='scope',
            field=models.CharField(choices=[('hotel', 'Hotel'), ('platform', 'Platform')], default='hotel', max_length=16),
        ),
        migrations.AddField(
            model_name='notification',
            name='dedup_key',
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name='notification',
            name='scope',
            field=models.CharField(choices=[('hotel', 'Hotel'), ('platform', 'Platform')], default='hotel', max_length=16),
        ),
        migrations.RunPython(backfill_scope_hotel, noop_reverse),
        migrations.AddIndex(
            model_name='activityevent',
            index=models.Index(fields=['scope', 'hotel', 'occurred_at'], name='activity_ev_scope_659424_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['recipient', 'scope', 'is_read'], name='hotel_notif_recipie_17fa92_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['recipient', 'scope', 'is_archived'], name='hotel_notif_recipie_f8e892_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['recipient', 'scope', 'created_at'], name='hotel_notif_recipie_f28156_idx'),
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.UniqueConstraint(condition=models.Q(('dedup_key__isnull', False)), fields=('recipient', 'dedup_key'), name='unique_notification_dedup_per_recipient'),
        ),
    ]
