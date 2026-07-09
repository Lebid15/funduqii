# Funduqii Design System — "Grand Lobby"

> The single source of truth for how Funduqii looks. Everything is driven by
> `frontend/src/styles/tokens.css` (tokens) + `frontend/src/styles/globals.css`
> (component CSS) + `frontend/src/components/ui|layout|public` (primitives).
> **No page defines its own visual style. Ever.**
>
> Direction, rationale and measured WCAG contrasts: see `docs/UI_BLUEPRINT.md`.
> Research trail: see `docs/UI_RESEARCH.md`.

## 1. The direction in one paragraph

Funduqii feels like a well-run luxury hotel lobby. Dark **forest-emerald
chrome** (sidebar, heroes, login aside, public footer) frames light **warm
ivory** operational surfaces. **Brass** is the only flourish — active-nav bars,
eyebrows, the brand mark, small glows — never large areas, never body text
except via the AA-safe `--color-accent-strong`. Titles are set in an engraved
serif (**Marcellus**; **Cairo 700** carries Arabic); everything else is
**Manrope**. Motion stays calm (130/220ms) and respects reduced-motion.

## 2. Token reference (`src/styles/tokens.css`)

### Color

| Group | Tokens | Use |
| --- | --- | --- |
| Brand | `--color-primary`, `-hover`, `-active`, `-strong`, `-soft`, `-soft-hover`, `-contrast`, `--color-brand` (alias) | Primary actions, links, active states, soft chips |
| Ink | `--color-ink`, `--color-ink-raised`, `--color-ink-border` | Dark chrome only: sidebar, footers, dark pills |
| Brass | `--color-accent` (decorative), `--color-accent-strong` (AA text on light), `--color-accent-bright` (AA text on dark), `--color-accent-soft` | Sparing accents: eyebrows, active markers, empty-state icons, brand mark |
| Canvas | `--color-bg`, `--color-bg-subtle`, `--color-surface`, `--color-surface-raised`, `--color-surface-muted`, `--color-surface-sunken` | Page canvas & card layers |
| Border | `--color-border`, `-subtle`, `-strong` | Hairlines; strong = inputs |
| Text | `--color-fg`, `-muted`, `-subtle`, `-inverse` | All AA on their intended surfaces |
| Feedback | `--color-success/-soft`, `--color-warning/-soft`, `--color-danger/-hover/-soft`, `--color-info/-soft`, `--color-neutral-soft` | Badges, alerts, toasts, status accents. Warning doubles as the star/brass tone |

### Gradients

`--gradient-brand` (primary CTA), `--gradient-gold` (brand mark, active-nav
bar, flourishes), `--gradient-ink` (sidebar/footer rail), `--gradient-hero`
(dashboard/public heroes), `--gradient-surface` (card sheen).

### Focus

`--focus-ring` (emerald) on light surfaces; `--focus-ring-inverse` (brass) on
dark surfaces — already wired for `.app-sidebar`, `.public-footer`,
`.public-hero`. Any NEW dark surface must opt into the inverse ring.

### Type

- `--font-sans`: Manrope + Cairo (+system fallbacks) — UI, body, data.
- `--font-display`: Marcellus + Cairo — display only.
- Sizes `--font-size-xs…5xl` (`--font-size-md` = legacy alias of `base`).
- Weights 500/600/700/800. Line heights `--line-tight/snug/normal`.
- Tracking `--tracking-tight/snug/wide/display` — **all zeroed under
  `[dir="rtl"]`** (Arabic is never letter-spaced; do not add literal
  `letter-spacing` values anywhere).

### Space / radius / elevation / motion / icons / z-index

Unchanged scales: 4px spacing (`--space-1…16`), radii (`sm…2xl, full`),
warm-ink shadows (`--shadow-xs…lg`) plus `--shadow-brand` and `--shadow-gold`,
`--transition-fast/base` with `--ease-out`, icon sizes 16/18/22 stroke 1.75,
z-index 40/50/60/70.

## 3. Webfonts (`src/styles/fonts.css`, `public/fonts/`)

Self-hosted woff2, ~94KB total, `font-display: swap`, unicode-range split:

| File | Family | Covers |
| --- | --- | --- |
| `manrope-latin-var.woff2` / `manrope-latin-ext-var.woff2` | Manrope 200–800 var | EN + TR |
| `marcellus-latin.woff2` / `marcellus-latin-ext.woff2` | Marcellus 400 | Display EN + TR |
| `cairo-arabic-var.woff2` | Cairo 200–1000 var | All Arabic glyphs |

Rules: never load additional families; never fetch fonts from a CDN; Arabic
display weight comes from the `[dir="rtl"]` overrides in `globals.css`, not
from new font files.

## 4. Primitive inventory & usage rules

### Layout (`components/layout/`)

