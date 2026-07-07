# Funduqii — Feature Flags Strategy

> **Status:** strategy established in **Phase 1.7**. No flag system is built now.
> This defines how features are toggled per hotel/package later.

---

## 1. Why feature flags

- Turn features **on/off per hotel or per subscription package** without code
  changes or redeploys.
- Roll out features gradually, disable a misbehaving feature quickly, and sell
  capabilities as part of packages.

## 2. Examples of future flags

- `restaurant_enabled`
- `whatsapp_enabled`
- `reports_advanced`
- `public_booking_enabled`
- `trial_enabled`

## 3. Permission vs feature flag (the key distinction)

- **Permission** = *what a specific user is allowed to see/do* inside a hotel
  (`section.operation`, backend-enforced — Phase 2). It is about **the user**.
- **Feature flag** = *whether a capability is available to the hotel at all*
  (often driven by the subscription package). It is about **the hotel/plan**.

Both must pass: a feature must be **enabled for the hotel** *and* the user must
**have permission** to use it. A disabled feature is unavailable even to a
manager who would otherwise have permission.

## 4. Sources of a flag's value

- **Package-level:** the subscription package enables/limits capabilities
  (e.g. advanced reports only on higher tiers).
- **Hotel-level:** a hotel may toggle an available feature (e.g. turn public
  booking off) within what its package allows.
- **Platform-level (kill switch):** the platform owner can globally disable a
  feature in an incident.

Precedence: platform kill switch → package availability → hotel toggle.

## 5. Enforcement

- Feature checks are **backend-enforced** (like permissions) — never by hiding
  UI only. The frontend also reads flags to render appropriately.
- Evaluated server-side and exposed to the client (e.g. via the hotel context)
  so the UI and API agree.

## Out of scope for Phase 1.7

No flag model, resolver, or config. (The Phase 1.6 integration switches such as
`MESSAGING_PROVIDER=disabled` are deployment-level enablement, not per-hotel
feature flags.) This document is the contract for the real flag system later.
