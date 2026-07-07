# Funduqii — Audit Log Strategy

> **Status:** rules established in **Phase 1.7**. The **full audit log is not
> built now** — but it is **mandatory** for sensitive operational actions in
> their phases. This document defines what to record and how.

---

## 1. Purpose

An audit log answers **who did what, when, and in which hotel** for sensitive
actions — for accountability, dispute resolution, and security investigation.

## 2. What every audit entry captures

- **Actor** — the user id (+ account type / membership).
- **Hotel** — the `hotel_id` context (or platform scope for platform actions).
- **Action** — a stable code (e.g. `payment.void`, `reservation.update`).
- **Target** — the affected entity type + id.
- **When** — server timestamp.
- **Summary / metadata** — before/after or key fields (never secrets/full PII).
- **Request context** — where useful (IP/user-agent), without sensitive data.

## 3. Events that MUST be audited (in their phases)

Examples (not exhaustive):

- **Reservations:** create, update, cancel, no-show, check-in, check-out.
- **Finance:** create payment, **void payment**, refund, add/void folio charge,
  create/void expense, issue invoice.
- **Staff & access:** change a staff member's permissions, create/disable a
  user, change membership.
- **Hotel settings:** change hotel settings, toggle public visibility/booking.
- **Subscriptions:** activate/suspend/extend/upgrade a subscription; grant trial.
- **Daily close:** run/re-open a daily closure.
- **Integrations (later):** send messages, external calls with side effects.

## 4. Properties

- **Append-only / immutable** — audit entries are not edited or deleted.
- **Tenant-scoped** — hotel audit entries are visible only within that hotel
  (platform audit within the platform scope), per permissions.
- **Written on the backend**, in the same transaction as the audited change
  where correctness requires it.
- **No secrets/full documents** in audit payloads.

## 5. Relationship to permissions & monitoring

- Permission checks decide **whether** an action is allowed; the audit log
  records **that it happened**. Both are backend-enforced.
- Security-relevant audit events feed alerting/monitoring (see
  [MONITORING_AND_OBSERVABILITY_STRATEGY.md](MONITORING_AND_OBSERVABILITY_STRATEGY.md)
  and [SECURITY_AND_FIREWALL_CHECKLIST.md](SECURITY_AND_FIREWALL_CHECKLIST.md)).

## 6. Audit Log vs Activity Feed (Phase 1.8)

- **Audit Log** — an append-only, tamper-resistant record of sensitive actions
  for **legal retention, traceability, and investigation**.
- **Activity Feed** — a future, read-only **operational** display of recent
  events for quick visibility in the panels.
- **The Activity Feed is NOT a replacement for the Audit Log.** They coexist and
  serve different purposes. See
  [PRODUCT_ENHANCEMENT_BACKLOG.md](PRODUCT_ENHANCEMENT_BACKLOG.md).

## Out of scope for Phase 1.7

No `audit_logs` model, no writer, no viewer. The blueprint already lists
`audit_logs`; this document is the contract for when it is implemented.
