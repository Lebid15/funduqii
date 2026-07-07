# Funduqii — Maps & Location Strategy

> **Status:** foundation established in **Phase 1.6**. Documentation + provider-
> neutral rules only. **No maps integration is implemented, no keys are set, and
> no external maps API is called.**

---

## 1. Why Funduqii needs maps

Hotels have a physical location that guests need to find, and the platform needs
to present it consistently. Maps/location support later powers discovery,
trust, and navigation to the property.

## 2. Where maps will appear (later phases)

- The hotel's **public page**.
- The hotel **details** page.
- **Hotel settings** (the manager sets/edits the location).
- **Search results** (later — map/list of matching hotels).
- An **"open on map"** button / navigation link.

## 3. Provider-neutral location storage

Location data is stored in a **vendor-neutral** way so we are never locked to
one maps provider. Proposed fields for **Hotel Settings** (added in the hotel
phase, not now):

| Field | Notes |
|---|---|
| `country` | ISO name/code |
| `city` | |
| `area` | district/neighborhood |
| `address_line` | street address |
| `latitude` | decimal degrees (nullable) |
| `longitude` | decimal degrees (nullable) |
| `map_url` | ready-to-open link (any provider) |
| `google_place_id` | optional, only if Google Places is used |
| `location_notes` | free text (landmarks, directions) |

Raw coordinates + a neutral `map_url` mean we can render with any provider and
switch providers without a data migration.

## 4. Capabilities (know the difference)

- **Map display** — show a map/pin for a known location. Cheapest; can use
  OpenStreetMap/Leaflet.
- **Geocoding** — turn an address into coordinates (and reverse). A backend call
  to a provider.
- **Autocomplete** — suggest addresses as the user types (Places Autocomplete).
  Higher cost; Google/Mapbox.
- **Place details** — rich metadata for a selected place (e.g. `place_id`).

## 5. Provider selection strategy

- **Google Maps** — when we need **Places/Autocomplete** and high accuracy.
- **OpenStreetMap / Leaflet** — when we only need **map display** at low/no cost.
- **Mapbox** — an alternative later (styling, geocoding) if it fits better.

Choose per-capability: e.g. Leaflet for display, a paid provider only where
Autocomplete/geocoding is genuinely required.

## 6. Keys, limits & security

- **Respect each provider's usage limits and terms.** Do not abuse a free/public
  service beyond its allowed usage.
- **Secret map keys stay in the backend env** (`GOOGLE_MAPS_API_KEY`,
  `MAPBOX_ACCESS_TOKEN`) — never shipped to the browser.
- A **public browser key** (`GOOGLE_MAPS_BROWSER_KEY`) may be exposed **only if**
  it is a browser-restricted key **locked to our domain(s)** and scoped to the
  minimum APIs.
- **Restrict keys by domain and by API/permission** before going live.
- Config surface (all default `disabled`/empty in Phase 1.6):
  `MAP_PROVIDER`, `GOOGLE_MAPS_API_KEY`, `GOOGLE_MAPS_BROWSER_KEY`,
  `MAPBOX_ACCESS_TOKEN`.

## 7. Out of scope for Phase 1.6

No maps page, no settings UI, no models, no provider SDKs, and **no real maps
API calls**. This document defines how location is stored and how a provider is
chosen when the feature is built.

## 8. Enhancements adopted from the legacy reference (Phase 1.8)

- **Map view in hotel results (Phase 12):** the public hotels page can show a
  **list + side map** with hotel **markers**, filters (city/area/price), and
  **opening a hotel's details from the map**.
- **Booking-management link + map (Phase 12):** the guest's booking link can
  open the hotel's location on the map.
- Markers/geocoding stay provider-neutral; keys remain domain-restricted
  (section 6). Nothing maps-related is built now. See
  [PRODUCT_ENHANCEMENT_BACKLOG.md](PRODUCT_ENHANCEMENT_BACKLOG.md).
