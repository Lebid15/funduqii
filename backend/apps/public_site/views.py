"""Public website APIs (Phase 15), under /api/v1/public/.

Unauthenticated by design, therefore aggressively limited: read-only hotel
display + availability, ONE write (booking creation), and token-gated booking
management. Scoped throttling protects every endpoint. Nothing internal ever
leaves this module: no staff, no finance, no folio, no internal notes, no
room numbers, no other hotels.
"""
from __future__ import annotations

import datetime

from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.rooms.models import RoomType

from . import services


class PublicAPIView(APIView):
    """Base for all public endpoints: anonymous + scoped throttle."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"


def _get_settings_or_404(slug: str):
    settings_obj = services.get_published_hotel(slug)
    if settings_obj is None:
        raise NotFound("Hotel not found.")
    return settings_obj


class PublicSiteSettingsView(PublicAPIView):
    """The platform's public-website configuration (Phase 16): header link
    visibility + label overrides, hero texts, platform contact info and the
    footer. Everything in this model is public by design — no secrets, no
    internal configuration, no hotel data."""

    def get(self, request: Request) -> Response:
        from apps.platform.models import PlatformPublicSettings

        s = PlatformPublicSettings.load()
        return Response(
            {
                "header": {
                    "show_home_link": s.show_home_link,
                    "show_hotels_link": s.show_hotels_link,
                    "show_contact_link": s.show_contact_link,
                    "show_book_now_button": s.show_book_now_button,
                    "show_trial_button": s.show_trial_button,
                    "home_label": s.header_home_label,
                    "hotels_label": s.header_hotels_label,
                    "contact_label": s.header_contact_label,
                    "book_now_label": s.header_book_now_label,
                    "trial_label": s.header_trial_label,
                },
                "hero": {
                    "title": s.hero_title,
                    "subtitle": s.hero_subtitle,
                    "primary_button_label": s.hero_primary_button_label,
                    "primary_button_url": s.hero_primary_button_url,
                    "secondary_button_label": s.hero_secondary_button_label,
                    "secondary_button_url": s.hero_secondary_button_url,
                },
                "contact": {
                    "phone": s.public_phone,
                    "whatsapp": s.public_whatsapp_display,
                    "email": s.public_email,
                    "address": s.public_address,
                    "facebook_url": s.facebook_url,
                    "instagram_url": s.instagram_url,
                    "website_url": s.website_url,
                },
                "footer": {"text": s.footer_text},
            }
        )


def _hotel_card(settings_obj) -> dict:
    media = services.hotel_media_payload(settings_obj.hotel)
    return {
        "slug": settings_obj.public_slug,
        "name": settings_obj.display_name or settings_obj.hotel.name,
        "short_description": settings_obj.short_description,
        "city": settings_obj.city,
        "country": settings_obj.country,
        "star_rating": settings_obj.star_rating,
        "featured": settings_obj.public_featured,
        "booking_enabled": services.booking_open(settings_obj),
        "cover_url": media["cover_url"],
        "logo_url": media["logo_url"],
    }


class PublicHotelListView(PublicAPIView):
    def get(self, request: Request) -> Response:
        qs = services.published_hotels_qs()
        p = request.query_params
        if p.get("q"):
            q = p["q"]
            qs = (
                qs.filter(display_name__icontains=q)
                | qs.filter(hotel__name__icontains=q)
                | qs.filter(city__icontains=q)
            )
        if p.get("city"):
            qs = qs.filter(city__iexact=p["city"])
        if p.get("country"):
            qs = qs.filter(country__iexact=p["country"])
        rows = [_hotel_card(s) for s in qs.distinct()[:60]]
        return Response({"count": len(rows), "results": rows})


class PublicHotelDetailView(PublicAPIView):
    def get(self, request: Request, slug: str) -> Response:
        settings_obj = _get_settings_or_404(slug)
        media = services.hotel_media_payload(settings_obj.hotel)
        room_types = [
            services.room_type_public_payload(settings_obj, rt)
            for rt in services.public_room_types_qs(settings_obj.hotel)
        ]
        return Response(
            {
                **_hotel_card(settings_obj),
                "description": settings_obj.description,
                "address": settings_obj.address_line,
                "area": settings_obj.area,
                "phone": settings_obj.phone,
                "whatsapp": settings_obj.whatsapp_number,
                "email": settings_obj.email,
                "website": settings_obj.website_url,
                "check_in_time": settings_obj.check_in_time,
                "check_out_time": settings_obj.check_out_time,
                "cancellation_policy": settings_obj.cancellation_policy,
                "terms": settings_obj.public_terms_text,
                "min_nights": settings_obj.public_min_nights,
                "max_nights": settings_obj.public_max_nights,
                "requires_confirmation": settings_obj.public_booking_requires_confirmation,
                "gallery": media["gallery"],
                "room_types": room_types,
            }
        )


class AvailabilityQuerySerializer(serializers.Serializer):
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    room_type = serializers.IntegerField(required=False, allow_null=True)


class PublicAvailabilityView(PublicAPIView):
    def get(self, request: Request, slug: str) -> Response:
        settings_obj = _get_settings_or_404(slug)
        query = AvailabilityQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        data = query.validated_data
        services.validate_public_dates(
            settings_obj, data["check_in"], data["check_out"]
        )
        return Response(
            {
                "check_in": str(data["check_in"]),
                "check_out": str(data["check_out"]),
                "booking_enabled": services.booking_open(settings_obj),
                "room_types": services.public_availability(
                    settings_obj,
                    data["check_in"],
                    data["check_out"],
                    room_type_id=data.get("room_type"),
                ),
            }
        )


class PublicBookingSerializer(serializers.Serializer):
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    room_type = serializers.IntegerField()
    rooms_count = serializers.IntegerField(
        min_value=1, max_value=services.MAX_ROOMS_PER_BOOKING, default=1
    )
    adults = serializers.IntegerField(min_value=1, max_value=services.MAX_GUESTS_PER_BOOKING)
    children = serializers.IntegerField(
        min_value=0, max_value=services.MAX_GUESTS_PER_BOOKING, default=0
    )
    guest_name = serializers.CharField(max_length=180)
    guest_phone = serializers.CharField(max_length=32)
    guest_email = serializers.EmailField(required=False, allow_blank=True, default="")
    guest_nationality = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    special_requests = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, default=""
    )
    accept_terms = serializers.BooleanField()

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError("Terms must be accepted.")
        return value


class PublicBookingCreateView(PublicAPIView):
    throttle_scope = "public_booking"

    def post(self, request: Request, slug: str) -> Response:
        settings_obj = _get_settings_or_404(slug)
        if not services.booking_open(settings_obj):
            raise PermissionDenied("Online booking is not available for this hotel.")
        serializer = PublicBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        room_type = RoomType.objects.filter(
            id=data["room_type"], hotel=settings_obj.hotel, public_is_visible=True
        ).first()
        if room_type is None:
            raise NotFound("Room type not found.")
        reservation, token = services.create_public_booking(
            settings_obj,
            room_type=room_type,
            check_in=data["check_in"],
            check_out=data["check_out"],
            rooms_count=data["rooms_count"],
            adults=data["adults"],
            children=data["children"],
            guest_name=data["guest_name"],
            guest_phone=data["guest_phone"],
            guest_email=data.get("guest_email", ""),
            guest_nationality=data.get("guest_nationality", ""),
            special_requests=data.get("special_requests", ""),
        )
        payload = services.public_booking_payload(settings_obj, reservation)
        # The ONLY time the plaintext token is ever returned.
        payload["manage_token"] = token
        return Response(payload, status=status.HTTP_201_CREATED)


def _get_booking_or_404(reference: str, token: str):
    reservation = services.find_public_booking(reference)
    if reservation is None or not services.token_matches(reservation, token):
        # One indistinguishable answer for wrong reference OR wrong token.
        raise NotFound("Booking not found.")
    return reservation


class PublicBookingManageView(PublicAPIView):
    def get(self, request: Request, reference: str) -> Response:
        token = request.query_params.get("token") or request.headers.get(
            "X-Manage-Token", ""
        )
        reservation = _get_booking_or_404(reference, token)
        settings_obj = getattr(reservation.hotel, "settings", None)
        if settings_obj is None:
            raise NotFound("Booking not found.")
        return Response(services.public_booking_payload(settings_obj, reservation))


class CancelRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class PublicBookingCancelRequestView(PublicAPIView):
    throttle_scope = "public_booking"

    def post(self, request: Request, reference: str) -> Response:
        serializer = CancelRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reservation = _get_booking_or_404(
            reference, serializer.validated_data["token"]
        )
        settings_obj = getattr(reservation.hotel, "settings", None)
        if settings_obj is None:
            raise NotFound("Booking not found.")
        reservation = services.request_public_cancellation(
            reservation, reason=serializer.validated_data.get("reason", "")
        )
        return Response(services.public_booking_payload(settings_obj, reservation))
