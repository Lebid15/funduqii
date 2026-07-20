"""Guest extra-services catalog + postings (GUEST-FOLIO-EXTRA-SERVICES-CLOSURE).

Two models:

- :class:`GuestExtraService` — the hotel's catalog of extra services (laundry,
  parking, minibar, damages, …). It is a pure catalog: it is DEACTIVATED, never
  deleted (money history that references it must survive).
- :class:`GuestServicePosting` — the operational/audit link created every time a
  catalog service is posted to a stay's folio. It points at ONE
  ``finance.FolioCharge`` (one-to-one) and carries the idempotency key +
  request fingerprint so a replay is safe.

Dependency direction (HARD RULE): ``guest_services`` depends on ``finance`` and
never the other way round — finance must not import or FK anything here. The only
cross-app FK is ``GuestServicePosting.folio_charge -> finance.FolioCharge`` (this
package -> finance), on ``PROTECT`` so a posted charge is never orphaned. Prices
and tax are FROZEN onto the ``FolioCharge`` snapshots at posting time, so a later
catalog rename / reprice never alters a posted charge (there is deliberately NO FK
from the charge back to the catalog).
"""
from __future__ import annotations

import re
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

MONEY_KW = dict(max_digits=12, decimal_places=2)
ZERO = Decimal("0.00")

#: The project convention for a currency code (mirrors
#: ``apps.hotels.serializers._CURRENCY_CODE_RE``): a 3-letter ISO code stored
#: uppercase. There is no fixed enum of supported currencies in this repo — the
#: "supported set" is any valid 3-letter code — so the catalog validates the
#: SHAPE and the add-service flow enforces ``service.currency == folio.currency``.
_CURRENCY_CODE_RE = re.compile(r"^[A-Z]{3}$")


def normalize_service_name(name: str) -> str:
    """Case/space-normalized key for the per-hotel uniqueness constraint.

    Lower-cases (casefold) and collapses ALL runs of whitespace to a single
    space, so ``"Extra  Bed"``, ``"extra bed"`` and ``" EXTRA BED "`` all map to
    the same key and cannot coexist in one hotel."""
    return " ".join((name or "").split()).casefold()


class GuestServiceCategory(models.TextChoices):
    LAUNDRY = "laundry", "Laundry"
    PARKING = "parking", "Parking"
    TRANSPORT = "transport", "Transport"
    MINIBAR = "minibar", "Minibar"
    EXTRA_BED = "extra_bed", "Extra bed"
    SPECIAL_CLEANING = "special_cleaning", "Special cleaning"
    DAMAGES = "damages", "Damages"
    EXTERNAL_REQUEST = "external_request", "External request"
    OTHER = "other", "Other"


class PricingMode(models.TextChoices):
    #: The catalog price + tax are authoritative; a client-sent price is ignored.
    FIXED = "fixed", "Fixed"
    #: A per-posting price override is allowed (guarded by ``finance.charge_create``
    #: + a mandatory reason); when no override is given the catalog price is used.
    VARIABLE = "variable", "Variable"


