"""Tests for the LOST-REPORT cycle (the guest/customer "I lost X" flow) + the
safe manual match to a FOUND item.

Covers: creation (per-type required fields + LR numbering), tenant isolation,
permission reuse (``lost_found.*`` only), the status transitions, the
``confirm_match`` link (found item UNCHANGED), cross-hotel + non-matchable
refusals, the double-active-match belt AND the DB partial-unique, unmatch
(reason + only-from-matched + frees the item), the ATOMIC both-or-neither
handover, close-unfound / cancel reason gates, absence of DELETE endpoints, the
disclosure gates (reporter_phone / internal_notes) and the candidate picker.
"""
from __future__ import annotations

from django.db import IntegrityError, transaction
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APITestCase

from apps.common.exceptions import (
    ClaimProofRequired,
    ClaimantRequired,
    CrossTenantReference,
    FoundItemAlreadyMatched,
    FoundItemNotMatchable,
    InvalidOperationStatusTransition,
    LostReportReasonRequired,
)
from apps.operations.models import (
    LostFoundCategory,
    LostFoundItem,
    LostFoundStatus,
    LostReport,
    LostReportStatus,
    LostReportStatusLog,
)
from apps.operations.services import (
    cancel_lost_report,
    change_lost_report_status,
    close_unfound,
    confirm_match,
    create_lost_found_item,
    create_lost_report,
    hand_over_matched_report,
    unmatch,
    update_lost_report,
)
from apps.operations.serializers import LostReportListSerializer, LostReportSerializer
from apps.tenancy.models import MembershipType

from .tests import HDR, LF_PERMS, add_member, make_hotel, make_room, make_stay


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def make_found_item(hotel, *, category=LostFoundCategory.OTHER, status=LostFoundStatus.STORED):
    """Seed a FOUND item directly through the domain service."""
    return create_lost_found_item(
        hotel,
        title="Black wallet",
        category=category,
        status=status,
    )


class LostReportMixin:
    def create_lr(self, hotel=None, **body):
        hotel = hotel or self.hotel
        body.setdefault("reporter_name", "Guest Reporter")
        return self.client.post(
            reverse("operations:lost-report-list"), body, format="json", **HDR(hotel)
        )

    def lr_action(self, pk, action, body=None, hotel=None):
        return self.client.post(
            reverse(f"operations:lost-report-{action}", args=[pk]),
            body or {},
            format="json",
            **HDR(hotel or self.hotel),
        )

    def get_lr(self, pk, hotel=None):
        return self.client.get(
            reverse("operations:lost-report-detail", args=[pk]),
            **HDR(hotel or self.hotel),
        )


# --------------------------------------------------------------------------- #
# Creation + numbering + per-type required fields                               #
# --------------------------------------------------------------------------- #


