"""Custom user model for Funduqii.

Login identifier is the email. ``account_type`` separates the platform owner
(runs the SaaS) from hotel users (managers/staff who belong to hotels via
memberships in the tenancy app). Two-factor auth is intentionally out of scope
for Phase 2.
"""
from __future__ import annotations

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone


class AccountType(models.TextChoices):
    PLATFORM_OWNER = "platform_owner", "Platform Owner"
    HOTEL_USER = "hotel_user", "Hotel User"


class UserManager(BaseUserManager):
    """Manager for the email-based custom user."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("account_type", AccountType.HOTEL_USER)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_platform_owner(self, email: str, password: str | None = None, **extra):
        extra["account_type"] = AccountType.PLATFORM_OWNER
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("account_type", AccountType.PLATFORM_OWNER)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32, blank=True, default="")
    avatar_url = models.URLField(blank=True, default="")
    account_type = models.CharField(
        max_length=32,
        choices=AccountType.choices,
        default=AccountType.HOTEL_USER,
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return self.email

    @property
    def is_platform_owner(self) -> bool:
        return self.account_type == AccountType.PLATFORM_OWNER
