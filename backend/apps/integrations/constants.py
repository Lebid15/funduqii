"""Shared constants for the integrations foundation (Phase 1.6).

No models here — these are plain, provider-neutral vocabularies used by the
provider interfaces, the notification catalog, and (later) real integrations.
"""
from __future__ import annotations

# Sentinel meaning "no real provider configured".
DISABLED = "disabled"

# Message delivery lifecycle (see docs/WHATSAPP_AND_MESSAGING_STRATEGY.md).
MESSAGE_STATUS_PENDING = "pending"
MESSAGE_STATUS_QUEUED = "queued"
MESSAGE_STATUS_SENT = "sent"
MESSAGE_STATUS_DELIVERED = "delivered"
MESSAGE_STATUS_FAILED = "failed"
MESSAGE_STATUS_CANCELLED = "cancelled"
MESSAGE_STATUS_DISABLED = DISABLED  # foundation: nothing is actually sent

# Channels a message/notification could use.
CHANNEL_IN_APP = "in_app"
CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_EMAIL = "email"
CHANNEL_SMS = "sms"

# Audiences (who receives a message/notification).
AUDIENCE_PLATFORM_OWNER = "platform_owner"
AUDIENCE_HOTEL_MANAGER = "hotel_manager"
AUDIENCE_HOTEL_STAFF = "hotel_staff"
AUDIENCE_GUEST = "guest"

# Supported template languages (mirror the app's i18n locales).
TEMPLATE_LANGUAGES = ("ar", "en", "tr")
