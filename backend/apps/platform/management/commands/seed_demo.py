"""Idempotent demo seed for a throwaway public demo (e.g. the free Render demo).

Creates ONE active demo hotel with settings, floors, varied room types and
rooms in every operational state, plus two logins: a full-access MANAGER and a
read-only STAFF member (``rooms.view`` only). Everything is keyed on stable
slugs / emails and uses ``get_or_create`` / ``update_or_create`` so running it
repeatedly is safe and converges to the same state — no duplicates.

This is SAMPLE data for demos, NOT production data. It prints the demo login
credentials at the end so the operator can hand them out.

Usage:
    python manage.py seed_demo
"""
from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import AccountType, User
from apps.hotels.models import HotelSettings
from apps.platform.services import create_hotel
from apps.rbac.services import grant_permission
from apps.rooms.models import Floor, Room, RoomType
from apps.rooms.services import change_room_status
from apps.tenancy.models import Hotel, HotelMembership, HotelStatus, MembershipType

# --- Stable identity (idempotency keys) -------------------------------------
DEMO_SLUG = "funduqii-demo-hotel"
DEMO_HOTEL_NAME = "Funduqii Demo Hotel"

MANAGER_EMAIL = "manager@demo.funduqii.app"
STAFF_EMAIL = "frontdesk@demo.funduqii.app"
# Throwaway demo password — printed below; NOT a secret and NOT production.
DEMO_PASSWORD = "Demo12345!"

# --- Room types: varied amenities / capacities / prices / activity ----------
# (code, name, base_cap, max_cap, rate, amenities, is_active)
ROOM_TYPES = [
    ("STD", "Standard", 1, 1, "120.00", ["wifi", "tv", "ac"], True),
    (
        "DLX",
        "Deluxe Double",
        2,
        2,
        "250.00",
        ["wifi", "tv", "ac", "balcony", "minibar", "safe"],
        True,
    ),
    (
        "FAM",
        "Family Suite",
        2,
        4,
        "400.00",
        [
            "wifi",
            "tv",
            "ac",
            "kitchenette",
            "jacuzzi",
            "view",
            "family_friendly",
            "accessible",
            "no_smoking",
        ],
        True,
    ),
    ("ECO", "Economy (no amenities)", 3, 3, "90.00", [], True),
    ("OLD", "Legacy (inactive)", 2, 2, "150.00", ["wifi"], False),
]

FLOORS = ["Ground Floor", "First Floor", "Second Floor"]

# (number, floor_index, type_code, status, note)
ROOMS = [
    ("101", 0, "STD", "available", ""),
    ("102", 0, "DLX", "available", ""),
    ("103", 0, "FAM", "available", ""),
    ("104", 0, "ECO", "available", ""),
    ("201", 1, "STD", "dirty", "guest checked out"),
    ("202", 1, "DLX", "cleaning", ""),
    ("203", 1, "FAM", "maintenance", "AC repair"),
    ("204", 1, "STD", "out_of_service", "flooding"),
    ("301", 2, "DLX", "archived", "renovated away"),
    ("302", 2, "ECO", "available", ""),
    ("303", 2, "FAM", "available", ""),
]