| Primitive | Rule |
| --- | --- |
| `AppShell` (+ `.app-shell`) | Console frame. Dark rail + light main. Do not build alternative shells. |
| `Sidebar` (`.app-sidebar*`, `.app-nav*`) | Dark forest rail. Active item = ink-raised pill + 3px gold inline-start bar. Only `aria-current="page"` drives the active state. |
| `Topbar` (`.app-topbar`) | Translucent ivory + blur. Scope label start, bell/lang/logout end. |
| `PageContainer` (`.page-container`) | Every console page's outermost wrapper. |
| `LanguageSwitcher`, `NotificationBell`, `LogoutButton` | Use as-is. |

### UI (`components/ui/`) — always import from `@/components/ui`

| Primitive | Rule |
| --- | --- |
| `Button` (`.btn--primary/secondary/danger/ghost`, `--sm/--lg/--block`) | One primary per view region. Secondary for everything else. Danger only for destructive confirms. |
| `Badge` (`--neutral/primary/success/warning/danger/info`) | Status is icon/dot + color, never color alone. |
| `StatCard`, `WorkflowCard`, `ActionCard`, `SectionCard`, `StatusSummaryCard`, `StepSummaryCard` | KPI/workflow surfaces; numerals are tabular automatically. |
| `PageHeader` / `SectionHeader` | Page titles render in the display serif automatically — pass plain text, no styling. |
| `DataTable` (`.table-scroll > .table`) | Never a bare `<table>`. Wide tables scroll inside `.table-scroll`. |
| `FormField` + `Input/Select/Textarea/PasswordInput/Switch` | All form controls. Errors via `aria-invalid` + `.field__error`. |
| `Modal` / `ConfirmDialog` | Warm-ink overlay, sheet behavior ≤640px. |
| `Alert` / `Toast` | Feedback tokens only. |
| `EmptyState` / `LoadingState` / `ErrorState` / `Skeleton` | Mandatory for every async surface; empty states get the brass icon chip automatically. |
| `Tabs`, `Pagination`, `FilterBar`, `Icon` (lucide only) | Use as-is. |

### Public (`components/public/`)

`PublicShell` (ivory blur header, dark footer bookend), `PublicHotelCard`
(lift hover, brass stars via warning tone), `PublicBookingPanel` (brass-topped
elevated panel). Public heroes use `.public-hero` — dark forest, serif title,
gold flourish; the secondary button restyles itself to ivory-outline inside.

## 5. Do / Don't

**Do**

- Reference tokens for every color, space, radius, shadow, font value.
- Use logical properties only (`inset-inline-start`, `padding-inline`,
  `margin-inline`, `border-inline-…`) — RTL must work with zero extra CSS.
- Put new component styles in the matching `globals.css` section with a
  comment, and reuse existing patterns (`.card`, `.state`, `.board-*`).
- Pair every status color with an icon, dot or label.
- Keep touch targets ≥44px on coarse pointers (the Phase-17 block does this
  for primitives — new interactive elements must match).
- Add UI text through all THREE dictionaries (ar/en/tr) with key parity.

**Don't**

- No hex/rgb values in components or pages — tokens only.
- No `letter-spacing` literals; use tracking tokens (RTL zeroes them).
- No new fonts, icon families, or UI libraries.
- No large brass areas; brass is a detail, not a surface.
- No dark backgrounds for data-dense surfaces (tables/forms stay light).
- No per-page media queries for layout the shell already handles
  (drawer ≤900px, filter stacking ≤640px, `.table-scroll`).
- No touching `@media print` rules without checking invoice/receipt printing.

## 6. Dark-surface recipe (for future chrome)

If a new dark surface is ever needed: bg `--gradient-ink` or `--color-ink`;
text `--color-fg-inverse` (primary) / `#c2d1c6` (muted) / `#9db4a7` (subtle);
accent `--color-accent-bright`; hairlines `--color-ink-border`; focus
`--focus-ring-inverse`. These exact pairings are the AA-verified set.

## 7. PWA / offline sync rule

`--color-primary` and `--color-bg` MUST stay in sync with:
`src/app/manifest.ts` (`theme_color`, `background_color`),
`src/app/layout.tsx` (`viewport.themeColor`), `public/offline.html` inline
styles, and the raster icons in `public/icons/` (regenerate on brand change —
current brand `#166a53`, brass door `#cfa64e`).

## 8. How future pages must follow the system

1. Compose from primitives (`PageHeader` → cards/tables/forms → states).
2. If a visual doesn't exist, extend `globals.css` centrally + document here.
3. Verify in all three locales; check RTL mirroring and Arabic headline weight.
4. Run `npm run lint`, `npx tsc --noEmit`, `npm run build` before delivering.
5. Screenshot desktop + mobile (`openwolf designqc`) and compare against this
   document's rules before merging.
