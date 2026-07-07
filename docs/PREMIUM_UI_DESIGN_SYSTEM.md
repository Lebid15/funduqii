# Funduqii — Premium UI Design System

> **Status:** In force from **Phase 3.1** onward.
> **Scope:** Visual language, design tokens, icon system, component rules,
> responsive/RTL rules, and motion. This is the mandatory reference for **every**
> screen built from Phase 3.1 forward — no page or component may deviate.
> **Companion docs:** [FRONTEND_DESIGN_SYSTEM_GUIDELINES.md](FRONTEND_DESIGN_SYSTEM_GUIDELINES.md)
> (engineering rules) and `DEVELOPMENT_RULES.md` §16 (centralized-UI mandate).

Funduqii must read as a **modern, premium SaaS product ready to sell** — not a
prototype. Every screen should feel calm, trustworthy, clean, and consistent.

---

## 1. Visual direction

- **Calm & trustworthy, not loud.** Restrained teal brand on a soft neutral
  canvas with crisp white surfaces. No garish colors, no random gradients, no
  heavy shadows, no visual clutter.
- **Clarity first.** Generous, measured whitespace; strong hierarchy; readable
  type; good contrast (aim for WCAG AA on text).
- **One consistent system.** Elegant cards, legible tables, uniform buttons, a
  single icon set, unified empty/loading/error states.
- **Quiet depth.** Subtle layered shadows and a single accent (teal) carry
  emphasis; color is used with intent (status, actions), never for decoration.

---

## 2. Design tokens (single source of truth)

All visual values live in `frontend/src/styles/tokens.css` as CSS custom
properties. **Components and pages reference tokens only** — never hardcode a
color, spacing, radius, shadow, or font size. Any value used more than once is a
token.

Token groups:

| Group | Examples | Notes |
|---|---|---|
| **Brand** | `--color-primary`, `--color-primary-hover/-active`, `--color-primary-soft`, `--color-primary-contrast` | Refined teal; hover/active are darker steps. |
| **Canvas & surfaces** | `--color-bg`, `--color-bg-subtle`, `--color-surface`, `--color-surface-muted`, `--color-surface-sunken` | Layered backgrounds for depth. |
| **Borders** | `--color-border`, `--color-border-subtle`, `--color-border-strong` | Hairline dividers → input outlines. |
| **Text** | `--color-fg`, `--color-fg-muted`, `--color-fg-subtle`, `--color-fg-inverse` | Primary → captions. |
| **Feedback** | `--color-success/-warning/-danger/-info` + matching `*-soft` | Calm, not neon; `*-soft` for tinted backgrounds. |
| **Focus** | `--ring-color`, `--focus-ring` | Consistent 3px ring on all focusable controls. |
| **Spacing** | `--space-1 … --space-16` | 4px base scale; layout uses these only. |
| **Radius** | `--radius-sm/md/lg/xl/full` | Generous, modern corners. |
| **Typography** | `--font-sans`, `--font-size-xs…3xl`, `--font-weight-*`, `--line-*`, `--tracking-*` | Inter-first stack with Arabic fallbacks. |
| **Layout** | `--container-max`, `--sidebar-width`, `--topbar-height`, `--page-pad` | Shell dimensions. |
| **Elevation** | `--shadow-xs/sm/md/lg` | Subtle, layered, low-alpha. |
| **Motion** | `--ease-out`, `--transition-fast/base` | One easing curve everywhere. |
| **Icons** | `--icon-sm/md/lg`, `--icon-stroke` | Standard icon sizing/stroke. |
| **Z-index** | `--z-sidebar/overlay/modal/toast` | Named layering scale. |

**Rule:** if you need a new visual constant, add a token — do not inline it.

---

## 3. Icon system

- **One library only: `lucide-react`.** No other icon source, no mixing sets,
  and **no emoji as UI icons**.
- All icons render through the central **`Icon`** wrapper
  (`components/ui/Icon.tsx`), which standardizes **size** (`sm` 16 / `md` 18 /
  `lg` 22 px) and **stroke width** (1.75). Decorative icons are `aria-hidden`;
  meaning-bearing icons take a `label`.