class GuestExtraService(models.Model):
    """A hotel's catalog entry for an extra service billed to a guest folio."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.PROTECT, related_name="guest_extra_services"
    )
    name = models.CharField(max_length=180)
    # A case/space-normalized copy of ``name`` (stored on save) that backs the
    # per-hotel uniqueness constraint. Not client-writable.
    name_normalized = models.CharField(max_length=180, editable=False, default="")
    category = models.CharField(
        max_length=20,
        choices=GuestServiceCategory.choices,
        default=GuestServiceCategory.OTHER,
    )
    description = models.CharField(max_length=255, blank=True, default="")
    unit_price = models.DecimalField(**MONEY_KW, default=ZERO)
    currency = models.CharField(max_length=3, default="USD")
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=ZERO
    )  # percent, 0..100
    pricing_mode = models.CharField(
        max_length=10, choices=PricingMode.choices, default=PricingMode.FIXED
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guest_extra_services_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "guest_extra_services"
        ordering = ["display_order", "name", "id"]
        indexes = [
            # C9 — the catalog list is ALWAYS read per-hotel in this exact order
            # (``display_order``, ``name``); without this composite index every
            # request pays a full sort of the hotel's catalog.
            models.Index(
                fields=["hotel", "display_order", "name"],
                name="gxs_hotel_order_name_idx",
            ),
        ]
        constraints = [
            # #12 — per-hotel uniqueness on the NORMALIZED name (case/space).
            models.UniqueConstraint(
                fields=["hotel", "name_normalized"],
                name="uniq_guest_extra_service_name_per_hotel",
            ),
            # #12 — money/shape invariants enforced at the DB, so no path
            # (admin, import, a future service, a bug) can store a corrupt row.
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="guest_extra_service_unit_price_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(tax_rate__gte=0) & models.Q(tax_rate__lte=100),
                name="guest_extra_service_tax_rate_range",
            ),
            models.CheckConstraint(
                condition=models.Q(display_order__gte=0),
                name="guest_extra_service_display_order_non_negative",
            ),
            # Name non-empty after normalization (a blank/whitespace-only name is
            # rejected; the normalized key is never empty for a valid row).
            models.CheckConstraint(
                condition=~models.Q(name_normalized=""),
                name="guest_extra_service_name_present",
            ),
            models.CheckConstraint(
                condition=~models.Q(currency=""),
                name="guest_extra_service_currency_present",
            ),
        ]

    def clean(self):
        # Friendly validation for the admin form (the DB constraints are the
        # backstop). Mirrors the invariants above with typed messages.
        name = (self.name or "").strip()
        if not name:
            raise ValidationError({"name": "A service name is required."})
        currency = (self.currency or "").strip().upper()
        if not _CURRENCY_CODE_RE.match(currency):
            raise ValidationError({"currency": "Currency must be a 3-letter code."})
        if self.unit_price is not None and self.unit_price < ZERO:
            raise ValidationError({"unit_price": "Unit price cannot be negative."})
        if self.tax_rate is not None and not (ZERO <= self.tax_rate <= Decimal("100")):
            raise ValidationError({"tax_rate": "Tax rate must be between 0 and 100."})
        if self.display_order is not None and self.display_order < 0:
            raise ValidationError(
                {"display_order": "Display order cannot be negative."}
            )

    def save(self, *args, **kwargs):
        # Normalize the write-shape once, centrally, so every path (admin, tests,
        # a future importer) stores a clean row: trimmed name, upper-cased
        # currency, and the derived normalized-name key that backs uniqueness.
        self.name = (self.name or "").strip()
        self.currency = (self.currency or "").strip().upper()
        self.name_normalized = normalize_service_name(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.category}) hotel={self.hotel_id}"


class GuestServicePosting(models.Model):
    """The audit/operational record of ONE catalog service posted to a folio.

    Links the stay, the catalog service, and the exact ``finance.FolioCharge``
    created for it, plus the idempotency key + request fingerprint that make a
    replay safe. Never hard-deleted (a correction voids the underlying charge in
    finance; this row stays as history)."""

    hotel = models.ForeignKey(
        "tenancy.Hotel", on_delete=models.PROTECT, related_name="guest_service_postings"
    )
    stay = models.ForeignKey(
        "stays.Stay", on_delete=models.PROTECT, related_name="guest_service_postings"
    )
    guest_extra_service = models.ForeignKey(
        GuestExtraService, on_delete=models.PROTECT, related_name="postings"
    )
    # This package -> finance (the only cross-app FK; PROTECT so a posted charge
    # can never be orphaned by deleting it — finance is void-not-delete anyway).
    # ``related_name="+"`` DISABLES the reverse accessor so ``FolioCharge`` exposes
    # NO relation back to ``guest_services`` — the HARD RULE (finance never depends
    # on guest_services), enforced by the finance foundation's
    # ``test_no_fk_from_charge_to_guest_services``. The forward FK, PROTECT, and the
    # OneToOne (one posting per charge) uniqueness are all preserved.
    folio_charge = models.OneToOneField(
        "finance.FolioCharge", on_delete=models.PROTECT, related_name="+"
    )
    # Empty => no idempotency for this call (each request creates a new posting).
    # A non-empty key is unique per hotel (constraint below), so a retry with the
    # SAME key + SAME fingerprint returns the existing posting instead of a second
    # charge; a DIFFERENT fingerprint on the same key is a 409 conflict.
    idempotency_key = models.CharField(max_length=64, blank=True, default="")
    # A stable sha256 hex over the salient request fields (see services.py).
    request_fingerprint = models.CharField(max_length=64, blank=True, default="")
    # B3 — the mandatory justification supplied when a VARIABLE service was posted
    # at an OVERRIDDEN unit price. Blank for every ordinary posting (a FIXED
    # service, or a variable service billed at the catalog price): the value is
    # only meaningful where an override actually moved the money, and it is the
    # audit counterpart of ``finance.adjust_charge``'s reason. Never client-
    # readable except through the stay's service-lines row.
    price_override_reason = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guest_service_postings_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "guest_service_postings"
        ordering = ["-created_at", "-id"]
        constraints = [
            # #5 — one posting per (hotel, idempotency_key) among NON-BLANK keys.
            # A blank key means "no idempotency", so blanks are excluded from the
            # uniqueness (multiple no-idempotency postings are allowed).
            models.UniqueConstraint(
                fields=["hotel", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_guest_service_posting_idempotency",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"posting stay={self.stay_id} service={self.guest_extra_service_id} "
            f"charge={self.folio_charge_id}"
        )