class LostReportCreateTests(APITestCase, LostReportMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(self.hotel, "m@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)

    def test_create_mints_lr_number_and_opens(self):
        resp = self.create_lr(description="Lost a black wallet in the lobby")
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertTrue(body["report_number"].startswith("LR"))
        self.assertEqual(body["status"], LostReportStatus.OPEN)
        # Sequence increments per hotel.
        resp2 = self.create_lr()
        self.assertNotEqual(body["report_number"], resp2.json()["report_number"])

    def test_reporter_name_required_for_lost_report(self):
        # A LOST report's required field is the reporter (not a title). Blank →
        # the neutral 422 claimant_required.
        resp = self.create_lr(reporter_name="")
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertEqual(resp.json()["code"], "claimant_required")

    def test_found_item_requires_title_not_reporter(self):
        # The FOUND item's required field is the title (different per type).
        resp = self.client.post(
            reverse("operations:lost-found-list"),
            {"category": LostFoundCategory.OTHER},
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("title", resp.json().get("details", resp.json()))


# --------------------------------------------------------------------------- #
# Tenant isolation                                                              #
# --------------------------------------------------------------------------- #


class LostReportIsolationTests(APITestCase, LostReportMixin):
    def setUp(self):
        self.hotel = make_hotel(slug="a")
        self.other = make_hotel(slug="b")
        self.manager = add_member(self.hotel, "a@x.com", kind=MembershipType.MANAGER)
        self.client.force_authenticate(self.manager)
        self.report = create_lost_report(self.hotel, reporter_name="R")

    def test_other_hotel_cannot_see_report(self):
        # The manager is a member of self.hotel only; requesting under hotel B
        # (which they are not a member of) is refused before the object lookup.
        resp = self.get_lr(self.report.id, hotel=self.other)
        self.assertIn(resp.status_code, (403, 404))

    def test_list_scoped_to_hotel(self):
        resp = self.client.get(
            reverse("operations:lost-report-list"), **HDR(self.hotel)
        )
        self.assertEqual(resp.status_code, 200)
        ids = [r["id"] for r in resp.json()["results"]]
        self.assertIn(self.report.id, ids)
        # A report in another hotel never appears.
        other_report = create_lost_report(self.other, reporter_name="X")
        self.assertNotIn(other_report.id, ids)

    def test_cross_hotel_match_refused(self):
        # Service-level: a found item in another hotel can never be matched.
        foreign_item = make_found_item(self.other)
        with self.assertRaises(CrossTenantReference):
            confirm_match(self.report, foreign_item, user=self.manager)


# --------------------------------------------------------------------------- #
# Permissions (reuse of lost_found.* — no new codes)                            #
# --------------------------------------------------------------------------- #


class LostReportPermissionTests(APITestCase, LostReportMixin):
    def setUp(self):
        self.hotel = make_hotel()
        # A staff member with ONLY lost_found.view.
        self.viewer = add_member(
            self.hotel, "v@x.com", perms=["lost_found.view"]
        )
        # A staff member with view+create but NOT status_update.
        self.creator = add_member(
            self.hotel, "c@x.com", perms=["lost_found.view", "lost_found.create"]
        )
        self.report = create_lost_report(self.hotel, reporter_name="R")

    def test_view_only_cannot_create(self):
        self.client.force_authenticate(self.viewer)
        resp = self.create_lr()
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_create_needs_lost_found_create(self):
        self.client.force_authenticate(self.creator)
        resp = self.create_lr()
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_match_needs_status_update(self):
        # creator has create but not status_update → match refused.
        self.client.force_authenticate(self.creator)
        item = make_found_item(self.hotel)
        resp = self.lr_action(self.report.id, "match", {"found_item": item.id})
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_unmatch_and_handover_need_status_update(self):
        self.client.force_authenticate(self.creator)
        r = self.lr_action(self.report.id, "unmatch", {"reason": "x"})
        self.assertEqual(r.status_code, 403)
        r = self.lr_action(self.report.id, "handover", {"recipient_name": "y"})
        self.assertEqual(r.status_code, 403)

    def test_view_only_cannot_read_without_view(self):
        # A member with NO lost_found perms at all cannot even list.
        nobody = add_member(self.hotel, "n@x.com", perms=[])
        self.client.force_authenticate(nobody)
        resp = self.client.get(
            reverse("operations:lost-report-list"), **HDR(self.hotel)
        )
        self.assertEqual(resp.status_code, 403)


# --------------------------------------------------------------------------- #
# Status transitions + confirm_match + unmatch                                  #
# --------------------------------------------------------------------------- #


class LostReportTransitionTests(APITestCase, LostReportMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=LF_PERMS
        )
        self.client.force_authenticate(self.manager)
        self.report = create_lost_report(self.hotel, reporter_name="R")

    def test_open_to_searching_via_status(self):
        resp = self.lr_action(
            self.report.id, "status", {"status": LostReportStatus.SEARCHING}
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["status"], LostReportStatus.SEARCHING)

    def test_status_endpoint_refuses_non_forward_move(self):
        # open → matched is NOT allowed through the generic status endpoint
        # (matching has its own action).
        resp = self.lr_action(
            self.report.id, "status", {"status": LostReportStatus.MATCHED}
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "invalid_operation_status_transition")

    def test_confirm_match_sets_link_and_leaves_item_unchanged(self):
        item = make_found_item(self.hotel, status=LostFoundStatus.STORED)
        item_updated_before = item.updated_at
        resp = self.lr_action(self.report.id, "match", {"found_item": item.id})
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], LostReportStatus.MATCHED)
        self.assertEqual(body["matched_found_item"], item.id)
        # The FOUND item is UNCHANGED — no status change, no delete.
        item.refresh_from_db()
        self.assertEqual(item.status, LostFoundStatus.STORED)
        self.assertEqual(item.updated_at, item_updated_before)
        self.assertTrue(LostFoundItem.objects.filter(pk=item.pk).exists())

    def test_match_refuses_returned_disposed_closed_item(self):
        for st in (
            LostFoundStatus.RETURNED,
            LostFoundStatus.DISPOSED,
            LostFoundStatus.CLOSED,
        ):
            item = make_found_item(self.hotel)
            LostFoundItem.objects.filter(pk=item.pk).update(status=st)
            item.refresh_from_db()
            with self.assertRaises(FoundItemNotMatchable):
                confirm_match(self.report, item, user=self.manager)

    def test_match_allows_found_stored_claimed(self):
        for st in (
            LostFoundStatus.FOUND,
            LostFoundStatus.STORED,
            LostFoundStatus.CLAIMED,
        ):
            report = create_lost_report(self.hotel, reporter_name="R")
            item = make_found_item(self.hotel)
            LostFoundItem.objects.filter(pk=item.pk).update(status=st)
            item.refresh_from_db()
            confirm_match(report, item, user=self.manager)
            report.refresh_from_db()
            self.assertEqual(report.status, LostReportStatus.MATCHED)

    def test_double_active_match_refused_app_level(self):
        item = make_found_item(self.hotel)
        confirm_match(self.report, item, user=self.manager)
        other = create_lost_report(self.hotel, reporter_name="R2")
        with self.assertRaises(FoundItemAlreadyMatched):
            confirm_match(other, item, user=self.manager)

    def test_double_active_match_refused_db_partial_unique(self):
        # Bypass the application belt to prove the DB partial-unique itself
        # rejects a second ACTIVE match on the same found item.
        item = make_found_item(self.hotel)
        confirm_match(self.report, item, user=self.manager)
        other = create_lost_report(self.hotel, reporter_name="R2")
        other.matched_found_item = item
        other.status = LostReportStatus.MATCHED
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                other.save()

    def test_unmatch_requires_reason_and_only_from_matched(self):
        # Not matched yet → cannot unmatch.
        with self.assertRaises(InvalidOperationStatusTransition):
            unmatch(self.report, reason="x", user=self.manager)
        item = make_found_item(self.hotel)
        confirm_match(self.report, item, user=self.manager)
        # Missing reason → neutral typed error.
        with self.assertRaises(LostReportReasonRequired):
            unmatch(self.report, reason="", user=self.manager)

    def test_unmatch_frees_item_for_rematch(self):
        item = make_found_item(self.hotel)
        confirm_match(self.report, item, user=self.manager)
        unmatch(self.report, reason="wrong item", user=self.manager)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, LostReportStatus.SEARCHING)
        self.assertIsNone(self.report.matched_found_item_id)
        # The freed item can be matched by another report.
        other = create_lost_report(self.hotel, reporter_name="R2")
        confirm_match(other, item, user=self.manager)
        other.refresh_from_db()
        self.assertEqual(other.matched_found_item_id, item.id)

    def test_matched_report_cannot_be_directly_cancelled_or_closed(self):
        item = make_found_item(self.hotel)
        confirm_match(self.report, item, user=self.manager)
        with self.assertRaises(InvalidOperationStatusTransition):
            close_unfound(self.report, reason="x", user=self.manager)
        with self.assertRaises(InvalidOperationStatusTransition):
            cancel_lost_report(self.report, reason="x", user=self.manager)


