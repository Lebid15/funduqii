"""Logic-level tests for the central guest-identity resolution service
(``apps.guests.identity`` — GUESTS central identity, W2).

These exercise the service API directly (no HTTP): reuse by each key, new
local/foreign creation, non-Latin-numeral folding, national-id/passport vs phone
conflicts with NO side effects, the ban fingerprint (including format variance
and the driving-license/'other' exclusion), reuse+reactivate with an audit event,
the ``allow_create=False`` contract, strict phone validation, and one
IntegrityError-refetch (race) path.

W4 owns the full concurrency + cross-section suite; the race test here is a
single logic-level check that also runs on SQLite.
"""
from __future__ import annotations

from unittest import mock

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.common.exceptions import GuestBlocked, GuestIdentityConflict
from apps.guests import identity as identity_mod
from apps.guests.identity import (
    classify_matches,
    ensure_identity_not_banned,
    resolve_or_create_guest,
    search_guests,
)
from apps.guests.models import DocumentType, Guest
from apps.hotels.models import HotelSettings
from apps.notifications.models import ActivityEvent
from apps.tenancy.models import Hotel, HotelStatus


def make_hotel(slug="hotel", *, phone_country="SA"):
    hotel = Hotel.objects.create(name="Hotel", slug=slug, status=HotelStatus.ACTIVE)
    HotelSettings.objects.create(hotel=hotel, default_phone_country=phone_country)
    return hotel


def make_user(email="clerk@x.com"):
    return User.objects.create_user(
        email=email, password="StrongPass!234", full_name="Clerk"
    )


class IdentityTestBase(TestCase):
    def setUp(self):
        self.hotel = make_hotel()
        self.user = make_user()

    def resolve(self, *, allow_create=True, **identity):
        return resolve_or_create_guest(
            self.hotel, identity=identity, user=self.user, allow_create=allow_create
        )

    def count(self):
        return Guest.objects.filter(hotel=self.hotel).count()


# ---------------------------------------------------------------------------
# Reuse by each key
# ---------------------------------------------------------------------------
class ReuseTests(IdentityTestBase):
    def test_reuse_by_national_id_ignores_punctuation(self):
        g1 = self.resolve(national_id="12345678", full_name="Alice")
        g2 = self.resolve(national_id="1234-5678", full_name="Alice again")
        self.assertEqual(g2.id, g1.id)
        self.assertEqual(self.count(), 1)

    def test_reuse_by_phone_ignores_format(self):
        g1 = self.resolve(phone="0555111222", full_name="Pat")
        # Same number entered in international form.
        g2 = self.resolve(phone="+966 555 111 222", full_name="Pat")
        self.assertEqual(g2.id, g1.id)
        self.assertEqual(self.count(), 1)
        self.assertEqual(g1.phone_normalized, "+966555111222")

    def test_reuse_by_passport_ignores_case_and_spacing(self):
        g1 = self.resolve(passport="AB-123456", full_name="Quinn")
        g2 = self.resolve(passport="ab 123456", full_name="Quinn")
        self.assertEqual(g2.id, g1.id)
        self.assertEqual(self.count(), 1)
        g1.refresh_from_db()
        self.assertEqual(g1.document_type, DocumentType.PASSPORT)


# ---------------------------------------------------------------------------
# New guests
# ---------------------------------------------------------------------------
class CreateTests(IdentityTestBase):
    def test_new_local_and_new_foreign_are_distinct(self):
        local = self.resolve(national_id="99887766", full_name="Local", nationality="SA")
        foreign = self.resolve(passport="P9999", full_name="Foreign", nationality="US")
        self.assertNotEqual(local.id, foreign.id)
        self.assertEqual(self.count(), 2)
        foreign.refresh_from_db()
        self.assertEqual(foreign.document_type, DocumentType.PASSPORT)
        self.assertEqual(foreign.document_number, "P9999")
        self.assertEqual(foreign.nationality, "US")

    def test_created_guest_records_creation_event(self):
        self.resolve(national_id="55554444", full_name="Audited")
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="guest.created"
            ).exists()
        )


# ---------------------------------------------------------------------------
# Non-Latin numerals (fold, never empty)
# ---------------------------------------------------------------------------
class NonLatinNumeralTests(IdentityTestBase):
    def test_arabic_indic_digits_fold_to_same_guest(self):
        g1 = self.resolve(
            national_id="١٢٣٤٥٦٧٨",  # ١٢٣٤٥٦٧٨
            phone="٠٥٥٥٩٩٩٩٩٩",  # ٠٥٥٥٩٩٩٩٩٩
            full_name="Noor",
        )
        self.assertEqual(g1.national_id_normalized, "12345678")
        self.assertNotEqual(g1.national_id_normalized, "")
        # Latin re-entry of the same identity reuses the row.
        g2 = self.resolve(national_id="12345678", full_name="Noor")
        self.assertEqual(g2.id, g1.id)
        self.assertEqual(self.count(), 1)


