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
        "cancel",
        "check_in",
        "check_out",
    ],
    "rooms": ["view", "create", "update", "delete", "status_update"],
    "guests": ["view", "create"],
    "payments": ["view", "create", "void"],
    "expenses": ["view", "create"],
    "folio": ["view", "add_charge"],
    "restaurant": ["view", "create_order"],
    "housekeeping": ["view", "update"],
    "maintenance": ["view", "update"],
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