- Icons appear consistently in: sidebar nav, dashboard stat cards, primary/table
  action buttons, empty states, alerts/toasts, password show-hide, modal close,
  pagination, and the language switcher.
- Directional icons (chevrons/arrows) **mirror in RTL** (see the `.icon-flip`
  utility and the pagination RTL rule). Never hardcode a left/right icon that
  implies direction without mirroring.

---

## 4. Component rules

Every UI primitive lives in `components/ui/` and is the **only** implementation
of its kind — never re-create buttons, tables, modals, etc. inside a page.

Each interactive component must define, using tokens:

- **default / hover / focus-visible / active / disabled** states,
- a **loading** state where relevant (e.g. `Button loading`, skeletons),
- **icon support** where relevant (leading/trailing icon slots),
- **RTL/LTR** correctness via logical properties,
- text supplied by the caller (translated) — **never hardcoded**.

Canonical components: `Button`, `IconButton`, `Card`, `StatCard`, `Badge`,
`Input`, `Select`, `Textarea`, `Switch`, `PasswordInput`, `Modal`,
`ConfirmDialog`, `DataTable`, `Pagination`, `FilterBar`, `FormField`,
`PageHeader`, `SectionHeader`, `Alert`, `Toast`, `Skeleton`, and the
loading/empty/error `states`.

---

## 5. AppShell, dashboard, tables & forms

- **AppShell** — sticky sidebar with brand mark + icon nav (active pill with an
  inline-start accent bar), a translucent sticky topbar with user avatar +
  identity, language switcher, and logout. Comfortable content padding; no
  content/topbar overlap; no stray scrollbars. On ≤900px the sidebar becomes an
  off-canvas drawer with an overlay.
- **Dashboard** — stat cards use tinted icon chips + clear values; a loading
  **skeleton** mirrors the layout; empty states when there's no data. Never load
  huge tables — only recent/summary slices.
- **Tables** — always inside a horizontal-scroll container so they never break
  the layout; uppercase muted headers, comfortable row spacing, row hover,
  status **badges**, right-aligned action clusters, an accent link on the first
  column.
- **Forms** — grouped in sections/cards, clear labels, token-based inputs with a
  visible focus ring, unified validation/error messaging, and
  `ConfirmDialog` for destructive/sensitive actions.

---

## 6. Responsive rules

Design must work at mobile, tablet, laptop, desktop, and wide screens:

- No broken tables, no off-screen buttons, no overlapping text.
- Stat/card grids reflow with `auto-fill` / `minmax`.
- The sidebar collapses to a drawer on small screens; the topbar never squeezes
  the content.
- Forms collapse to a single column on narrow widths.

---

## 7. RTL / LTR rules

- Use **CSS logical properties** (`margin-inline`, `padding-inline`,
  `inset-inline-start/end`, `border-*-start/end`) — never physical
  `margin-left/right` for directional layout.
- `<html dir lang>` is set from the locale cookie server-side; the client i18n
  provider flips it instantly on language change.
- Mirror directional icons in RTL.
- Test every screen in Arabic (RTL) and English/Turkish (LTR).

---

## 8. Motion & micro-interactions

- Subtle only: hover/color transitions, button press feedback (`translateY(1px)`),
  modal fade+scale, sidebar drawer slide, toast slide, skeleton shimmer.
- One easing curve (`--ease-out`) and short durations (`--transition-fast/base`).
- **Always** honor `prefers-reduced-motion: reduce` (animations/transitions are
  reduced to ~0 globally under that query).
- Motion must never harm performance or block interaction.

---

## 9. Forbidden (no random design)

- ❌ Hardcoded colors, spacing, radii, shadows, or font sizes in pages/components.
- ❌ Duplicated buttons/tables/modals/inputs inside pages.
- ❌ Hardcoded user-facing text (all strings come from the i18n dictionaries).
- ❌ Emoji as icons, or mixing icon libraries.
- ❌ Physical `left/right` CSS for directional layout (breaks RTL).
- ❌ Loud colors, random gradients, exaggerated shadows, heavy motion.
- ❌ Per-page layouts (every platform page uses the central `AppShell`).