# --------------------------------------------------------------------------- #
# Atomic handover (both-or-neither)                                             #
# --------------------------------------------------------------------------- #


class LostReportHandoverTests(APITestCase, LostReportMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=LF_PERMS
        )
        self.report = create_lost_report(self.hotel, reporter_name="R")

    def test_handover_success_flips_both(self):
        item = make_found_item(self.hotel, category=LostFoundCategory.OTHER)
        confirm_match(self.report, item, user=self.manager)
        report = hand_over_matched_report(
            self.report, user=self.manager, recipient_name="Owner Guest"
        )
        report.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(report.status, LostReportStatus.RETURNED)
        self.assertIsNotNone(report.returned_at)
        self.assertEqual(item.status, LostFoundStatus.RETURNED)

    def test_handover_missing_proof_sensitive_rolls_back_both(self):
        # A MONEY item is sensitive (WP7): handover without proof must fail and
        # leave BOTH records untouched.
        item = make_found_item(self.hotel, category=LostFoundCategory.MONEY)
        confirm_match(self.report, item, user=self.manager)
        with self.assertRaises(ClaimProofRequired):
            hand_over_matched_report(
                self.report, user=self.manager, recipient_name="Owner"
            )
        self.report.refresh_from_db()
        item.refresh_from_db()
        # Both-or-neither: nothing changed on either record.
        self.assertEqual(self.report.status, LostReportStatus.MATCHED)
        self.assertIsNone(self.report.returned_at)
        self.assertEqual(item.status, LostFoundStatus.STORED)
        self.assertIsNone(item.returned_at)

    def test_handover_sensitive_with_full_proof_succeeds(self):
        item = make_found_item(self.hotel, category=LostFoundCategory.JEWELRY)
        confirm_match(self.report, item, user=self.manager)
        report = hand_over_matched_report(
            self.report,
            user=self.manager,
            recipient_name="Owner Guest",
            recipient_phone="0555",
            claim_proof_type="receipt_reference",
            claim_proof_reference="RCPT-1",
        )
        report.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(report.status, LostReportStatus.RETURNED)
        self.assertEqual(item.status, LostFoundStatus.RETURNED)

    def test_handover_requires_matched(self):
        # Not matched → cannot hand over.
        with self.assertRaises(InvalidOperationStatusTransition):
            hand_over_matched_report(
                self.report, user=self.manager, recipient_name="x"
            )