class Command(BaseCommand):
    help = "Seed (idempotently) one active demo hotel with sample rooms and two logins."

    @transaction.atomic
    def handle(self, *args, **options):
        # --- Hotel (active) -------------------------------------------------
        hotel = Hotel.objects.filter(slug=DEMO_SLUG).first()
        if hotel is None:
            hotel = create_hotel(
                name=DEMO_HOTEL_NAME, slug=DEMO_SLUG, status=HotelStatus.ACTIVE
            )
        elif hotel.status != HotelStatus.ACTIVE:
            hotel.status = HotelStatus.ACTIVE
            hotel.save(update_fields=["status", "updated_at"])

        # --- Hotel settings (currency / language / timezone) ----------------
        HotelSettings.objects.update_or_create(
            hotel=hotel,
            defaults={
                "default_currency": "USD",
                "default_language": "en",
                "timezone": "UTC",
            },
        )

        # --- Users + memberships -------------------------------------------
        manager = self._ensure_user(MANAGER_EMAIL, "Demo Manager")
        HotelMembership.objects.update_or_create(
            user=manager,
            hotel=hotel,
            defaults={
                "membership_type": MembershipType.MANAGER,
                "is_primary_manager": True,
                "is_active": True,
            },
        )

        staff = self._ensure_user(STAFF_EMAIL, "Demo Front Desk")
        staff_membership, _ = HotelMembership.objects.update_or_create(
            user=staff,
            hotel=hotel,
            defaults={
                "membership_type": MembershipType.STAFF,
                "is_active": True,
            },
        )
        # Read-only staff: only rooms.view (grant_permission is idempotent).
        grant_permission(staff_membership, "rooms.view")

        # --- Floors ---------------------------------------------------------
        floors = []
        for index, name in enumerate(FLOORS):
            floor, _ = Floor.objects.get_or_create(
                hotel=hotel,
                name=name,
                defaults={"sort_order": index},
            )
            floors.append(floor)

        # --- Room types -----------------------------------------------------
        types_by_code = {}
        for order, (code, name, base_cap, max_cap, rate, amenities, active) in enumerate(
            ROOM_TYPES
        ):
            room_type, _ = RoomType.objects.update_or_create(
                hotel=hotel,
                code=code,
                defaults={
                    "name": name,
                    "base_capacity": base_cap,
                    "max_capacity": max_cap,
                    "base_rate": Decimal(rate),
                    "amenities": amenities,
                    "is_active": active,
                    "public_is_visible": active,
                    "sort_order": order,
                },
            )
            types_by_code[code] = room_type

        # --- Rooms (every operational state) --------------------------------
        for number, floor_index, type_code, status, note in ROOMS:
            room, _ = Room.objects.get_or_create(
                hotel=hotel,
                number=number,
                defaults={
                    "floor": floors[floor_index],
                    "room_type": types_by_code[type_code],
                },
            )
            # change_room_status early-returns when the status + note already
            # match, so repeated runs write no duplicate status logs.
            if status != "available" or room.status != "available":
                change_room_status(
                    room, status, note=note, user=manager, notify=False
                )

        self._report(hotel)

    # -- helpers ------------------------------------------------------------
    def _ensure_user(self, email: str, full_name: str) -> User:
        """Get-or-create a hotel user and (re)set the known demo password so the
        credentials printed below always work, even on a re-run."""
        email = email.strip().lower()
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(
                email=email,
                password=DEMO_PASSWORD,
                full_name=full_name,
                account_type=AccountType.HOTEL_USER,
            )
        else:
            user.set_password(DEMO_PASSWORD)
            user.full_name = full_name
            user.is_active = True
            user.save(update_fields=["password", "full_name", "is_active"])
        return user

    def _report(self, hotel: Hotel) -> None:
        room_count = Room.objects.filter(hotel=hotel).count()
        out = self.stdout
        out.write(self.style.SUCCESS("=== DEMO SEED COMPLETE (idempotent) ==="))
        out.write(f"HOTEL      : {hotel.name} (slug={hotel.slug}, status={hotel.status})")
        out.write("CURRENCY   : USD | language en | timezone UTC")
        out.write(
            f"INVENTORY  : {len(FLOORS)} floors | {len(ROOM_TYPES)} room types "
            f"(1 inactive, 1 no-amenity) | {room_count} rooms"
        )
        out.write(
            "STATES     : available / dirty / cleaning / maintenance / "
            "out_of_service / archived"
        )
        out.write("")
        out.write(self.style.WARNING("Demo logins (sample data — not production):"))
        out.write(f"  MANAGER (full access) : {MANAGER_EMAIL} / {DEMO_PASSWORD}")
        out.write(f"  STAFF   (rooms.view)  : {STAFF_EMAIL} / {DEMO_PASSWORD}")
