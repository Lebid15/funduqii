# Funduqii — Documentation

This folder collects project documentation that grows with each phase.

- [PROJECT_BLUEPRINT.md](../PROJECT_BLUEPRINT.md) — the authoritative product & architecture blueprint (Phase 0).
- [DEVELOPMENT_RULES.md](../DEVELOPMENT_RULES.md) — mandatory engineering rules.
- [README.md](../README.md) — how to run the project locally.

## Phase 1.5 — Scalability & production-readiness strategy

- [PERFORMANCE_AND_REALTIME_STRATEGY.md](PERFORMANCE_AND_REALTIME_STRATEGY.md) — caching, background jobs, realtime (Channels), query guardrails, performance budget.
- [DATABASE_INDEX_STRATEGY.md](DATABASE_INDEX_STRATEGY.md) — indexing rules for large tables.
- [HETZNER_PRODUCTION_READINESS.md](HETZNER_PRODUCTION_READINESS.md) — production architecture & deployment plan on Hetzner.
- [PRODUCTION_ENVIRONMENT_MATRIX.md](PRODUCTION_ENVIRONMENT_MATRIX.md) — development vs staging vs production.
- [BACKUP_AND_RESTORE_STRATEGY.md](BACKUP_AND_RESTORE_STRATEGY.md) — backups, retention, restore runbooks.
- [SECURITY_AND_FIREWALL_CHECKLIST.md](SECURITY_AND_FIREWALL_CHECKLIST.md) — network/firewall/app hardening.
- [MONITORING_AND_OBSERVABILITY_STRATEGY.md](MONITORING_AND_OBSERVABILITY_STRATEGY.md) — logs, metrics, alerts, health checks.
- [MEDIA_AND_OBJECT_STORAGE_STRATEGY.md](MEDIA_AND_OBJECT_STORAGE_STRATEGY.md) — media never in DB; object storage plan.
- [SCALING_ROADMAP.md](SCALING_ROADMAP.md) — Stage 1 → Stage 4 scaling path.

Production topology example: [../docker-compose.prod.example.yml](../docker-compose.prod.example.yml).

## Phase 1.6 — Maps, messaging & external integrations strategy

- [MAPS_AND_LOCATION_STRATEGY.md](MAPS_AND_LOCATION_STRATEGY.md) — provider-neutral location storage & maps provider choice.
- [WHATSAPP_AND_MESSAGING_STRATEGY.md](WHATSAPP_AND_MESSAGING_STRATEGY.md) — official WhatsApp only, templates, consent, delivery pipeline.
- [EXTERNAL_INTEGRATIONS_ARCHITECTURE.md](EXTERNAL_INTEGRATIONS_ARCHITECTURE.md) — adapter/provider pattern, no-op defaults, integration rules.
- [NOTIFICATION_EVENTS_CATALOG.md](NOTIFICATION_EVENTS_CATALOG.md) — reference catalog of future platform/hotel/guest events.

## Phase 1.7 — Governance, compliance, QA & release strategy

- [DATA_GOVERNANCE_STRATEGY.md](DATA_GOVERNANCE_STRATEGY.md) — data ownership, isolation, export/delete, retention, soft vs hard delete.
- [AUDIT_LOG_STRATEGY.md](AUDIT_LOG_STRATEGY.md) — what/when/who to audit for sensitive actions.
- [RATE_LIMITING_AND_ABUSE_PROTECTION.md](RATE_LIMITING_AND_ABUSE_PROTECTION.md) — login/booking/messaging/public-API protection.
- [FEATURE_FLAGS_STRATEGY.md](FEATURE_FLAGS_STRATEGY.md) — per-hotel/package toggles; permission vs feature flag.
- [API_VERSIONING_STRATEGY.md](API_VERSIONING_STRATEGY.md) — `/api/v1/`, breaking changes, backward compatibility.
- [QA_AND_TESTING_STRATEGY.md](QA_AND_TESTING_STRATEGY.md) — test types + the release checklist/gate.
- [RELEASE_AND_DEPLOYMENT_WORKFLOW.md](RELEASE_AND_DEPLOYMENT_WORKFLOW.md) — dev/staging/prod, migrations, rollback, approvals.
- [SUPPORT_AND_INCIDENT_RESPONSE.md](SUPPORT_AND_INCIDENT_RESPONSE.md) — report types, severity levels, incident handling.