# --------------------------------------------------------------------------- #
# Close-unfound / cancel reason gates + no delete                               #
# --------------------------------------------------------------------------- #


class LostReportTerminalTests(APITestCase, LostReportMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=LF_PERMS
        )
        self.client.force_authenticate(self.manager)
        self.report = create_lost_report(self.hotel, reporter_name="R")

    def test_close_unfound_requires_reason(self):
        resp = self.lr_action(self.report.id, "close-unfound", {"reason": ""})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "lost_report_reason_required")
        self.assertEqual(resp.json()["details"]["reason"], "close_unfound")

    def test_close_unfound_success(self):
        resp = self.lr_action(
            self.report.id, "close-unfound", {"reason": "searched everywhere"}
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["status"], LostReportStatus.CLOSED_UNFOUND)

    def test_cancel_requires_reason(self):
        resp = self.lr_action(self.report.id, "cancel", {"reason": ""})
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "cancellation_reason_required")

    def test_cancel_success(self):
        resp = self.lr_action(self.report.id, "cancel", {"reason": "duplicate"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["status"], LostReportStatus.CANCELLED)

    def test_no_delete_endpoint(self):
        resp = self.client.delete(
            reverse("operations:lost-report-detail", args=[self.report.id]),
            **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 405)

    def test_no_delete_list_endpoint(self):
        resp = self.client.delete(
            reverse("operations:lost-report-list"), **HDR(self.hotel)
        )
        self.assertEqual(resp.status_code, 405)


# --------------------------------------------------------------------------- #
# Disclosure gates (reporter_phone / internal_notes)                            #
# --------------------------------------------------------------------------- #


class LostReportDisclosureTests(APITestCase, LostReportMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=LF_PERMS
        )
        self.report = create_lost_report(
            self.hotel,
            reporter_name="R",
            reporter_phone="0555000",
            internal_notes="secret note",
        )

    def test_list_never_exposes_phone_or_internal_notes(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get(
            reverse("operations:lost-report-list"), **HDR(self.hotel)
        )
        self.assertEqual(resp.status_code, 200)
        row = resp.json()["results"][0]
        self.assertNotIn("reporter_phone", row)
        self.assertNotIn("internal_notes", row)
        self.assertEqual(row["record_type"], "lost_report")

    def test_detail_shows_gated_fields_to_privileged_caller(self):
        self.client.force_authenticate(self.manager)
        resp = self.get_lr(self.report.id)
        body = resp.json()
        self.assertEqual(body["reporter_phone"], "0555000")
        self.assertEqual(body["internal_notes"], "secret note")

    def test_detail_hides_phone_from_caller_without_status_update(self):
        # A caller with view+update but NOT status_update sees internal_notes
        # (update satisfies it) but NOT the reporter_phone.
        member = add_member(
            self.hotel, "u@x.com", perms=["lost_found.view", "lost_found.update"]
        )
        self.client.force_authenticate(member)
        resp = self.get_lr(self.report.id)
        body = resp.json()
        self.assertNotIn("reporter_phone", body)
        self.assertIn("internal_notes", body)

    def test_detail_hides_both_from_view_only_caller(self):
        member = add_member(self.hotel, "vo@x.com", perms=["lost_found.view"])
        self.client.force_authenticate(member)
        resp = self.get_lr(self.report.id)
        body = resp.json()
        self.assertNotIn("reporter_phone", body)
        self.assertNotIn("internal_notes", body)

    def test_serializer_fail_closed_without_request_context(self):
        # No request context at all → both sensitive fields dropped (fail-closed).
        data = LostReportSerializer(self.report).data
        self.assertNotIn("reporter_phone", data)
        self.assertNotIn("internal_notes", data)

    def test_list_serializer_excludes_sensitive_fields_by_construction(self):
        # The list serializer NEVER declares the sensitive fields at all.
        data = LostReportListSerializer(self.report).data
        self.assertNotIn("reporter_phone", data)
        self.assertNotIn("internal_notes", data)


# --------------------------------------------------------------------------- #
# Candidate picker                                                              #
# --------------------------------------------------------------------------- #


class LostReportCandidatesTests(APITestCase, LostReportMixin):
    def setUp(self):
        self.hotel = make_hotel(slug="a")
        self.other = make_hotel(slug="b")
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=LF_PERMS
        )
        self.client.force_authenticate(self.manager)
        self.report = create_lost_report(self.hotel, reporter_name="R")

    def _candidates(self, **params):
        return self.client.get(
            reverse("operations:lost-report-candidates", args=[self.report.id]),
            params,
            **HDR(self.hotel),
        )

    def test_candidates_are_hotel_scoped(self):
        mine = make_found_item(self.hotel)
        foreign = make_found_item(self.other)
        resp = self._candidates()
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [r["id"] for r in resp.json()]
        self.assertIn(mine.id, ids)
        self.assertNotIn(foreign.id, ids)

    def test_candidates_exclude_already_matched_and_terminal(self):
        matchable = make_found_item(self.hotel, status=LostFoundStatus.STORED)
        already = make_found_item(self.hotel, status=LostFoundStatus.STORED)
        other_report = create_lost_report(self.hotel, reporter_name="R2")
        confirm_match(other_report, already, user=self.manager)
        returned = make_found_item(self.hotel)
        LostFoundItem.objects.filter(pk=returned.pk).update(
            status=LostFoundStatus.RETURNED
        )
        resp = self._candidates()
        ids = [r["id"] for r in resp.json()]
        self.assertIn(matchable.id, ids)
        self.assertNotIn(already.id, ids)  # actively matched
        self.assertNotIn(returned.id, ids)  # not matchable

    def test_candidates_never_leak_phone_or_proof(self):
        item = make_found_item(self.hotel, category=LostFoundCategory.MONEY)
        # Give the item a claimant phone + proof so we can prove they never leak.
        LostFoundItem.objects.filter(pk=item.pk).update(
            claimed_by_phone="0555", claim_proof_reference="RCPT"
        )
        resp = self._candidates()
        rows = resp.json()
        self.assertTrue(rows)
        for row in rows:
            self.assertNotIn("claimed_by_phone", row)
            self.assertNotIn("claim_proof_reference", row)

    def test_candidates_search_filters(self):
        make_found_item(self.hotel)  # "Black wallet"
        needle = create_lost_found_item(
            self.hotel, title="Silver ring", category=LostFoundCategory.JEWELRY
        )
        resp = self._candidates(search="Silver")
        ids = [r["id"] for r in resp.json()]
        self.assertIn(needle.id, ids)


# --------------------------------------------------------------------------- #
# StatCards                                                                     #
# --------------------------------------------------------------------------- #


class LostReportStatCardTests(APITestCase, LostReportMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=LF_PERMS
        )
        self.client.force_authenticate(self.manager)

    def test_overview_counts_lost_report_cards(self):
        # 1 open, 1 searching  → open_lost_reports == 2
        open_r = create_lost_report(self.hotel, reporter_name="A")
        searching_r = create_lost_report(self.hotel, reporter_name="B")
        change_lost_report_status(
            searching_r, new_status=LostReportStatus.SEARCHING, user=self.manager
        )
        # 1 matched → confirmed_matches == 1 ; the matched item is stored.
        matched_r = create_lost_report(self.hotel, reporter_name="C")
        item = make_found_item(self.hotel, status=LostFoundStatus.STORED)
        confirm_match(matched_r, item, user=self.manager)
        # 1 returned → returned_reports == 1
        returned_r = create_lost_report(self.hotel, reporter_name="D")
        item2 = make_found_item(self.hotel, status=LostFoundStatus.STORED)
        confirm_match(returned_r, item2, user=self.manager)
        hand_over_matched_report(
            returned_r, user=self.manager, recipient_name="Owner"
        )

        resp = self.client.get(reverse("operations:overview"), **HDR(self.hotel))
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["open_lost_reports"], 2)  # open + searching
        self.assertEqual(body["confirmed_matches"], 1)
        self.assertEqual(body["returned_reports"], 1)
        # stored_found_items: item (still matched but STORED) is counted; item2
        # became RETURNED by the handover → not counted.
        self.assertEqual(body["stored_found_items"], 1)
        # matched item never has its status mutated by the match itself.
        item.refresh_from_db()
        self.assertEqual(item.status, LostFoundStatus.STORED)


