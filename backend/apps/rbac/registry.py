"""Canonical registry of hotel permissions in ``section.operation`` form.

This is the single source of truth for which permission codes exist. Granting
a code that is not in this registry is rejected. Sections are added as their
phases arrive; the codes below mirror the blueprint's reference list.
"""
from __future__ import annotations

PERMISSIONS_BY_SECTION: dict[str, list[str]] = {
    "dashboard": ["view"],
    "reservations": [
        "view",
        "create",
        "update",
        "confirm",
        "cancel",
        "assign_room",
        "check_in",
        "check_out",
        # STAYS-ARRIVALS-DEPARTURES §29 — mark an expected arrival as a no-show
        # (a reservation whose guest never checked in). Deliberately separate
        # from cancel: a no-show follows the arrival/grace policy, not a manual
        # cancellation, and frees availability per policy.
        "mark_no_show",
    ],
    "availability": ["view"],
    "rooms": ["view", "create", "update", "delete", "status_update"],
    # Guests final closure: VIP/block/sensitive-data are deliberately separate
    # codes — never bundled under guests.update.
    "guests": [
        "view",
        "create",
        "update",
        "delete",
        "mark_vip",
        "block",
        "view_sensitive_data",
    ],
    # Front-desk operations (Phase 7). The reservations.check_in/check_out codes
    # above are vestigial blueprint entries and are NOT used; front-desk uses
    # these explicit stays.* codes instead. extend/shorten/move_room arrived
    # with the front-desk final closure round — deliberately separate codes,
    # NOT bundled under stays.update.
    "stays": [
        "view",
        "check_in",
        "check_out",
        "update",
        "extend",
        "shorten",
        "move_room",
        # STAYS-ARRIVALS-DEPARTURES §30 — reverse a mistaken check-in through an
        # organised reversal flow (never a hard delete): reverse the stay, folio
        # and room state with a mandatory reason + audit. Deliberately separate
        # from check_out.
        "reverse_check_in",
        # STAYS rate-integrity remediation — set/override an agreed nightly rate on
        # a stay (an extension OVERRIDE at a different rate, or legacy rate
        # remediation). Deliberately separate from extend/finance: a precise
        # pricing authorisation, always with a reason + audit.
        "rate_override",
    ],
    # Internal finance (Phase 8). Folios/charges/payments/invoices live under
    # one clear `finance` section; expenses have their own.
    "finance": [
        "view",
        "create",
        "update",
        "close",
        "void",
        "charge_create",
        "charge_void",
        # Folio closure round: corrections AFTER a record's void window
        # closed — deliberately separate from charge_create/payment_void.
        "adjust",
        "payment_create",
        "payment_void",
        "payment_reverse",
        "invoice_create",
        "invoice_issue",
        "invoice_void",
        # STAYS-ARRIVALS-DEPARTURES round — deliberately separate codes:
        # §37 refund = a real payout of a credit balance to the guest (distinct
        #   from payment_reverse, which is a correction inside the void rules);
        # §42 reopen = reopen a CLOSED folio (special permission + reason + audit,
        #   respecting the daily close); distinct from close;
        # §35 insurance_manage = record / refund / deduct a refundable insurance
        #   held separately from the folio account.
        "refund",
        "reopen",
        "insurance_manage",
    ],
    # Expenses closure: `reverse` = the full linked counter-voucher AFTER the
    # record's void window closed — deliberately separate from create/void.
    "expenses": ["view", "create", "update", "void", "reverse"],
    # Service catalog + internal service orders (Phase 9): restaurant / café /
    # room service. The blueprint's `restaurant.*` codes below are vestigial and
    # NOT used; Phase 9 uses these explicit sections instead.
    # Restaurant/café closure: `tables_manage` covers the simple outlet
    # tables (create/edit/status); `settle_direct` is the direct-payment
    # settlement — deliberately separate from post_to_folio.
    "services": ["view", "create", "update", "delete", "tables_manage"],
    "service_orders": [
        "view",
        "create",
        "update",
        "settle_direct",
        "cancel",
        "status_update",
        "post_to_folio",
    ],
    "restaurant": ["view", "create_order"],
    # Daily room operations (Phase 10): housekeeping tasks, maintenance
    # requests and lost & found — each with explicit operation codes.
    # housekeeping.inspect arrived with the housekeeping final closure —
    # supervisor-only approve/reject of completed rooms (policy-gated).
    "housekeeping": [
        "view",
        "create",
        "update",
        "cancel",
        "status_update",
        "assign",
        "inspect",
    ],
    "maintenance": [
        "view",
        "create",
        "update",
        "cancel",
        "status_update",
        "assign",
        "close",
    ],
    "lost_found": ["view", "create", "update", "status_update", "close"],
    # Staff & permissions management (Phase 11). `manage` is a vestigial
    # blueprint code and NOT used; the explicit operations below are.
    "staff": [
        "view",
        "create",
        "update",
        "deactivate",
        "permissions_view",
        "permissions_update",
        # Staff closure: sensitive lifecycle actions, each on its own grant
        # (never folded into `update`).
        "delete",
        "change_email",
        "manage_managers",
        "manage",
    ],
    # Reports & analytics (Phase 13). Read-only; finance/operations/shifts
    # sections and CSV export are gated separately on top of `view`.
    "reports": ["view", "finance", "operations", "shifts", "export"],
    # In-app notifications + activity center (Phase 14). No external channels.
    "notifications": ["view", "update"],
    "activity": ["view", "view_all"],
    "settings": ["view", "update"],
    # Shifts + handover (Phase 12).
    "shifts": [
        "view",
        "create",
        "update",
        "close",
        "cancel",
        "handover",
        "accept_handover",
    ],
    # Daily close (Phase 12). `run` is a vestigial blueprint code and NOT
    # used; `reopen` is registered for the future — reopening a closed day is
    # deliberately not built in Phase 12 (documented).
    "daily_close": ["view", "prepare", "close", "reopen", "run"],
    # Reservations rework round. Reservation guest documents (national id /
    # passport / residence / visa / marriage contract / family book, etc.)
    # live in secure PRIVATE storage streamed only to authorized users.
    # `view` gates reading/streaming a document, `upload` gates creating one,
    # `replace` gates overwriting an existing document's file — deliberately
    # separate codes, never bundled together.
    "reservation_documents": ["view", "upload", "replace"],
    # Manual currency-exchange rate for a multi-currency payment. There is no
    # reference-rate table this round, so `override` gates entering a manual FX
    # rate when the payment currency differs from the folio/base currency.
    "exchange_rate": ["override"],
}

ALL_PERMISSIONS: frozenset[str] = frozenset(
    f"{section}.{operation}"
    for section, operations in PERMISSIONS_BY_SECTION.items()
    for operation in operations
)


def is_valid_permission(code: str) -> bool:
    return code in ALL_PERMISSIONS