## Phase 1.8 — Legacy reference insights & enhancement backlog

- [LEGACY_REFERENCE_INSIGHTS.md](LEGACY_REFERENCE_INSIGHTS.md) — ideas harvested from the legacy reference (adopt/adapt/reject/later) mapped to phases.
- [PRODUCT_ENHANCEMENT_BACKLOG.md](PRODUCT_ENHANCEMENT_BACKLOG.md) — tracked backlog of enhancement ideas with target phases and security notes.

## Frontend UI standard (mandatory from Phase 3)

- [FRONTEND_DESIGN_SYSTEM_GUIDELINES.md](FRONTEND_DESIGN_SYSTEM_GUIDELINES.md) — central design system, components, i18n/RTL, responsive, layout, unified states, accessibility, and the page acceptance checklist. **Binding for all UI from Phase 3 onward.**
- [PREMIUM_UI_DESIGN_SYSTEM.md](PREMIUM_UI_DESIGN_SYSTEM.md) — premium visual direction, design tokens, the single icon system (lucide-react), component/table/form/dashboard rules, motion, and RTL rules. **In force from Phase 3.1 onward.**

## Phase 4 — Hotels & hotel settings

- [HOTEL_SETTINGS_AND_MEDIA_STRATEGY.md](HOTEL_SETTINGS_AND_MEDIA_STRATEGY.md) — `HotelSettings` and `HotelMedia` structure, the settings/media separation, image rules (types/sizes/limits/validation), tenant isolation, permissions, and what is deferred to later phases.

## Phase 5 — Floors, room types & rooms

- [FLOORS_ROOM_TYPES_ROOMS_STRATEGY.md](FLOORS_ROOM_TYPES_ROOMS_STRATEGY.md) — the `apps/rooms` app (`Floor`, `RoomType`, `Room`, `RoomStatusLog`), the manual room-status model (no `reserved`/`occupied`), business rules (tenant isolation, uniqueness, capacity, deletion guards, suspended read-only), permissions (`rooms.*`), the `/api/v1/hotel/` API surface, the tabbed rooms console, and what is deferred to later phases.

## Phase 6 — Reservations & availability

- [RESERVATIONS_AND_AVAILABILITY_STRATEGY.md](RESERVATIONS_AND_AVAILABILITY_STRATEGY.md) — the `apps/reservations` app (`Reservation`, `ReservationRoomLine`, `ReservationStatusLog`; optional room assignment in 6.1), the reservation status model (held/confirmed/cancelled/expired — no check-in/out), the central `AvailabilityService` (date-overlap rule, back-to-back, blocking statuses, held expiry, inventory math, overbooking prevention with transactions + row locks), permissions (`reservations.*`, `availability.view`), the `/api/v1/hotel/` API surface, the tabbed reservations console, and why guests/money/check-in/public-booking are deferred.

## Phase 7 — Guests, check-in & check-out

- [GUESTS_CHECKIN_CHECKOUT_STRATEGY.md](GUESTS_CHECKIN_CHECKOUT_STRATEGY.md) — the `apps/guests` (`Guest` directory) and `apps/stays` (`Stay`, `StayGuest`, `StayStatusLog`) apps, the central `CheckInService`/`CheckOutService`, derived occupancy (why there is no manual `room.status = occupied`), current residents / arrivals-today / departures-today, permissions (`guests.*`, `stays.*`), the `/api/v1/hotel/` API surface, the front-desk & guests console, why check-out creates no invoice, and what is deferred to Phase 8.

Phase-specific design notes (data model decisions, API contracts, permission
maps, etc.) will be added here as the project progresses through its phases.
