# Funduqii — External Integrations Architecture

> **Status:** foundation established in **Phase 1.6**. Documentation + a
> lightweight, disabled-by-default code seam (`apps/integrations`). **No real
> integration, no external call, no secrets.**

---

## 1. Principle: adapter / provider pattern

Funduqii talks to external services **only** through a provider interface (an
adapter). The rest of the app depends on the **interface**, never on a specific
vendor SDK. This lets us swap providers, run a no-op in development, and add new
providers without touching business code.

## 2. Provider categories

- **Maps provider** — display / geocoding / autocomplete.
- **Messaging provider** — WhatsApp (official), and generally the send pipeline.
- **Email provider** — transactional email (later).
- **SMS provider** — text messages (later).
- **Payment provider** — payments (later phase).
- **Booking / channel-manager provider** — OTA/channel sync (later).

## 3. Default provider: disabled / no-op

- In development (and by default everywhere), every provider is **disabled** and
  resolves to a **no-op** that performs no external call and sends nothing.
- Implemented today: `apps/integrations` with `NoopMessagingProvider` and
  `NoopMapsProvider`, selected via `registry.get_messaging_provider()` /
  `get_maps_provider()`. Config helpers (`is_messaging_enabled()`, …) report
  `False` until a real provider is configured.

## 4. Rules for every external integration

Each integration MUST:

- **Read its settings from env** (never hardcode); **no secrets in Git**.
- Have a **timeout** on every network call.
- Have a **retry strategy** where appropriate (bounded, with backoff).
- **Log failures clearly** (without leaking secrets/PII).
- **Not break the core request** when the call is **non-critical** (fail soft).
- Use **Celery** for heavy/slow or non-critical work (don't block the request).

## 5. Sync vs async; blocking vs non-blocking

- **Async (Celery)** — the default for messaging, notifications, and any slow or
  non-critical call. The user's request returns immediately.
- **Sync** — only when the caller genuinely needs the result inline (e.g. a
  payment authorization during checkout in its future phase).
- **Blocking** — reserved for **critical** integrations where the operation
  cannot proceed without the external result (and must fail if it fails).
- **Non-blocking** — everything else; failures are logged and retried, never
  fatal to the core flow.

## 6. Auditing & observability (later)

Sensitive integrations (payments, and any state-changing external call) get
**audit logging** and metrics in their phase — request/response metadata (never
secrets), status, latency, and failures — feeding the monitoring strategy.

## 7. Out of scope for Phase 1.6

No real provider implementations, no external packages/SDKs, no network calls,
no models, no APIs. Only the interfaces, no-op providers, and rules above.
