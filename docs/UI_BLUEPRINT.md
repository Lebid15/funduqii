# UI Blueprint — Funduqii "Grand Lobby" Redesign

> The approved plan for the full UI redesign. Everything flows from
> `src/styles/tokens.css` → `src/styles/globals.css` → the central primitives.
> No page builds its own styling. Logic, API contracts, routing and i18n keys
> are untouched.

## 1. Direction & mood

**Grand Lobby (الردهة الكبرى)** — the feeling of a well-run luxury hotel lobby:
deep forest-emerald surfaces (lacquered wood, marble), warm ivory paper, brass
details used sparingly, engraved serif titles, calm and unhurried. Operational
surfaces (tables, forms, boards) stay light, quiet and dense enough for staff
who look at them all day. The dark tones live in the *chrome*: sidebar, heroes,
login aside, public footer.

## 2. Palette (exact hexes + WCAG contrast)

### Brand — emerald

| Token | Hex | Contrast notes (measured) |
| --- | --- | --- |
| `--color-primary` | `#166a53` | 6.52:1 vs white — AA/AAA for white button text |
| `--color-primary-hover` | `#125743` | 8.50:1 vs white |
| `--color-primary-active` | `#0e4736` | > 9:1 vs white |
| `--color-primary-strong` | `#0b3a2d` | dark emphasis |
| `--color-primary-soft` | `#e6f3ec` | chip/soft bg; paired text `#0e5340` = 7.90:1 |
| `--color-primary-soft-hover` | `#d7ecdf` | |
| `--color-primary-contrast` | `#ffffff` | |

### Ink — deep forest (dark chrome)

| Token | Hex | Contrast notes |
| --- | --- | --- |
| `--color-ink` | `#0d2f26` | vs ivory text `#f2ede2` = 12.4:1; vs muted nav `#c2d1c6` = 9.1:1; vs subtle `#9db4a7` = 6.6:1 |
| `--color-ink-raised` | `#144439` | hover/active pills on dark; white on it = 10.9:1 |

### Brass — the accent (used sparingly)

| Token | Hex | Contrast notes |
| --- | --- | --- |
| `--color-accent` | `#b88a33` | decorative only (bars, icons ≥ 3:1 needs check per use) |
| `--color-accent-strong` | `#8a6519` | 5.31:1 vs white — AA text on light |
| `--color-accent-bright` | `#d9bd7f` | 7.95:1 vs ink — AA text on dark |
| `--color-accent-soft` | `#f4edda` | soft gold surface |

### Canvas & neutrals — warm ivory

| Token | Hex |
| --- | --- |
| `--color-bg` | `#f6f4ee` |
| `--color-bg-subtle` | `#efece2` |
| `--color-surface` | `#ffffff` |
| `--color-surface-muted` | `#faf8f2` |
| `--color-surface-sunken` | `#f2efe6` |
| `--color-border` / subtle / strong | `#e6e2d6` / `#eeebe1` / `#d5d0c0` |

### Text

| Token | Hex | Contrast |
| --- | --- | --- |
| `--color-fg` | `#1b2620` | 14.2:1 on ivory |
| `--color-fg-muted` | `#4c5a52` | 6.60:1 ivory / 7.26:1 white |
| `--color-fg-subtle` | `#5f6d63` | 4.95:1 ivory / 5.45:1 white — AA (fixed: old value was ~3:1) |
| `--color-fg-inverse` | `#f6f4ee` | |

### Feedback (calm, warm-tuned)

| Token | Hex | Contrast |
| --- | --- | --- |
| success | `#157f5f` / soft `#e7f5ee` | 4.96:1 on white; soft-pair `#116a4f` = 5.9:1 |
| warning | `#96690f` / soft `#faf3e1` | 4.86:1 on white — doubles as star/brass tone |
| danger | `#c2453f` (hover `#ab3833`) / soft `#fdeeec` | 4.98:1 on white |
| info | `#2563eb` / soft `#eaf1fe` | 5.17:1 on white |

States are never color-only: every alert/badge/state keeps its icon or dot.

## 3. Typography

Self-hosted (public/fonts, ~94KB total, `font-display: swap`, subsets only):

- **Manrope** (variable 200–800, latin + latin-ext) — UI/body/data. Covers TR.
- **Marcellus** (400, latin + latin-ext) — display serif: page titles, heroes,
  brand wordmark, public section titles, login headline.
- **Cairo** (variable 200–1000, arabic subset) — all Arabic glyphs, body AND
  display (Arabic display = Cairo 700, since Marcellus has no Arabic).

Tokens: `--font-sans: "Manrope","Cairo",system-ui,…` and
`--font-display: "Marcellus","Cairo",serif`. Size scale unchanged, plus
`--font-size-5xl: 2.75rem` for the public hero.

**RTL rules:** all `--tracking-*` tokens are zeroed under `[dir="rtl"]` (Arabic
must never be letter-spaced); display elements get `font-weight: 700` under
RTL so Cairo carries the headline weight. Numerals: `tabular-nums` on tables,
stat values and finance figures.

