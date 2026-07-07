"""Securely create the first platform owner account.

Password resolution order (no secrets in code):
  1. --password argument
  2. FUNDUQII_PLATFORM_OWNER_PASSWORD environment variable
  3. interactive prompt (TTY only)

Usage:
    python manage.py create_platform_owner --email owner@example.com --full-name "Owner"
"""
from __future__ import annotations

import os
import sys
from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

PASSWORD_ENV_VAR = "FUNDUQII_PLATFORM_OWNER_PASSWORD"


class Command(BaseCommand):
    help = "Create the first platform owner account securely."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--full-name", required=True, dest="full_name")
        parser.add_argument(
            "--password",
            dest="password",
            default=None,
            help=(
                "Optional. Falls back to the "
                f"{PASSWORD_ENV_VAR} env var, then an interactive prompt."
            ),
        )

    def handle(self, *args, **options):
        User = get_user_model()

        email = options["email"].strip().lower()
        full_name = options["full_name"].strip()
        password = options["password"] or os.environ.get(PASSWORD_ENV_VAR)

        if not password:
            if not sys.stdin.isatty():
                raise CommandError(
                    "No password provided. Pass --password, set "
                    f"{PASSWORD_ENV_VAR}, or run in an interactive terminal."
                )
            password = getpass("Password: ")
            if password != getpass("Confirm password: "):
                raise CommandError("Passwords do not match.")

        if not password:
            raise CommandError("Password must not be empty.")

        if User.objects.filter(email=email).exists():
            raise CommandError(f"A user with email {email} already exists.")

        try:
            User.objects.create_platform_owner(
                email=email, password=password, full_name=full_name
            )
        except IntegrityError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Platform owner created: {email}"))
