"""Add ``HotelSettings.default_phone_country`` (ISO-3166-1 alpha-2) + a safe
backfill.

The field seeds LOCAL guest-phone canonicalization. It is backfilled from the
existing free-text ``country`` ONLY when that value is already an unambiguous
2-letter alpha code (i.e. an ISO alpha-2 the hotel typed) — because a free-text
country NAME (any language) cannot be mapped to an alpha-2 code deterministically
or reliably. Every other row stays blank ("no default"); the hotel sets it from
the localization settings section. Nothing is guessed.

reverse: RemoveField (the backfill needs no inverse — the source ``country`` is
untouched).
"""
from django.db import migrations, models


def _backfill(apps, schema_editor):
    HotelSettings = apps.get_model("hotels", "HotelSettings")
    to_update = []
    for s in HotelSettings.objects.only("id", "country", "default_phone_country"):
        code = (s.country or "").strip()
        # Adopt ONLY an already-valid alpha-2 code; never map a country name.
        if len(code) == 2 and code.isalpha():
            s.default_phone_country = code.upper()
            to_update.append(s)
    if to_update:
        HotelSettings.objects.bulk_update(
            to_update, ["default_phone_country"], batch_size=500
        )


class Migration(migrations.Migration):

    dependencies = [
        ("hotels", "0008_settingsauditlog_settings_audit_scope_hotel_consistency"),
    ]

    operations = [
        migrations.AddField(
            model_name="hotelsettings",
            name="default_phone_country",
            field=models.CharField(blank=True, default="", max_length=2),
        ),
        migrations.RunPython(_backfill, migrations.RunPython.noop),
    ]
