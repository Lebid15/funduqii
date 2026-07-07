# Funduqii — Product Enhancement Backlog

> **Status:** established in **Phase 1.8**. A tracked list of enhancement ideas
> (mostly harvested from the legacy reference — see
> [LEGACY_REFERENCE_INSIGHTS.md](LEGACY_REFERENCE_INSIGHTS.md)). These are
> **planned ideas, not implemented features**. Nothing here is built yet.

**Status legend:** `Planned` (accepted, scheduled) · `Deferred` (accepted, no
firm phase yet) · `Optional` (nice-to-have) · `Rejected-as-primary`.
**Requires columns:** ✅ yes · ➖ no · ~ partial/later.

---

<div style="overflow-x:auto">

| Feature | Description | Source | Priority | Target Phase | Backend? | Frontend? | Realtime? | Security Notes | Status |
|---|---|---|---|---|---|---|---|---|---|
| Search / Meilisearch | Fast search over hotels, reservations, guests, phones, codes, cities, invoices/payments | Legacy | Medium | Search phase (~12–13) | ✅ | ✅ | ➖ | Read/search **index only**, not source of truth; tenant-scoped results | Deferred |
| Command Palette | Ctrl/Cmd+K quick actions & navigation inside panels | Legacy | Low | After Phase 5 | ~ | ✅ | ➖ | Actions must respect permissions **and** feature flags | Deferred |
| Reservation Timeline / Gantt | Rooms×days timeline, status colors, overlap prevention, weekly/monthly | Legacy | High | Phase 6 | ✅ | ✅ | ~ | No drag/drop before backend validation, transactions, double-booking guard | Planned |
| Booking Management Link (token) | Guest link to review/track/cancel a public booking + map/contact | Legacy | High | Phase 12 | ✅ | ✅ | ➖ | Secure, access-limited token; no sensitive data exposure | Planned |
| Activity Feed | Chronological operational activity (read-only) | Legacy | Medium | Phase 13 | ✅ | ✅ | ~ | **Not** a replacement for Audit Log; tenant-scoped; permission-filtered | Planned |
| Optimistic Updates | Instant UI updates for non-critical actions | Legacy | Medium | UX (from Phase 3) | ➖ | ✅ | ➖ | **Forbidden** for money/reservations/check-in-out; requires clear rollback UI | Planned |
| Skeleton Loading | Skeletons instead of blank pages | Legacy | Medium | Design system (Phase 3) | ➖ | ✅ | ➖ | Perceived-performance only; no data implications | Planned |
| Room Status Interaction Model | Interactive room cards; state changes by permission | Legacy | High | Phase 5 (+ Phase 10) | ✅ | ✅ | ~ | No status change on reservation/guest-linked rooms without backend rules | Planned |
| Separate Check-in/Folio/Checkout screens | Dedicated operational screens | Legacy | High | Phase 7 & 8 | ✅ | ✅ | ➖ | Money on backend; permission-gated actions | Planned |
| Public Hotels Map View | List + side map with markers/filters | Legacy | Medium | Phase 12 | ✅ | ✅ | ➖ | Public data only; provider-neutral maps; domain-restricted keys | Planned |
| Uptime Kuma monitoring | Simple early uptime/health monitor + alerts | Legacy | Low | Monitoring (ops) | ➖ | ➖ | ➖ | Health endpoints only; no sensitive data in probes | Optional |
| Caddy alternative | Auto-SSL reverse proxy alternative to Nginx | Legacy | Low | Hetzner docs | ➖ | ➖ | ➖ | Nginx stays default; Caddy optional note only | Rejected-as-primary |
| Argon2 password hashing | Stronger password hashing | Legacy | Medium | Security (post-eval) | ✅ | ➖ | ➖ | Evaluate impact on auth tests/env before enabling | Deferred |
| UUID / Public ID strategy | Public ids/UUIDs for API & public links | Legacy | High | From Phase 4 (design rule) | ✅ | ~ | ➖ | Never expose sequential IDs in public URLs/sensitive public APIs | Planned |
| Realtime Topics Model | `hotel.{id}.{domain}` WS topics | Legacy | Medium | Phase 13 / realtime phases | ✅ | ✅ | ✅ | Every topic: auth → membership → permission → tenant isolation | Planned |

</div>

---

### Notes
- **Priority** and **Target Phase** are indicative and reviewed as phases open;
  none of these is in scope before its phase.
- Every item, before implementation, must satisfy the relevant rules in
  [../DEVELOPMENT_RULES.md](../DEVELOPMENT_RULES.md) (permissions, tenant
  isolation, backend-source-of-truth money, no secrets, audit, etc.).
- New ideas from any source are added here **first**, before implementation.
