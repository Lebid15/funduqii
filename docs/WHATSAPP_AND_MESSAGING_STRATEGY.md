# Funduqii — WhatsApp & Messaging Strategy

> **Status:** foundation established in **Phase 1.6**. Documentation + rules
> only. **No message is sent, no WhatsApp API is called, and no token is set.**

---

## 1. Official channels only

- WhatsApp is used **only** via the **official WhatsApp Business Platform /
  Cloud API** (or an officially approved BSP).
- **Forbidden:** WhatsApp Web automation, personal-number automation, scraping,
  or any unofficial/unsupported solution.

## 2. Audiences

Messages target three distinct audiences, each with different content and rules:

- **Guest** — the customer.
- **Hotel owner/manager** — operational alerts for their hotel.
- **Platform owner** — business alerts across the platform.

## 3. Example future messages (not implemented now)

**To the guest:**
- Booking confirmation · pre-arrival reminder · check-in day message ·
  check-out time message · thank-you after checkout · review request ·
  hotel location link.

**To the hotel owner/manager:**
- New reservation · reservation cancelled · new payment · overdue guest ·
  today's departures · important cleaning/maintenance request.

**To the platform owner:**
- New hotel registered · hotel requested a plan · free trial ending soon ·
  payment failed · subscription expired · hotel became inactive.

## 4. Multi-language templates

- Templates exist per language: **ar / en / tr** (mirroring the app locales).
- Templates use **variables**, e.g.: `guest_name`, `hotel_name`,
  `reservation_code`, `check_in_date`, `check_out_date`, `map_url`, `amount`,
  `subscription_plan`.
- WhatsApp message **templates must be pre-approved** by the provider before use.

## 5. Consent & compliance

- **Guest messaging requires consent** per applicable laws/policies; record when
  and how consent was given.
- Provide an **opt-out** path (later) and honor it.
- Respect official **WhatsApp template categories** — `utility`, `marketing`,
  `authentication`, `service` — and use the right category per message.

## 6. Delivery pipeline

- Messages are sent **via Celery**, never inside a direct request/response.
- **Idempotency key** per message prevents duplicate sends (e.g. don't send two
  "booking confirmed" messages for the same reservation).
- **Message status** is tracked (later, when the messaging models exist):
  `pending → queued → sent → delivered`, or `failed` / `cancelled`.
- **Retry policy** for transient failures (bounded retries + backoff); permanent
  failures are logged, not retried forever.
- A failed **non-critical** message must not break the underlying operation.

## 7. Secrets

- **No real token in Git.** WhatsApp credentials live only in server env:
  `WHATSAPP_API_BASE_URL`, `WHATSAPP_BUSINESS_ACCOUNT_ID`,
  `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`,
  `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
- Config surface defaults to `disabled`/empty in Phase 1.6
  (`MESSAGING_PROVIDER`, `WHATSAPP_PROVIDER`).

## 8. Out of scope for Phase 1.6

No sending, no WhatsApp API calls, no templates UI, no messaging models, no
webhooks. The default provider is a **no-op that sends nothing**
(`apps/integrations`). This document defines how real messaging behaves when
built.
