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
    ],
    "availability": ["view"],
    "rooms": ["view", "create", "update", "delete", "status_update"],
    "guests": ["view", "create", "update", "delete"],
    # Front-desk operations (Phase 7). The reservations.check_in/check_out codes
    # above are vestigial blueprint entries and are NOT used; front-desk uses
    # these explicit stays.* codes instead.
    "stays": ["view", "check_in", "check_out", "update"],
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
        "payment_create",
        "payment_void",
        "invoice_create",
        "invoice_issue",
        "invoice_void",
    ],
    "expenses": ["view", "create", "update", "void"],
    # Service catalog + internal service orders (Phase 9): restaurant / café /
    # room service. The blueprint's `restaurant.*` codes below are vestigial and
    # NOT used; Phase 9 uses these explicit sections instead.
    "services": ["view", "create", "update", "delete"],
    "service_orders": [
        "view",
        "create",
        "update",
        "cancel",
        "status_update",
        "post_to_folio",
    ],
    "restaurant": ["view", "create_order"],
    # Daily room operations (Phase 10): housekeeping tasks, maintenance
    # requests and lost & found — each with explicit operation codes.
    "housekeeping": [
        "view",
        "create",
        "update",
        "cancel",
        "status_update",
        "assign",
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
    "staff": ["view", "manage"],
    "reports": ["view"],
    "settings": ["view", "update"],
    "daily_close": ["view", "run"],
}

ALL_PERMISSIONS: frozenset[str] = frozenset(
    f"{section}.{operation}"
    for section, operations in PERMISSIONS_BY_SECTION.items()
    for operation in operations
)


def is_valid_permission(code: str) -> bool:
    return code in ALL_PERMISSIONS
