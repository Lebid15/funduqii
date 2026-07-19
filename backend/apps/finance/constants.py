"""Central, single-source-of-truth constants for the finance app.

This module is deliberately dependency-light (only ``django.db.models`` for the
``TextChoices`` base) so any consumer — including a later ``guest_services``
flow — can import the canonical charge ``source`` values WITHOUT creating an
import cycle. Finance itself NEVER imports ``guest_services``; the arrow only
ever points the other way.
"""
from __future__ import annotations

from django.db import models


class ChargeSource(models.TextChoices):
    """The canonical ``FolioCharge.source`` values.

    Every value here MUST equal a ``source`` string already produced by the
    running code so adopting these constants stores exactly what was stored
    before (NO data migration). ``GUEST_EXTRA_SERVICE`` is the ONE new value,
    added for the guest extra-services flow that a later package wires up.

    NOTE: this enum is intentionally NOT bound to the model field's ``choices``
    — historical rows carry other free-text markers (e.g. ``"legacy"``) and the
    field must keep accepting them. It is a values source-of-truth, not a DB
    constraint.
    """

    MANUAL = "manual", "Manual"
    SERVICE_ORDER = "service_order", "Service order"
    STAY_ROOM = "stay_room", "Room night"
    ROOM_ACCOUNT = "room_account", "Room account"
    ADJUSTMENT = "adjustment", "Adjustment"
    # New — the guest extra-services flow (19 chars; see the ``source`` column
    # width note in migration 0010).
    GUEST_EXTRA_SERVICE = "guest_extra_service", "Guest extra service"


#: The set of ``source`` values counted as guest-facing "service line items" on
#: a folio (guest extra services + posted restaurant/café orders). This is a
#: SOURCE allowlist, NOT ``ChargeType.SERVICE`` — a charge's *type* and its
#: *origin* are different axes. ``TextChoices`` members are ``str`` subclasses,
#: so plain-string membership tests (``charge.source in SERVICE_LINE_SOURCES``)
#: work whether ``charge.source`` is the raw column value or an enum member.
SERVICE_LINE_SOURCES = frozenset(
    {
        ChargeSource.GUEST_EXTRA_SERVICE,
        ChargeSource.SERVICE_ORDER,
    }
)
