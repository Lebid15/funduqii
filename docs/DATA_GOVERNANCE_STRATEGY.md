# Funduqii — Data Governance Strategy

> **Status:** rules established in **Phase 1.7**. Documentation only — no models,
> endpoints, or deletion/export tooling are built here. These rules bind the
> operational phases that touch data.

---

## 1. Hotel data ownership

- Each hotel's operational data (rooms, reservations, guests, payments, folio,
  orders, tasks, shifts, closures, media, …) **belongs to that hotel**.
- The **platform owner** administers the platform (hotels, packages,
  subscriptions, commissions) but does not own a hotel's day-to-day records; it
  acts as the data processor/administrator, not the content owner.

## 2. Tenant isolation

- Every hotel-owned record is scoped by `hotel_id` and isolated on the backend
  (established in Phase 2). **A hotel can never read or write another hotel's
  data** — enforced by query scoping + object-level checks, not UI hiding.
- Isolation is a **tested invariant** (see
  [QA_AND_TESTING_STRATEGY.md](QA_AND_TESTING_STRATEGY.md)).

## 3. Guest data

- Guest profiles/documents are **owned by the hotel** that created them and are
  not shared across hotels automatically.
- Handle guest PII per applicable privacy law: collect what is needed, restrict
  access by permission, and support consent/opt-out for messaging (see
  [WHATSAPP_AND_MESSAGING_STRATEGY.md](WHATSAPP_AND_MESSAGING_STRATEGY.md)).

## 4. Documents & images

- **Never stored in the database** — only references (see
  [MEDIA_AND_OBJECT_STORAGE_STRATEGY.md](MEDIA_AND_OBJECT_STORAGE_STRATEGY.md)).
- Private documents (IDs, guest documents) are access-controlled and served via
  signed URLs; namespaced per hotel.

## 5. Export

- A hotel's data must be **exportable** later (data portability): structured
  export (e.g. JSON/CSV) of its records, plus its media. Export is
  tenant-scoped and permission-gated. **Not built in Phase 1.7.**

## 6. Deleting / disabling a hotel

- **Disabling/suspending** a hotel blocks operations but **retains data**
  (matches the subscription rules: data is never deleted on expiry).
- **Deletion** (if ever performed) is deliberate, authorized, logged, and
  preceded by an export + backup. Prefer disable over delete.

## 7. Retention

- Define retention windows per data class (operational logs, notifications,
  audit logs, backups — see [BACKUP_AND_RESTORE_STRATEGY.md](BACKUP_AND_RESTORE_STRATEGY.md)).
- Financial records follow the **longest** legally required retention and are
  not purged on a whim.

## 8. Soft delete vs hard delete

- **Soft delete** (mark inactive/void, keep the row) is the default for
  operationally or financially meaningful records — preserves history and audit.
- **Hard delete** (remove the row) is reserved for truly transient/throwaway
  data, and only with authorization.
- **Financial records are voided, never deleted** (Void-over-delete — matches
  the blueprint): payments/expenses/folio items are marked `void` with reason,
  actor, and time, and remain for audit.

## 9. Subscription expiry

- On expiry: **no data is deleted**; important operations are restricted per the
  subscription policy until renewal (see the blueprint). Read access and
  export/renewal paths remain.

## Out of scope for Phase 1.7

No deletion/export endpoints, no retention jobs, no models. This document
defines the rules those features must follow.