# ---------------------------------------------------------------------------
# Conflicts — refuse with NO side effects
# ---------------------------------------------------------------------------
class ConflictTests(IdentityTestBase):
    def test_national_id_vs_phone_conflict(self):
        a = self.resolve(national_id="A1111111", phone="0500000001", full_name="A")
        b = self.resolve(national_id="B2222222", phone="0500000002", full_name="B")
        self.assertEqual(self.count(), 2)
        with self.assertRaises(GuestIdentityConflict):
            # national id -> A, phone -> B (a different LIVE guest).
            self.resolve(national_id="A1111111", phone="0500000002", full_name="X")
        # No side effects: nothing created, both untouched/active.
        self.assertEqual(self.count(), 2)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertTrue(a.is_active and b.is_active)

    def test_passport_vs_phone_conflict(self):
        self.resolve(passport="PA1", phone="0500000011", full_name="A")
        self.resolve(passport="PB2", phone="0500000012", full_name="B")
        self.assertEqual(self.count(), 2)
        with self.assertRaises(GuestIdentityConflict):
            self.resolve(passport="PA1", phone="0500000012", full_name="X")
        self.assertEqual(self.count(), 2)

    def test_national_id_vs_passport_conflict(self):
        self.resolve(national_id="NID55555", full_name="A")
        self.resolve(passport="PASSPORTX", full_name="B")
        self.assertEqual(self.count(), 2)
        with self.assertRaises(GuestIdentityConflict):
            # national id -> A, passport -> B (two different strong ids).
            self.resolve(national_id="NID55555", passport="PASSPORTX", full_name="X")
        self.assertEqual(self.count(), 2)


# ---------------------------------------------------------------------------
# Ban fingerprint
# ---------------------------------------------------------------------------
class BanTests(IdentityTestBase):
    def _block(self, guest):
        Guest.objects.filter(pk=guest.pk).update(is_blocked=True)

    def test_ban_blocks_by_national_id(self):
        g = self.resolve(national_id="BAN11111", full_name="Ban")
        self._block(g)
        with self.assertRaises(GuestBlocked):
            self.resolve(national_id="ban 11111", full_name="Ban")
        with self.assertRaises(GuestBlocked):
            ensure_identity_not_banned(self.hotel, national_id="BAN-11111")

    def test_ban_blocks_by_passport(self):
        g = self.resolve(passport="BANPASS9", full_name="Ban")
        self._block(g)
        with self.assertRaises(GuestBlocked):
            ensure_identity_not_banned(self.hotel, passport="ban pass 9")

    def test_ban_blocks_by_phone_format_variance(self):
        g = self.resolve(phone="0555111222", full_name="Ban")
        self._block(g)
        with self.assertRaises(GuestBlocked):
            ensure_identity_not_banned(
                self.hotel, phone="+966 555 111 222", default_country="SA"
            )

    def test_ban_carries_no_reason(self):
        g = self.resolve(national_id="BANNORS1", full_name="Ban")
        self._block(g)
        try:
            ensure_identity_not_banned(self.hotel, national_id="BANNORS1")
            self.fail("expected GuestBlocked")
        except GuestBlocked as exc:
            # The neutral default detail only; no reason / identifier leaked.
            self.assertEqual(exc.default_code, "guest_blocked")
            self.assertNotIn("BANNORS1", str(exc.detail))

    def test_ban_ignores_driving_license(self):
        Guest.objects.create(
            hotel=self.hotel,
            full_name="DL holder",
            document_type=DocumentType.DRIVING_LICENSE,
            document_number="DL777",
            is_blocked=True,
        )
        # Same number typed as a passport must NOT be treated as banned.
        ensure_identity_not_banned(self.hotel, passport="DL777")  # no raise
        created = self.resolve(passport="DL777", full_name="Fresh")
        self.assertIsNotNone(created.pk)

    def test_ban_ignores_other_document(self):
        Guest.objects.create(
            hotel=self.hotel,
            full_name="Other holder",
            document_type=DocumentType.OTHER,
            document_number="OT888",
            is_blocked=True,
        )
        ensure_identity_not_banned(self.hotel, passport="OT888")  # no raise


# ---------------------------------------------------------------------------
# Reuse + reactivate an inactive match (audited)
# ---------------------------------------------------------------------------
class ReactivateTests(IdentityTestBase):
    def test_reuse_reactivates_inactive_and_audits(self):
        g = self.resolve(national_id="REACT111", phone="0555333444", full_name="React")
        Guest.objects.filter(pk=g.pk).update(is_active=False)

        g2 = self.resolve(national_id="REACT111", full_name="React")
        self.assertEqual(g2.id, g.id)
        g.refresh_from_db()
        self.assertTrue(g.is_active)
        self.assertEqual(self.count(), 1)
        self.assertTrue(
            ActivityEvent.objects.filter(
                hotel=self.hotel, event_type="guest.reactivated"
            ).exists()
        )

    def test_reactivation_never_bypasses_ban(self):
        g = self.resolve(national_id="REACTBAN", full_name="React")
        Guest.objects.filter(pk=g.pk).update(is_active=False, is_blocked=True)
        with self.assertRaises(GuestBlocked):
            self.resolve(national_id="REACTBAN", full_name="React")
        g.refresh_from_db()
        self.assertFalse(g.is_active)  # not resurrected