## 4. Space, radius, shadow, motion

- **Spacing**: unchanged 4px scale (`--space-1…16`). Discipline kept.
- **Radius**: unchanged scale (sm 6 / md 10 / lg 14 / xl 20 / 2xl 28 / full).
- **Elevation**: warm-ink tinted shadows (xs→lg), `--shadow-brand` (emerald)
  for primary CTAs/active nav, new `--shadow-gold` for the brass brand-mark.
- **Motion**: unchanged (130/220ms ease-out, `prefers-reduced-motion` kept).
- **Gradients**: `--gradient-brand` (emerald CTA), `--gradient-ink` (sidebar
  rail), `--gradient-hero` (deep forest + faint brass glow), `--gradient-gold`
  (brand mark), `--gradient-surface` (warm card sheen).

## 5. Component-by-component changes

| Component | Change |
| --- | --- |
| App shell | Canvas ivory; content untouched structurally. |
| **Sidebar** | THE move: deep-forest rail (`--gradient-ink`), brass brand-mark, Marcellus wordmark, muted sage nav text, active link = soft ivory pill + 3px brass inline-start bar + white text; user card = translucent panel; light ring focus for dark surface; thin dark scrollbar. RTL mirrors via logical properties (already). |
| Topbar | Ivory translucent + blur (kept), warm border. |
| Buttons | Primary = emerald gradient + brand shadow (tokens do the work); secondary = white + warm border; ghost/danger retuned via tokens. Sizes/behavior unchanged. |
| Badges | Same anatomy; colors flow from new feedback tokens. |
| Console hero | New forest gradient + brass radial glow; eyebrow in brass; title in Marcellus; dot-grid kept but fainter. |
| Stat cards | Tabular numerals; hover lift kept; primary icon chip = emerald gradient; others soft tints. |
| Page/Section headers | Titles in Marcellus (Cairo 700 in Arabic); subtitles muted. |
| Tables | Header on warm muted bg, AA header text, row hover = warm neutral (was primary tint — too loud); tabular numerals; sticky header kept; `.table-scroll` kept. |
| Forms | Inputs unchanged structurally; warm borders, emerald focus (ring kept); select chevron recolored to new muted. |
| Tabs | Sunken ivory track, white active pill, emerald active text. |
| Modal / ConfirmDialog | Warm-ink overlay; radii/paddings kept; mobile sheet behavior kept. |
| Alerts / Toasts | Token-driven retune; toast base = warm ink. |
| Empty/Loading/Error states | Empty icon chip switches to brass soft (distinctive); skeleton shimmer warms via tokens. |
| Room/stay/avail cards | Status accent bars kept (semantic colors); surfaces warm. |
| Board (services/housekeeping) | Sunken ivory columns; cards white. |
| **Login** | Aside: forest gradient + brass glow, Marcellus headline + brass flourish bar, brass feature icons; form card: white, lg shadow, brass-gold brand mark. |
| **Public site** | Header: ivory blur + Marcellus wordmark. Hero: deep forest panel, Marcellus title (5xl), gold flourish, ivory subtitle, features with brass icons; secondary CTA becomes ivory-outline on dark (scoped). Hotel cards: lift hover, brass stars, emerald price/CTA. Detail page: serif hotel name, sticky booking aside with stronger elevation. Footer: deep forest, ivory text, brass link hover. |
| Offline page / PWA | offline.html + manifest.ts + viewport themeColor synced to new hexes (primary `#166a53`, bg `#f6f4ee`). |

## 6. Page-level notes

- **Hotel console (13 pages)** and **Platform console (7 pages)**: inherit
  everything via the shell + primitives; no per-page styling. Highest-traffic
  surfaces (front desk, reservations, finance) benefit from the table/card
  retune automatically.
- **Login**: two-panel kept; aside hidden ≤900px (kept).
- **Public home / hotels / hotel detail / booking manage**: same primitives;
  hero and footer are the warm bookends; content stays light.
- **Print (invoices/receipts)**: `@media print` rules untouched.

## 7. Deliberately KEPT

- Layout structure (grid shell, drawer sidebar ≤900px, sticky topbar).
- Spacing/radius scales, motion timing, `prefers-reduced-motion` support.
- All Phase-17 responsive/mobile/touch/print rules.
- All component anatomies and className hooks (no JSX churn).
- The i18n dictionaries (no key changes needed — redesign is CSS-level).
- Focus-visible ring pattern (plus a light variant for dark surfaces).
- Icon system (lucide via `Icon`), sizes and stroke.

## 8. Known small fixes folded in

- `--color-brand` was referenced but never defined → now defined as an alias.
- `--font-size-md` referenced once (mini-list) → token added as alias.
- `--color-fg-subtle` failed AA for caption text → darkened to `#5f6d63`.
- Hardcoded select-chevron / overlay rgba colors → aligned to new palette.
- Uppercase+tracking labels in RTL → tracking zeroed globally under RTL.