# --------------------------------------------------------------------------- #
# Update guard                                                                  #
# --------------------------------------------------------------------------- #


class LostReportUpdateTests(APITestCase, LostReportMixin):
    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=LF_PERMS
        )

    def test_update_blocked_once_matched(self):
        report = create_lost_report(self.hotel, reporter_name="R")
        item = make_found_item(self.hotel)
        report = confirm_match(report, item, user=self.manager)
        from apps.common.exceptions import OperationNotEditable

        with self.assertRaises(OperationNotEditable):
            update_lost_report(report, user=self.manager, description="edited")


# --------------------------------------------------------------------------- #
# Actively-matched reverse guard (FLAG-1)                                        #
# --------------------------------------------------------------------------- #


class ActivelyMatchedItemGuardTests(APITestCase, LostReportMixin):
    """A found item ACTIVELY matched by a lost report (report status ==
    ``matched``) may NOT be disposed / returned / claimed through the standalone
    lost-&-found actions — that would dangle the report as ``matched`` to a gone
    item and risk a handover to the WRONG party. It must be released first via
    the report's ``unmatch`` (documented reason) or handed over atomically. This
    hardens the SYMMETRIC reverse of ``confirm_match``'s forward guard."""

    def setUp(self):
        self.hotel = make_hotel()
        self.manager = add_member(
            self.hotel, "m@x.com", kind=MembershipType.MANAGER, perms=LF_PERMS
        )
        self.client.force_authenticate(self.manager)
        self.report = create_lost_report(self.hotel, reporter_name="R")
        # A NORMAL-category (OTHER) matched item → no proof needed on handover.
        self.item = make_found_item(self.hotel, status=LostFoundStatus.STORED)
        confirm_match(self.report, self.item, user=self.manager)

    def _lf_action(self, action, body=None):
        return self.client.post(
            reverse(f"operations:lost-found-{action}", args=[self.item.id]),
            body or {},
            format="json",
            **HDR(self.hotel),
        )

    def _assert_still_matched_and_stored(self):
        self.item.refresh_from_db()
        self.report.refresh_from_db()
        # Item unchanged (still holdable) and the report still actively holds it.
        self.assertEqual(self.item.status, LostFoundStatus.STORED)
        self.assertTrue(LostFoundItem.objects.filter(pk=self.item.pk).exists())
        self.assertEqual(self.report.status, LostReportStatus.MATCHED)
        self.assertEqual(self.report.matched_found_item_id, self.item.id)

    def test_dispose_refused_for_actively_matched_item(self):
        resp = self._lf_action("dispose", {"reason": "damaged"})
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "found_item_actively_matched")
        self._assert_still_matched_and_stored()

    def test_return_refused_for_actively_matched_item(self):
        resp = self._lf_action("return", {"claimed_by_name": "Someone Else"})
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "found_item_actively_matched")
        self._assert_still_matched_and_stored()

    def test_claim_refused_for_actively_matched_item(self):
        resp = self._lf_action("claim", {"claimed_by_name": "Someone Else"})
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "found_item_actively_matched")
        self._assert_still_matched_and_stored()

    def test_handover_still_returns_matched_item(self):
        # The atomic handover of the very item this report matches SUCCEEDS — the
        # non-forgeable ``_via_matched_handover`` bypass lets the legitimate
        # return through the same guard that blocks the standalone action.
        report = hand_over_matched_report(
            self.report, user=self.manager, recipient_name="Owner Guest"
        )
        report.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(report.status, LostReportStatus.RETURNED)
        self.assertEqual(self.item.status, LostFoundStatus.RETURNED)

    def test_actions_succeed_after_unmatch(self):
        # After a documented unmatch the reverse guard is released, so each of the
        # three standalone actions succeeds. A fresh matched-then-unmatched item
        # per action (each terminal is one-way).
        def fresh_unmatched_item():
            report = create_lost_report(self.hotel, reporter_name="R2")
            item = make_found_item(self.hotel, status=LostFoundStatus.STORED)
            confirm_match(report, item, user=self.manager)
            unmatch(report, reason="wrong item", user=self.manager)
            return item

        claim_item = fresh_unmatched_item()
        resp = self.client.post(
            reverse("operations:lost-found-claim", args=[claim_item.id]),
            {"claimed_by_name": "Owner"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        claim_item.refresh_from_db()
        self.assertEqual(claim_item.status, LostFoundStatus.CLAIMED)

        return_item = fresh_unmatched_item()
        resp = self.client.post(
            reverse("operations:lost-found-return", args=[return_item.id]),
            {"claimed_by_name": "Owner"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        return_item.refresh_from_db()
        self.assertEqual(return_item.status, LostFoundStatus.RETURNED)

        dispose_item = fresh_unmatched_item()
        resp = self.client.post(
            reverse("operations:lost-found-dispose", args=[dispose_item.id]),
            {"reason": "damaged"}, format="json", **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        dispose_item.refresh_from_db()
        self.assertEqual(dispose_item.status, LostFoundStatus.DISPOSED)

    def test_client_supplied_via_matched_handover_is_ignored(self):
        # The internal bypass flag cannot be forged through the serializer: it is
        # NOT a serializer field, so a body that also tries to send it (either
        # spelling) STILL hits the guard — mirrors the cycle_source non-forgeability.
        resp = self.client.post(
            reverse("operations:lost-found-return", args=[self.item.id]),
            {
                "claimed_by_name": "Someone Else",
                "_via_matched_handover": True,
                "via_matched_handover": True,
            },
            format="json",
            **HDR(self.hotel),
        )
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "found_item_actively_matched")
        self._assert_still_matched_and_stored()

    def test_via_matched_handover_is_not_a_serializer_field(self):
        from apps.operations.serializers import LostFoundClaimSerializer

        self.assertNotIn("_via_matched_handover", LostFoundClaimSerializer().fields)
        self.assertNotIn("via_matched_handover", LostFoundClaimSerializer().fields)

    def test_handover_status_log_records_recipient_name(self):
        # The report's own audit trail is self-sufficient: it records the NON-
        # SENSITIVE recipient name — never the phone/proof.
        hand_over_matched_report(
            self.report,
            user=self.manager,
            recipient_name="Owner Guest",
            recipient_phone="0555999888",
        )
        log = (
            LostReportStatusLog.objects.filter(report=self.report)
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(log)
        self.assertIn("Owner Guest", log.note)
        # Privacy: the phone is NEVER written to the status log.
        self.assertNotIn("0555999888", log.note)
