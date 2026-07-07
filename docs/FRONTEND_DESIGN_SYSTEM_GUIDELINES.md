# Funduqii — Frontend Design System Guidelines

> **Status:** established now; **binding for all UI from Phase 3 onward.** No
> page, component, button, table, or form may be built ad-hoc. Every interface
> is composed from the central design system, translations, and layout. This is
> a hard gate, not a suggestion.
>
> Builds on: central i18n (Phase 1), permissions (Phase 2), feature flags
> (Phase 1.7 — [FEATURE_FLAGS_STRATEGY.md](FEATURE_FLAGS_STRATEGY.md)), and the
> unified API client. No operational UI is built yet — these are the rules the
> UI phases follow.

---

## 1. Central Design System (tokens only)

- Use **design tokens only** for: colors, fonts, spacing, sizes, shadows,
  borders, radius, hover/focus/disabled states, and z-index (where needed).
- **No random colors** inside pages/components. **No repeated ad-hoc CSS values**
  that already exist as tokens.
- Tokens live centrally (e.g. `frontend/src/styles/tokens.css`) and grow there —
  never hardcoded per page.

## 2. Central components (reuse, don't duplicate)

Build/use shared components instead of re-creating them:

`Button` · `IconButton` · `Card` · `StatCard` · `Table` · `DataTable` · `Input`
· `Select` · `Textarea` · `Checkbox` · `Switch` · `DateInput` · `Modal` ·
`ConfirmDialog` · `Drawer` · `Toast` · `Alert` · `Badge` · `Tabs` · `EmptyState`
· `LoadingState` · `ErrorState` · `PageHeader` · `SectionHeader` · `FilterBar` ·
`Pagination` · `Breadcrumb` · `ResponsiveGrid`.

- Any page needing a button/table/dialog **uses the central component**. A
  bespoke variant is allowed **only with a clear, documented reason**.

## 3. Translation system (no hardcoded text)

- **No hardcoded user-facing strings.** All text comes from the central i18n
  dictionaries.
- Languages: **Arabic · English · Turkish**.
- **RTL for Arabic; LTR for English/Turkish**, with **automatic page direction**
  by language.
- Layout must **not break when text length changes** across languages.
- **No temporary/placeholder text** in final pages.

## 4. Responsive design

- Every page works on **Mobile · Tablet · Laptop · Desktop · Large screens** —
  verified mentally and in the browser at small/medium/large widths.
- **No page that works only on laptop and breaks on mobile.**
- **Large tables must have a clear mobile treatment:** responsive cards,
  controlled horizontal scroll, or an alternative layout.
- **Buttons and filters wrap gracefully** and never pile up randomly.

## 5. Central layout

- Panels are built on a central layout: **AppShell · Sidebar · Topbar ·
  ContentContainer · PageContainer**, with **responsive sidebar behavior**
  (collapsible/drawer on small screens).
- **No page defines its own layout.**

## 6. Unified states

Every data-bearing page handles these **uniformly** (via the shared state
components):

`loading` · `empty` · `error` · `success` · `permission denied` ·
`feature disabled` · `subscription restricted` · `offline / connection problem`
(later).

- **Never leave a page blank** during load or on error — always show a
  skeleton/loading, empty, or error state.

## 7. Accessibility

- Visible **focus states**; **labels** for every field; clear buttons.
- Acceptable **contrast**; **never rely on color alone** to convey state (use
  icon/text too).
- Support **keyboard navigation** wherever possible.

## 8. No random code

Forbidden:

- Re-implementing the same button/table/modal on every page.
- Ad-hoc CSS inside each component when a token/shared style exists.
- Hardcoded text instead of translations.
- Building a non-responsive UI.
- Building UI before confirming permissions and feature flags.
- Building a page that doesn't use the central API client.

## 9. Page acceptance criteria (gate for every new frontend page)

A new page is accepted **only if** it:

- [ ] Uses **central components**.
- [ ] Uses **translations** (no hardcoded strings).
- [ ] Supports **RTL/LTR** with automatic direction.
- [ ] Is **responsive** (mobile → large).
- [ ] Uses the **central API client**.
- [ ] Handles **loading / empty / error** states.
- [ ] Respects **permissions** (backend-enforced; UI reflects them).
- [ ] Respects **feature flags** where relevant.
- [ ] Has **no unjustified ad-hoc CSS**.
- [ ] Has **no hardcoded text**.
- [ ] Does not break **build / lint / typecheck**.

## 10. Relationship to backend enforcement

- The UI **reflects** permissions and feature flags; it never **replaces**
  backend enforcement. Hiding a button is not protection — the backend still
  authorizes every action (Phase 2 rule).
- Money is never computed on the frontend; the UI renders backend results.

---

**Binding note:** These guidelines are mandatory for **Phase 3 and every phase
after it**. Phase 3+ must not be built ad-hoc. See also
[../DEVELOPMENT_RULES.md](../DEVELOPMENT_RULES.md) and PROJECT_BLUEPRINT sections
15 (translation) & 16 (central design).