# ---------------------------------------------------------------------------
# allow_create=False (public path) contract
# ---------------------------------------------------------------------------
class PublicPathTests(IdentityTestBase):
    def test_no_match_returns_none_and_creates_nothing(self):
        result = self.resolve(
            national_id="NOEXIST1", full_name="Anon", allow_create=False
        )
        self.assertIsNone(result)
        self.assertEqual(self.count(), 0)

    def test_active_match_is_returned(self):
        g = self.resolve(national_id="PUB11111", full_name="Known")
        result = self.resolve(
            national_id="PUB11111", full_name="Known", allow_create=False
        )
        self.assertEqual(result.id, g.id)

    def test_inactive_match_is_not_reactivated_returns_none(self):
        g = self.resolve(national_id="PUB22222", full_name="Known")
        Guest.objects.filter(pk=g.pk).update(is_active=False)
        result = self.resolve(
            national_id="PUB22222", full_name="Known", allow_create=False
        )
        self.assertIsNone(result)
        g.refresh_from_db()
        self.assertFalse(g.is_active)  # public path never reactivates

    def test_public_path_still_enforces_ban(self):
        g = self.resolve(national_id="PUBBAN11", full_name="Known")
        Guest.objects.filter(pk=g.pk).update(is_blocked=True)
        with self.assertRaises(GuestBlocked):
            self.resolve(national_id="PUBBAN11", full_name="Known", allow_create=False)


# ---------------------------------------------------------------------------
# Strict phone validation (Decision 1)
# ---------------------------------------------------------------------------
class PhoneValidationTests(IdentityTestBase):
    def test_uninterpretable_phone_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self.resolve(phone="not-a-number", full_name="X")
        self.assertEqual(self.count(), 0)  # nothing stored

    def test_local_number_without_country_raises_validation_error(self):
        no_country = make_hotel(slug="nocountry", phone_country="")
        with self.assertRaises(ValidationError):
            resolve_or_create_guest(
                no_country,
                identity={"phone": "0555111222", "full_name": "X"},
                user=self.user,
            )
        self.assertEqual(Guest.objects.filter(hotel=no_country).count(), 0)

    def test_empty_phone_is_allowed(self):
        g = self.resolve(national_id="NOPHONE1", full_name="No phone", phone="")
        self.assertEqual(g.phone_normalized, "")


# ---------------------------------------------------------------------------
# search / classify units
# ---------------------------------------------------------------------------
class SearchClassifyTests(IdentityTestBase):
    def test_classify_none_when_no_match(self):
        result = search_guests(self.hotel, national_id="GHOST999")
        self.assertEqual(classify_matches(result).kind, identity_mod.NONE)

    def test_classify_single_by_national_id(self):
        g = self.resolve(national_id="SNGL1111", full_name="One")
        result = search_guests(self.hotel, national_id="SNGL1111")
        verdict = classify_matches(result)
        self.assertEqual(verdict.kind, identity_mod.SINGLE)
        self.assertEqual(verdict.guest.id, g.id)

    def test_search_includes_inactive_rows(self):
        g = self.resolve(phone="0555777888", full_name="Off")
        Guest.objects.filter(pk=g.pk).update(is_active=False)
        result = search_guests(self.hotel, phone="+966555777888")
        self.assertEqual([m.id for m in result.phone_matches], [g.id])
        self.assertFalse(result.phone_matches[0].is_active)


# ---------------------------------------------------------------------------
# Concurrency: create IntegrityError -> refetch the winner (never a 500)
# ---------------------------------------------------------------------------
class RaceTests(IdentityTestBase):
    def test_create_integrityerror_refetches_winner(self):
        """Simulate a losing racer: force the first classification to NONE so the
        service attempts a create that trips the national-id unique constraint,
        then verify it refetches and reuses the winning row instead of 500-ing."""
        winner = self.resolve(national_id="RACE1111", full_name="Winner")
        real_classify = identity_mod.classify_matches
        state = {"n": 0}

        def flaky(result):
            state["n"] += 1
            if state["n"] == 1:
                return identity_mod.MatchClassification(identity_mod.NONE)
            return real_classify(result)

        with mock.patch.object(identity_mod, "classify_matches", side_effect=flaky):
            resolved = self.resolve(national_id="RACE1111", full_name="Loser")

        self.assertEqual(resolved.id, winner.id)
        self.assertEqual(
            Guest.objects.filter(
                hotel=self.hotel, national_id_normalized="RACE1111"
            ).count(),
            1,
        )
