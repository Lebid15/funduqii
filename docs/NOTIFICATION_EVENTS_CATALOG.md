# Funduqii — Notification Events Catalog

> **Status:** catalog established in **Phase 1.6**. This is a **reference list of
> future events**, not an implementation. No events are emitted, no
> notifications are sent. Every new event must be added here **before** it is
> implemented in its phase.

Legend — **audience:** platform_owner / hotel_manager / hotel_staff / guest ·
**channels:** in_app / whatsapp / email / sms · **priority:** low / normal /
high / critical · **timing:** immediate / scheduled / manual · **consent:**
whether guest consent is required · **WhatsApp-suitable:** whether the message
fits an official WhatsApp template category.

---

## Platform events

| Event | Audience | Channels | Priority | Timing | Consent | WhatsApp-suitable |
|---|---|---|---|---|---|---|
| `platform.hotel_registered` | platform_owner | in_app, email, whatsapp | normal | immediate | no | yes (utility) |
| `platform.hotel_plan_requested` | platform_owner | in_app, email, whatsapp | high | immediate | no | yes (utility) |
| `platform.subscription_trial_started` | platform_owner | in_app, email | low | immediate | no | optional |
| `platform.subscription_trial_ending` | platform_owner | in_app, email, whatsapp | high | scheduled | no | yes (utility) |
| `platform.subscription_expired` | platform_owner | in_app, email, whatsapp | high | immediate | no | yes (utility) |
| `platform.payment_failed` | platform_owner | in_app, email, whatsapp | critical | immediate | no | yes (utility) |

## Hotel events

| Event | Audience | Channels | Priority | Timing | Consent | WhatsApp-suitable |
|---|---|---|---|---|---|---|
| `hotel.reservation_created` | hotel_manager, hotel_staff | in_app, whatsapp | normal | immediate | no | yes (utility) |
| `hotel.reservation_cancelled` | hotel_manager, hotel_staff | in_app, whatsapp | normal | immediate | no | yes (utility) |
| `hotel.guest_check_in_today` | hotel_manager, hotel_staff | in_app | normal | scheduled | no | optional |
| `hotel.guest_check_out_today` | hotel_manager, hotel_staff | in_app | normal | scheduled | no | optional |
| `hotel.payment_received` | hotel_manager | in_app, whatsapp | normal | immediate | no | yes (utility) |
| `hotel.expense_created` | hotel_manager | in_app | low | immediate | no | no |
| `hotel.room_needs_cleaning` | hotel_staff | in_app | normal | immediate | no | no |
| `hotel.maintenance_requested` | hotel_manager, hotel_staff | in_app, whatsapp | high | immediate | no | yes (utility) |
| `hotel.daily_close_completed` | hotel_manager | in_app, email | normal | immediate | no | optional |

## Guest events

| Event | Audience | Channels | Priority | Timing | Consent | WhatsApp-suitable |
|---|---|---|---|---|---|---|
| `guest.reservation_confirmed` | guest | whatsapp, email, sms | high | immediate | yes | yes (utility) |
| `guest.reservation_pending` | guest | whatsapp, email | normal | immediate | yes | yes (utility) |
| `guest.check_in_reminder` | guest | whatsapp, sms | normal | scheduled | yes | yes (utility) |
| `guest.check_out_reminder` | guest | whatsapp, sms | normal | scheduled | yes | yes (utility) |
| `guest.thank_you_after_checkout` | guest | whatsapp, email | low | scheduled | yes | yes (utility/marketing) |
| `guest.review_request` | guest | whatsapp, email | low | scheduled | yes | yes (marketing) |

---

## Rules

- **Guest events require consent** and use pre-approved WhatsApp templates.
- Non-critical events are sent **async via Celery**, with idempotency keys.
- Any **new event** is added to this catalog (audience/channels/priority/timing/
  consent/WhatsApp-suitability) **before** implementation.

## Out of scope for Phase 1.6

No event bus, no emitters, no notification models, no sending. This is the
agreed vocabulary for when notifications are built in their phases.
