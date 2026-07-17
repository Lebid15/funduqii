"""Round 5 §9 foundation — typed settings groups, per-section save, central audit."""
from __future__ import annotations

import threading
from unittest.mock import patch

from django.db import IntegrityError, connection, connections, transaction
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import AccountType, User
from apps.hotels.models import HotelSettings, SettingsAuditLog, SettingsAuditScope
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

from .tests import add_member, make_hotel

STRONG = "StrongPass!234"
_PG_SKIP = (
    "Real two-connection settings concurrency is only meaningful on PostgreSQL "
    "(row MVCC + column-scoped update_fields). SQLite serialises writers."
)


class HotelSettingsSectionTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager, _ = add_member(
            self.hotel, "mgr@x.com", kind=MembershipType.MANAGER
        )
        self.headers = {"HTTP_X_HOTEL_ID": str(self.hotel.id)}
        self.client.force_authenticate(self.manager)

    def _section_url(self, section):
        return reverse("hotel:settings-section", args=[section])

    def test_section_save_updates_only_its_fields_and_audits(self):
        res = self.client.patch(
            self._section_url("identity"),
            {"display_name": "Sea View", "facility_type": "resort"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 200, res.content)
        s = HotelSettings.objects.get(hotel=self.hotel)
        self.assertEqual(s.display_name, "Sea View")
        self.assertEqual(s.facility_type, "resort")
        log = SettingsAuditLog.objects.get(hotel=self.hotel, section="identity")
        self.assertEqual(log.scope, SettingsAuditScope.HOTEL)
        self.assertEqual(log.actor_id, self.manager.id)
        self.assertIn("display_name", log.changes)
        self.assertEqual(log.changes["facility_type"]["new"], "resort")

    def test_section_save_ignores_foreign_fields(self):
        # A field from another section is ignored, not applied.
        res = self.client.patch(
            self._section_url("identity"),
            {"display_name": "X", "default_currency": "EUR"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 200)
        s = HotelSettings.objects.get(hotel=self.hotel)
        self.assertEqual(s.display_name, "X")
        self.assertEqual(s.default_currency, "USD")  # unchanged (other section)

    def test_every_writable_settings_field_is_grouped(self):
        """§9.17/§9.19 invariant (drift guard): a field writable through the
        settings API MUST belong to a settings group — otherwise it would be
        saved without appearing in the audit diff and without a UI home. This
        test fails the moment someone adds a writable field to HotelSettings
        without registering it in HOTEL_SETTINGS_GROUPS."""
        from apps.hotels.serializers import HotelSettingsSerializer
        from apps.hotels.settings_services import GROUPED_FIELDS

        writable = {
            name
            for name, field in HotelSettingsSerializer().fields.items()
            if not field.read_only
        }
        self.assertEqual(writable - set(GROUPED_FIELDS), set())

    def test_section_save_rejects_non_object_body(self):
        res = self.client.patch(
            self._section_url("identity"), [1, 2], format="json", **self.headers
        )
        self.assertEqual(res.status_code, 400)

    def test_unknown_section_404(self):
        res = self.client.patch(
            self._section_url("does-not-exist"), {"x": 1}, format="json", **self.headers
        )
        self.assertEqual(res.status_code, 404)

    def test_noop_save_records_no_audit(self):
        # First establish the value.
        self.client.patch(
            self._section_url("identity"),
            {"display_name": "Same"},
            format="json",
            **self.headers,
        )
        SettingsAuditLog.objects.all().delete()
        # Saving the same value again changes nothing -> no audit row.
        self.client.patch(
            self._section_url("identity"),
            {"display_name": "Same"},
            format="json",
            **self.headers,
        )
        self.assertEqual(SettingsAuditLog.objects.count(), 0)

    def test_staff_without_update_cannot_section_save(self):
        staff = add_member(self.hotel, "staff@x.com", perms=("settings.view",))[0]
        self.client.force_authenticate(staff)
        res = self.client.patch(
            self._section_url("identity"),
            {"display_name": "Nope"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 403)

    def test_suspended_hotel_cannot_section_save(self):
        self.hotel.status = HotelStatus.SUSPENDED
        self.hotel.save(update_fields=["status"])
        res = self.client.patch(
            self._section_url("identity"),
            {"display_name": "Nope"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data["code"], "hotel_suspended")

    def test_business_date_is_not_writable_via_settings(self):
        """business_date is the hotel's operational anchor: it advances ONLY via
        the daily close, never by a settings edit. A settings PATCH must not be
        able to move it (which would corrupt every daily-derived figure)."""
        import datetime

        s, _ = HotelSettings.objects.get_or_create(hotel=self.hotel)
        s.business_date = datetime.date(2026, 1, 10)
        s.save(update_fields=["business_date"])
        res = self.client.patch(
            reverse("hotel:settings"),
            {"business_date": "2030-01-01"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 200)
        s.refresh_from_db()
        self.assertEqual(s.business_date, datetime.date(2026, 1, 10))  # unchanged

    def test_full_patch_still_audits(self):
        res = self.client.patch(
            reverse("hotel:settings"),
            {"legal_name": "Legal LLC"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(
            SettingsAuditLog.objects.filter(
                hotel=self.hotel, section="all"
            ).exists()
        )


class HotelSettingsAuditReadTests(APITestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager, _ = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER
        )
        self.headers = {"HTTP_X_HOTEL_ID": str(self.hotel.id)}

    def test_audit_read_is_tenant_scoped(self):
        other = make_hotel(slug="other")
        SettingsAuditLog.objects.create(
            scope=SettingsAuditScope.HOTEL, hotel=self.hotel, section="identity",
            changes={"display_name": {"old": "", "new": "A"}},
        )
        SettingsAuditLog.objects.create(
            scope=SettingsAuditScope.HOTEL, hotel=other, section="identity",
            changes={"display_name": {"old": "", "new": "B"}},
        )
        self.client.force_authenticate(self.manager)
        res = self.client.get(reverse("hotel:settings-audit"), **self.headers)
        self.assertEqual(res.status_code, 200)
        rows = res.data["results"] if isinstance(res.data, dict) else res.data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["section"], "identity")

    def test_platform_audit_scope_not_visible_to_hotel(self):
        SettingsAuditLog.objects.create(
            scope=SettingsAuditScope.PLATFORM, hotel=None, section="platform",
            changes={"platform_name": {"old": "A", "new": "B"}},
        )
        self.client.force_authenticate(self.manager)
        res = self.client.get(reverse("hotel:settings-audit"), **self.headers)
        rows = res.data["results"] if isinstance(res.data, dict) else res.data
        self.assertEqual(len(rows), 0)  # hotel filter excludes platform rows


class PlatformSettingsAuditTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@platform.local", password=STRONG, full_name="Owner",
            account_type=AccountType.PLATFORM_OWNER,
        )

    def test_platform_settings_patch_audits(self):
        self.client.force_authenticate(self.owner)
        res = self.client.patch(
            reverse("platform:settings"),
            {"platform_name": "Funduqii Pro"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        log = SettingsAuditLog.objects.get(scope=SettingsAuditScope.PLATFORM, section="platform")
        self.assertIsNone(log.hotel_id)
        self.assertEqual(log.changes["platform_name"]["new"], "Funduqii Pro")

    def test_hotel_user_cannot_read_platform_audit(self):
        hotel = make_hotel()
        manager = add_member(hotel, "m2@x.com", kind=MembershipType.MANAGER)[0]
        self.client.force_authenticate(manager)
        res = self.client.get(reverse("platform:settings-audit"))
        self.assertEqual(res.status_code, 403)


class SettingsAtomicityTests(APITestCase):
    """§9.17 audit-or-nothing: a settings write and its audit row commit together,
    and the audit table cannot hold an orphan (scope↔hotel consistency)."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager, _ = add_member(
            self.hotel, "mgr@x.com", kind=MembershipType.MANAGER
        )
        self.headers = {"HTTP_X_HOTEL_ID": str(self.hotel.id)}
        self.client.force_authenticate(self.manager)

    def test_audit_failure_rolls_back_the_settings_change(self):
        """If recording the audit row fails, the whole PATCH rolls back: the
        settings value must NOT persist without its audit trail."""
        HotelSettings.objects.get_or_create(hotel=self.hotel)
        HotelSettings.objects.filter(hotel=self.hotel).update(display_name="Before")
        with patch(
            "apps.hotels.views.record_settings_change",
            side_effect=RuntimeError("audit sink down"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.patch(
                    reverse("hotel:settings-section", args=["identity"]),
                    {"display_name": "After"},
                    format="json",
                    **self.headers,
                )
        s = HotelSettings.objects.get(hotel=self.hotel)
        self.assertEqual(s.display_name, "Before")  # rolled back
        self.assertFalse(
            SettingsAuditLog.objects.filter(hotel=self.hotel).exists()
        )

    def test_orphan_audit_row_is_rejected_by_check_constraint(self):
        """migration 0008: a HOTEL-scoped row with no hotel (or a PLATFORM row
        with a hotel) is impossible — the DB CHECK constraint rejects it."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SettingsAuditLog.objects.create(
                    scope=SettingsAuditScope.HOTEL, hotel=None, section="identity",
                    changes={"x": {"old": "", "new": "y"}},
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SettingsAuditLog.objects.create(
                    scope=SettingsAuditScope.PLATFORM, hotel=self.hotel,
                    section="platform", changes={"x": {"old": "", "new": "y"}},
                )


def _section_save_worker(hotel_id, user_id, section, data, barrier, errors):
    """Run one section save on a fresh connection, loading the settings row
    BEFORE the barrier so both workers hold a stale copy when they write — the
    exact interleaving that a full-row save would lose."""
    from apps.accounts.models import User as _User
    from apps.hotels.settings_services import group_fields
    from apps.hotels.views import _apply_settings_update
    from apps.tenancy.models import Hotel as _Hotel

    try:
        hotel = _Hotel.objects.get(pk=hotel_id)
        user = _User.objects.get(pk=user_id)
        obj = HotelSettings.objects.get(hotel=hotel)
        req = type("Req", (), {"hotel": hotel, "user": user})()
        barrier.wait(timeout=15)  # both loaded stale -> now race the writes
        _apply_settings_update(req, obj, data, section, group_fields(section))
    except Exception as exc:  # noqa: BLE001 - surfaced to the asserting thread
        errors.append(repr(exc))
    finally:
        connection.close()


class SettingsConcurrencyTests(TransactionTestCase):
    """Owner PG gate: two concurrent saves on the shared HotelSettings row must
    not lose each other's columns. Column-scoped update_fields makes disjoint
    sections independent and same-section a clean, audited last-writer-wins."""

    reset_sequences = True

    def setUp(self):
        self.hotel = make_hotel()
        self.manager, _ = add_member(
            self.hotel, "mgr@x.com", kind=MembershipType.MANAGER
        )
        HotelSettings.objects.get_or_create(hotel=self.hotel)

    def _run_pair(self, spec_a, spec_b):
        barrier = threading.Barrier(2)
        errors: list[str] = []
        threads = [
            threading.Thread(
                target=_section_save_worker,
                args=(self.hotel.id, self.manager.id, sec, data, barrier, errors),
            )
            for sec, data in (spec_a, spec_b)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        connections.close_all()
        self.assertEqual(errors, [], f"worker error(s): {errors}")

    def test_concurrent_different_sections_both_saved(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)
        self._run_pair(
            ("identity", {"display_name": "T1-identity"}),
            ("contact", {"phone": "+90 555 000 1111"}),
        )
        s = HotelSettings.objects.get(hotel=self.hotel)
        self.assertEqual(s.display_name, "T1-identity")  # neither
        self.assertEqual(s.phone, "+90 555 000 1111")     # clobbered the other
        self.assertEqual(
            SettingsAuditLog.objects.filter(hotel=self.hotel).count(), 2
        )

    def test_concurrent_same_section_is_clean_last_writer_wins(self):
        if connection.vendor != "postgresql":
            self.skipTest(_PG_SKIP)
        self._run_pair(
            ("identity", {"display_name": "Writer-A"}),
            ("identity", {"display_name": "Writer-B"}),
        )
        s = HotelSettings.objects.get(hotel=self.hotel)
        # A clean overwrite to exactly one of the two values (no corruption /
        # no mixed row) and BOTH writes are audited (the loss is not silent).
        self.assertIn(s.display_name, {"Writer-A", "Writer-B"})
        self.assertEqual(
            SettingsAuditLog.objects.filter(
                hotel=self.hotel, section="identity"
            ).count(),
            2,
        )
