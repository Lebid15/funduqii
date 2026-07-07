# Funduqii — Security & Firewall Checklist

> **Status:** checklist established in **Phase 1.5** (expanded). Documentation
> only. Some items are already enforced in code (noted ✅); the rest are applied
> at the deployment/hardening phase.

---

## 1. Network / firewall

- [ ] **Close all non-essential ports.** Only expose what is needed.
- [ ] Public: **80/443** only (Nginx). HTTP redirects to HTTPS.
- [ ] **SSH restricted** — non-default handling, key-only, limited source IPs.
- [ ] **PostgreSQL (5432) NOT public** — internal Docker network / private
      network only.
- [ ] **Redis (6379) NOT public** — internal only; add a password/ACL when not
      isolated.
- [ ] Use **Hetzner Cloud Firewall** (and/or `ufw`) to enforce the above at the
      network edge.

## 2. Server hardening

- [ ] **SSH keys instead of passwords**; disable password auth.
- [ ] **Disable root login** where possible; use a sudo user.
- [ ] **Regular security updates** (unattended-upgrades / scheduled patching).
- [ ] Fail2ban (or equivalent) to throttle brute-force SSH.

## 3. Application security (Django)

- ✅ `DEBUG=False` in production (`config/settings/production.py`); **stack
      traces are never exposed** in production.
- ✅ `ALLOWED_HOSTS` required from env in production.
- ✅ `CORS_ALLOWED_ORIGINS` restricted to real origins (no wildcard).
- ✅ **HTTPS enforced** (`SECURE_SSL_REDIRECT`) and **HSTS**
      (`SECURE_HSTS_SECONDS`, subdomains, preload).
- ✅ Secure cookies (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`),
      `SECURE_CONTENT_TYPE_NOSNIFF`, `X-Frame-Options`.
- ✅ `SECRET_KEY` required from env in production (no insecure fallback).
- [ ] CSRF protection for any cookie-authenticated browser flows (JWT APIs are
      header-based; apply CSRF where session cookies are used).
- [ ] **Rate limiting** for auth endpoints and the public booking endpoints
      (added in their phases; e.g. DRF throttling / Nginx `limit_req`).

## 4. Secrets

- ✅ **No secrets in Git.** Only `*.env.example` / `*.env.prod.example` are
      committed; real env files are git-ignored (`.env`, `*.env.prod`, …).
- [ ] Secrets generated on the server (strong `SECRET_KEY`, DB password).
- [ ] Rotate credentials periodically; never log secrets.

## 5. Data isolation (multi-tenant)

- ✅ Backend enforces tenant isolation (Phase 2): one hotel cannot access
      another hotel's data; permissions enforced server-side, not by hiding UI.
- [ ] Object storage keys namespaced per hotel; private documents via signed
      URLs (see media strategy).

## 6. Monitoring & auditing (later)

- [ ] **Monitor failed login attempts**; alert on spikes.
- [ ] **Logging for sensitive operations** (payments, voids, check-in/out,
      permission changes) — the full Audit Log is a later phase.
- [ ] Centralized/structured logs; no PII/secret leakage in logs.

## 7. TLS

- ✅ HSTS configured in production settings.
- [ ] Valid Let's Encrypt certs, auto-renewed; strong TLS config in Nginx.

> Items marked ✅ are already implemented in Phase 2 / Phase 1.5 settings. The
> unchecked items are the deployment/hardening checklist for go-live.

## 8. Enhancements from the legacy reference (Phase 1.8)

- [ ] **Argon2 password hashing** — a potential later security improvement;
      evaluate its impact on auth tests and the environment before enabling.
- [ ] **Public IDs / UUIDs** — expose a UUID/`public_id` (not the internal
      sequential `id`) for entities in APIs and public links.
- [ ] **No sequential IDs in public URLs** or sensitive public APIs (prevents
      enumeration). See
      [LEGACY_REFERENCE_INSIGHTS.md](LEGACY_REFERENCE_INSIGHTS.md).
