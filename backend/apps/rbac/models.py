"""Per-membership permission grants.

A grant assigns one registry permission code to one hotel membership. Unknown
codes are rejected at validation time (``full_clean`` runs on every save), so
no cosmetic/unknown permissions can be stored.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from .registry import is_valid_permission


class HotelPermissionGrant(models.Model):
    membership = models.ForeignKey(
        "tenancy.HotelMembership",
        on_delete=models.CASCADE,
        related_name="permission_grants",
    )
    code = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "permissions"
        ordering = ["membership_id", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "code"],
                name="unique_membership_permission",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.membership_id}:{self.code}"

    def clean(self):
        if not is_valid_permission(self.code):
            raise ValidationError({"code": f"Unknown permission code: {self.code}"})

    def save(self, *args, **kwargs):
        # Enforce registry validation on every write path.
        self.full_clean()
        super().save(*args, **kwargs)
