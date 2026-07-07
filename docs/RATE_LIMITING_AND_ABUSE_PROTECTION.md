# Funduqii — Rate Limiting & Abuse Protection

> **Status:** strategy established in **Phase 1.7**. **No throttling is wired in
> code now** (to avoid affecting the foundation endpoints/tests); this document
> defines the plan applied in the relevant phases and at the edge (Nginx).

---

## 1. Why

Public and auth-facing endpoints are exposed to brute force, credential
stuffing, scraping, and spam. Rate limiting protects availability and accounts.

## 2. What to protect (and rough intent)

- **Login / token endpoints** — strict per-IP (and per-account) limits to stop
  **brute force** and credential stuffing; back off / lock after repeated
  failures; log failed attempts (feeds monitoring).
- **Public booking endpoints** (later) — per-IP limits + validation to stop
  **spam/abusive** bookings; consider CAPTCHA/anti-bot if needed.
- **Message sending** (later) — provider-side + internal caps; idempotency keys
  prevent duplicates; never send in a loop without bounds.
- **General public APIs** — sane default per-IP limits; heavier limits on
  expensive endpoints.

Different endpoints get **different limits** based on cost and sensitivity.

## 3. Where it is enforced

- **Application layer:** DRF throttling (e.g. `ScopedRateThrottle`,
  `AnonRateThrottle`, `UserRateThrottle`) with per-scope rates, backed by the
  Redis cache for shared counters across processes.
- **Edge layer:** Nginx `limit_req` / connection limits (and Hetzner firewall)
  as a first line of defense.

## 4. Responses

- Return **HTTP 429** with the unified error envelope
  (`{"code": "throttled", ...}`) and a `Retry-After` header where appropriate.

## 5. Phasing

- **Now (Phase 1.7):** documentation only.
- **Phase 2 area (auth):** add throttling to login/token endpoints when the auth
  surface is hardened.
- **Public booking phase:** add booking/anti-spam protections.
- Tune limits from real traffic; alert on sustained 429 spikes.

## Out of scope for Phase 1.7

No throttle classes, no Nginx config, no counters are added now. This is the
plan; implementation happens per endpoint in its phase.
