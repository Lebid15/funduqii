# STAYS rate-integrity round — migrate pre-existing IN-HOUSE stays onto the new
# per-stay ``StayRatePeriod`` table, then drop the superseded ``Stay.nightly_rate``.
#
# HONESTY RULE (critical, do not weaken):
#   * The value the earlier 0002/0003 pair wrote into ``Stay.nightly_rate`` was
#     GUESSED from the LIVE ``RoomType.base_rate`` — it is NOT a proven historical
#     agreed rate. This migration therefore DISCARDS ``Stay.nightly_rate`` entirely
#     and NEVER turns it into a rate period.
#   * A period is created ONLY from a RELIABLE agreed source: the reservation
#     line's booking-time snapshot (``ReservationRoomLine.agreed_nightly_rate``,
#     captured together with ``agreed_rate_currency``).
#   * When there is NO reliable source, NO period is created. The stay then
#     surfaces as "needs attention": its due nights raise
#     ``MissingAgreedNightlyRate`` at posting rather than being billed at a
#     fabricated rate. We never invent a rate to fill the gap.
#
# Idempotent (get_or_create on (stay, start_date)); reverse re-adds the nullable
# column via ``RemoveField`` and keeps the migrated periods (the documented data
# loss on reverse is acceptable on this unpublished branch).
from django.db import migrations


def _hotel_default_currency(apps, db, hotel_id):
    """The hotel's default currency (HotelSettings) or ``USD`` — a currency is a
    non-money attribute, so coalescing an EMPTY captured currency to the hotel
    default is NOT fabricating a rate; the honesty rule (no guessed rate) holds."""
    HotelSettings = apps.get_model("tenancy", "HotelSettings")
    row = HotelSettings.objects.using(db).filter(hotel_id=hotel_id).first()
    default = (getattr(row, "default_currency", "") or "") if row is not None else ""
    return default or "USD"


def create_periods_from_agreed_rate(apps, schema_editor):
    Stay = apps.get_model("stays", "Stay")
    StayRatePeriod = apps.get_model("stays", "StayRatePeriod")
    db = schema_editor.connection.alias

    stays = (
        Stay.objects.using(db)
        .filter(status="in_house", reservation_line__isnull=False)
        .select_related("reservation_line")
    )
    for stay in stays.iterator():
        line = stay.reservation_line
        agreed = getattr(line, "agreed_nightly_rate", None)
        # RELIABLE source only: no booking-time snapshot => create NO period (an
        # honest gap, never the discarded ``Stay.nightly_rate`` guess).
        if agreed is None:
            continue
        # FIX G — a PRICED period must carry a non-empty currency (the new
        # ``priced_has_currency`` CheckConstraint). ``agreed_rate_currency`` is
        # normally captured with the rate, but a legacy priced line with an EMPTY
        # currency would abort the migration; coalesce it to the hotel default so
        # the backfill never raises IntegrityError (this coalesces a CURRENCY, not a
        # rate — the honesty rule is untouched).
        currency = getattr(line, "agreed_rate_currency", "") or ""
        if not currency:
            currency = _hotel_default_currency(apps, db, stay.hotel_id)
        StayRatePeriod.objects.using(db).get_or_create(
            stay=stay,
            start_date=stay.planned_check_in_date,
            defaults={
                "hotel_id": stay.hotel_id,
                "end_date": stay.planned_check_out_date,
                "nightly_rate": agreed,
                "currency": currency,
                "source": "booking",
            },
        )


def reverse_noop(apps, schema_editor):
    # Nothing to undo here: ``RemoveField``'s own reverse re-adds a nullable
    # ``Stay.nightly_rate`` column; the migrated rate periods are intentionally
    # kept (re-deriving the old column from them is out of scope, and the data
    # loss on reverse is documented/acceptable on this unpublished branch).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("stays", "0004_stayrateperiod"),
        # The backfill reads ``ReservationRoomLine.agreed_nightly_rate`` /
        # ``agreed_rate_currency``, so those columns must already exist.
        ("reservations", "0007_reservationroomline_agreed_rate"),
    ]

    operations = [
        # 1) migrate only RELIABLE agreed rates into periods (never the guess),
        migrations.RunPython(create_periods_from_agreed_rate, reverse_noop),
        # 2) then drop the superseded per-stay column.
        migrations.RemoveField(
            model_name="stay",
            name="nightly_rate",
        ),
    ]
