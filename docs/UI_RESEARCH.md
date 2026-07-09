# UI Research — Funduqii Redesign (Phase: full UI redesign)

> External research performed before choosing the design direction. Patterns and
> principles only — no site's design, code, assets or branding was copied.

## 1. What was researched

| Topic | Why |
| --- | --- |
| Hospitality PMS dashboards (Mews, Cloudbeds, RoomRaccoon coverage) | Funduqii's core is a staff console used all day — density, calm and clarity matter more than spectacle. |
| Luxury hotel website palettes & typography | The public site must sell rooms; hospitality warmth converts. |
| Dark-sidebar premium SaaS dashboards & data-dense tables | The single strongest "not a generic admin template" move available to a token-central codebase. |

Sources reviewed (2026):

- Mews product & PMS pages — mews.com/en, mews.com/en/property-management-system
- "The best PMS systems by hospitality segment" — runnr.ai
- "Rethinking the Hotel PMS" — hospitality.today
- "Luxury Hotel Website Design — 52 Examples" — mediaboom.com
- "Website Designs With A Luxury Color Palette" — muffingroup.com
- "Hotel Website Design: Best Practices & Examples" — cloudbeds.com/articles/hotel-website-design
- "Hotel Website Design Trends for Higher Bookings" — mediaboom.com
- "The Anatomy of High-Performance SaaS Dashboard Design: 2026 Trends" — saasframe.io
- "50 Best Dashboard Design Examples" — muz.li
- "Best Dark Mode Dashboard Templates & Design Examples" — adminlte.io / wrappixel.com
- "Admin Dashboard UI/UX: Best Practices" — medium.com/@CarlosSmith24

## 2. Patterns that FIT Funduqii (adopted)

1. **Deep green + warm metallic accent = hospitality luxury.** Emerald/forest
   paired with cream/ivory and a restrained brass highlight is the recurring
   "quiet luxury" recipe on premium hotel sites (Park Lane-style gold + serif).
   It reads *hotel lobby*, not *bootstrap admin*. Adopted as the brand story:
   emerald primary, deep forest ink, brass accent, warm ivory canvas.
2. **Serif display + clean sans body.** Luxury hospitality sites consistently
   pair an elegant serif for headlines with a working sans for UI. Adopted:
   Marcellus (display) + Manrope (UI) + Cairo (Arabic), self-hosted subsets.
3. **Dark-tinted sidebar, light content.** Modern premium SaaS (PostHog-style
   restraint: dark chrome, sparing green accents) uses a dark navigation rail
   to brand the shell while keeping data surfaces light and readable. Adopted:
   deep-forest sidebar with brass active markers; everything else stays light.
4. **Dark grey/green rather than pure black** for dark surfaces, layered with
   subtle elevation. Adopted: ink `#0d2f26` family, never `#000`.
5. **5–9 core elements per dashboard, one clear primary answer.** The existing
   hero + stat grid + workflow cards already follow this; kept, re-skinned.
6. **Monospace/tabular numerics in dense tables** (Bloomberg-terminal lineage).
   Adopted as `font-variant-numeric: tabular-nums` on tables, stat values and
   finance figures — no new font needed.
7. **Booking UX: clear CTAs, few steps, visible price.** Kept the existing
   booking panel flow; elevated price/CTA emphasis only.

## 3. Patterns that do NOT fit (rejected)

1. **Full dark mode console.** Staff work long shifts in varied lighting; the
   data surfaces (tables, forms, folios) stay light for readability. Dark is
   reserved for chrome (sidebar, hero, footer, login aside).
2. **Neon/glassmorphism accents.** Common in 2025-26 dashboard templates;
   conflicts with hospitality calm and WCAG AA. Rejected.
3. **Heavy imagery/video heroes** on the console. Operational tool — rejected;
   the public site gets the warmth instead, via color and type, not payload.
4. **Serif for body/data text.** Luxury sites use serif everywhere; in a PMS it
   degrades scanability. Serif is display-only here.
5. **Component library migration (shadcn/MUI/Tailwind).** The project already
   has a fully centralized token + primitive system; migrating is risk without
   design payoff. Rejected per project rules.
6. **Letter-spacing flourishes in Arabic.** Wide tracking on uppercase labels
   is a Latin-only device; Arabic must never be letter-spaced. Implemented as
   an RTL token override that zeroes all tracking.

## 4. Why the final direction won

"**Grand Lobby**" (deep emerald + brass + ivory + serif display) was chosen over
two other drafted candidates:

- *Calm enterprise clarity* (blue-grey, higher density): safest, but keeps the
  "generic admin" feeling the owner explicitly asked to leave behind.
- *Dense data-ops* (near-black chrome, amber, mono numerals): striking, but
  wrong tone for hospitality and for the public booking site.

Grand Lobby wins because it is the only direction that serves **both** surfaces
with one token system: the console gets a branded dark rail + calm ivory data
surfaces; the public site gets genuine hotel warmth from the same palette.

## 5. Research-based recommendations for later

- Consider a soft "evening mode" (dim, not dark) for night-shift front desk.
- Product photography guidelines (warm, low-saturation) for hotel covers would
  compound the palette's effect on the public site.
- If charts are added (reports), use the emerald/brass ramp with grey support
  colors — never rainbow palettes.
