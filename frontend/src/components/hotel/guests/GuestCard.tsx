"use client";

import {
  AlertTriangle,
  Ban,
  BedDouble,
  CalendarRange,
  CreditCard,
  DoorOpen,
  FileText,
  Globe,
  History,
  Layers,
  Pencil,
  Phone,
  Repeat,
  ShieldCheck,
  Star,
  UserPlus,
} from "lucide-react";

import { ActionIconButton, Badge, Icon } from "@/components/ui";
import type { GuestDirectoryRow } from "@/lib/api/types";
import { initials } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

import {
  IDENTIFIER_DIR,
  formatDateOnly,
  formatIdentifier,
  formatQuantity,
} from "./guestFormat";

/**
 * One guest as a VERTICAL, equal-height directory card (GUESTS-CLOSURE U-17),
 * mirroring the central `.res-card` / `.room-op-card` pattern. It is a guest
 * IDENTITY card — it deliberately carries NO operational stay controls
 * (check-in / check-out / take-payment / manage-folio / extend / room-move); the
 * front desk owns those.
 *
 * Regions:
 *   (1) Header — a STATUS-badge row then the focal name (a plain heading — the
 *       comprehensive profile modal was removed, so the card IS the interface and
 *       its action icons open each record sub-modal directly). The badges are the
 *       guest's STATES, never numbers: in-house + the current unit ("<type>
 *       <number>") + floor (or a compact "N current units" summary for a guest in
 *       two-plus units at once), the new/repeat guest status (derived from the
 *       stay count, shown exactly once), then VIP / banned / has-upcoming /
 *       needs-review / past / inactive.
 *   (2) Identity facts — phone / nationality / document number. Phone + document
 *       are IDENTIFIERS: rendered verbatim (never localised digits) inside a
 *       `<bdi dir="ltr">` so an RTL layout can never reorder them. The document
 *       number is shown exactly as the server sent it — a masked value stays
 *       masked (the card never unmasks client-side).
 *   (3) Stay stats — NUMBERS only: stays count, total nights (only when at least
 *       one stay exists), and the last / current stay date. Counts use the locale
 *       numerals (`formatQuantity`); the date uses `formatDateOnly` (no UTC
 *       day-shift). The new/repeat STATUS never lives here — it is a top badge.
 *   (4) Actions — few + permission-gated icon buttons that open each record
 *       sub-modal DIRECTLY (no profile step): edit / stays / reservations /
 *       documents / change-log / VIP / block. Each renders only when its callback
 *       is supplied (AND, for documents, the permission passes). There is NO folio
 *       icon on the card. Every icon action carries an aria-label that names the
 *       guest, a translated tooltip, and the central focus/hover styling.
 */
export interface GuestCardProps {
  guest: GuestDirectoryRow;
  /** Cosmetic permission gate — every API re-checks server-side regardless. */
  can: (...codes: string[]) => boolean;
  /** Disables the card's mutating actions while one is in flight for this guest. */
  busy?: boolean;
  /** guests.update — opens the personal-data edit modal DIRECTLY (pencil). */
  onEdit?: (guest: GuestDirectoryRow) => void;
  /** guests.mark_vip — toggles the VIP marker. */
  onToggleVip?: (guest: GuestDirectoryRow) => void;
  /** guests.block — blocks, or unblocks when the guest is already blocked. */
  onBlock?: (guest: GuestDirectoryRow) => void;
  /* --- Record sub-modals opened DIRECTLY from the card. A button renders ONLY
   *     when its callback is supplied (AND, for documents, the permission passes),
   *     so gating stays in the panel. --- */
  onStays?: (guest: GuestDirectoryRow) => void;
  onReservations?: (guest: GuestDirectoryRow) => void;
  onDocuments?: (guest: GuestDirectoryRow) => void;
  onChangeLog?: (guest: GuestDirectoryRow) => void;
}

export function GuestCard({
  guest: g,
  can,
  busy = false,
  onEdit,
  onToggleVip,
  onBlock,
  onStays,
  onReservations,
  onDocuments,
  onChangeLog,
}: GuestCardProps) {
  const { t, locale } = useI18n();
  const c = t.guests.card;

  // Short card indicators, straight from the directory row (backend-derived,
  // never client-inferred): the guest holds an active forthcoming reservation,
  // and/or the profile still needs staff review. Full details live in the
  // reservations modal. Read defensively so a row without the flags is safe.
  const hasUpcoming = g.has_upcoming === true;
  const needsReview = g.needs_review === true;
  // The directory only lists guests with >= 1 real stay, so a non-resident row is
  // a PAST guest and its night total is meaningful. A resident's night total may
  // still be accruing, so it is shown but framed by the "in house" badge.
  const isPast = !g.is_resident && g.stays_count > 0;
  const showNights = g.stays_count > 0;
  // New vs repeat is a STATUS (top badge), not a statistic: repeat once the guest
  // has more than one stay, otherwise a new guest. Every listed guest has >= 1
  // stay, so the badge always renders — exactly once.
  const isRepeat = g.stays_count > 1;
  // The compact current-unit summary. `current_unit` is populated by the backend
  // ONLY for exactly one in-house unit; two-plus units surface as a count.
  const unit = g.current_unit;
  const floorLabel = unit ? unit.floor_name || unit.floor_number || "" : "";
  // The translated floor label is split around its `{floor}` placeholder so ONLY
  // the value is direction-isolated (LTR) while the label itself stays translated.
  const floorPlaceholder = "{floor}";
  const floorSplitAt = c.floor.indexOf(floorPlaceholder);
  const floorBefore = floorSplitAt === -1 ? c.floor : c.floor.slice(0, floorSplitAt);
  const floorAfter =
    floorSplitAt === -1 ? "" : c.floor.slice(floorSplitAt + floorPlaceholder.length);
  const multipleUnits = !unit && g.current_units_count >= 2;
  const unitsSummary = multipleUnits
    ? g.current_units_count === 2
      ? c.currentUnits.dual
      : c.currentUnits.plural.replace("{n}", formatQuantity(g.current_units_count, locale))
    : "";

  // Status accent bar — one visual state, never colour-only (badges carry text).
  const accent = g.is_blocked
    ? "blocked"
    : !g.is_active
      ? "inactive"
      : g.is_resident
        ? "in_house"
        : "past";

  const withName = (template: string) => template.replace("{name}", g.full_name);

  return (
    <article className={`guest-card guest-card--${accent}`} aria-label={g.full_name}>
      {/* 1) Header — status badges (row 1) then the focal name (a plain heading;
          the card's action icons open every record sub-modal directly). */}
      <div className="guest-card__header">
        <div className="guest-card__status-row">
          {/* Residency FIRST: the "in-house" status, then the current unit as a
              clear "<type> <number>" (type = free-text RoomType.name, shown
              as-is; number is an LTR identifier) and a translated floor label —
              OR a compact "N current units" summary for a guest in two-plus units
              at once. A non-resident shows none of these. */}
          {g.is_resident ? (
            <Badge tone="success" variant="filled" icon={DoorOpen}>
              {c.inHouse}
            </Badge>
          ) : null}
          {unit ? (
            <>
              {/* WHERE they are — neutral OUTLINE chips, deliberately apart from
                  the soft-toned WHO/status pills below so "where" reads as its own
                  group. The free-text type name is bidi-isolated (auto <bdi>) and
                  clamped to a single line with an ellipsis + a full-value title;
                  the LTR unit number stays attached to it and is never clipped. */}
              <Badge
                className="guest-card__unit"
                tone="neutral"
                variant="outline"
                icon={BedDouble}
              >
                <bdi className="guest-card__unit-type" title={unit.room_type_name}>
                  {unit.room_type_name}
                </bdi>{" "}
                <bdi dir={IDENTIFIER_DIR}>{unit.room_number}</bdi>
              </Badge>
              {floorLabel ? (
                <Badge className="guest-card__floor" tone="neutral" variant="outline">
                  {floorBefore}
                  <bdi dir={IDENTIFIER_DIR}>{floorLabel}</bdi>
                  {floorAfter}
                </Badge>
              ) : null}
            </>
          ) : multipleUnits ? (
            <Badge
              className="guest-card__unit"
              tone="neutral"
              variant="outline"
              icon={Layers}
            >
              {unitsSummary}
            </Badge>
          ) : null}
          {/* New vs repeat guest — a STATUS, shown exactly once. `success` (soft)
              for a returning guest keeps it clear of the adjacent `info` upcoming
              badge; `primary` welcomes a first-time guest. */}
          <Badge
            tone={isRepeat ? "success" : "primary"}
            icon={isRepeat ? Repeat : UserPlus}
          >
            {isRepeat ? c.repeatGuest : c.newGuest}
          </Badge>
          {g.is_vip ? (
            <Badge tone="vip" variant="filled" icon={Star}>
              {t.guests.vip.badge}
            </Badge>
          ) : null}
          {g.is_blocked ? (
            <Badge tone="danger" variant="filled" icon={Ban}>
              {t.guests.block.badge}
            </Badge>
          ) : null}
          {hasUpcoming ? (
            <Badge tone="info" icon={CalendarRange}>
              {c.upcomingBadge}
            </Badge>
          ) : null}
          {needsReview ? (
            <Badge tone="warning" icon={AlertTriangle}>
              {t.guests.needsReview}
            </Badge>
          ) : null}
          {isPast ? <Badge tone="neutral">{c.pastBadge}</Badge> : null}
          {!g.is_active ? <Badge tone="neutral">{t.guests.inactive}</Badge> : null}
        </div>

        <div className="guest-card__idrow">
          <span className="guest-card__avatar" aria-hidden="true">
            {initials(g.full_name)}
          </span>
          <span className="guest-card__name">{g.full_name}</span>
        </div>
      </div>

      {/* 2) Identity facts — phone / nationality / document. Identifiers render
          verbatim + LTR so RTL never reorders their digits; a masked document
          stays masked (server-controlled). */}
      <dl className="guest-card__facts">
        <div className="guest-card__fact">
          <dt>
            <Icon icon={Phone} size="sm" />
            {t.guests.form.phone}
          </dt>
          <dd>
            <bdi dir={IDENTIFIER_DIR}>{formatIdentifier(g.phone)}</bdi>
          </dd>
        </div>
        <div className="guest-card__fact">
          <dt>
            <Icon icon={Globe} size="sm" />
            {t.guests.form.nationality}
          </dt>
          <dd>{g.nationality || "—"}</dd>
        </div>
        <div className="guest-card__fact">
          <dt>
            <Icon icon={CreditCard} size="sm" />
            {t.guests.list.document}
          </dt>
          <dd>
            <bdi dir={IDENTIFIER_DIR}>{formatIdentifier(g.document_number)}</bdi>
          </dd>
        </div>
      </dl>

      {/* 3) Stay stats — NUMBERS only (the new/repeat STATUS moved to the top
          badges); date without a UTC shift. */}
      <dl className="guest-card__facts">
        <div className="guest-card__fact">
          <dt>{t.guests.directory.stays}</dt>
          <dd>{formatQuantity(g.stays_count, locale)}</dd>
        </div>
        {showNights ? (
          <div className="guest-card__fact">
            <dt>{t.guests.profile.nights}</dt>
            <dd>{formatQuantity(g.nights_total, locale)}</dd>
          </div>
        ) : null}
        <div className="guest-card__fact">
          <dt>{g.is_resident ? t.guests.profile.currentStay : t.guests.directory.lastStay}</dt>
          <dd>{formatDateOnly(g.last_stay_date, locale)}</dd>
        </div>
      </dl>

      {/* 4) Actions — permission-gated icon bar. Each icon opens its record
          sub-modal DIRECTLY (edit / stays / reservations / documents / change-log)
          or fires an inline mutation (VIP / block). No folio icon lives here. */}
      <div className="guest-card__actions">
        <div className="guest-card__iconbar">
          {onStays ? (
            <ActionIconButton
              icon={BedDouble}
              label={withName(c.ariaStays)}
              tooltip={c.viewStays}
              size="sm"
              onClick={() => onStays(g)}
            />
          ) : null}
          {onReservations ? (
            <ActionIconButton
              icon={CalendarRange}
              label={withName(c.ariaReservations)}
              tooltip={c.viewReservations}
              size="sm"
              onClick={() => onReservations(g)}
            />
          ) : null}
          {onDocuments && can("reservation_documents.view") ? (
            <ActionIconButton
              icon={FileText}
              label={withName(c.ariaDocuments)}
              tooltip={c.viewDocuments}
              size="sm"
              onClick={() => onDocuments(g)}
            />
          ) : null}
          {onChangeLog ? (
            <ActionIconButton
              icon={History}
              label={withName(c.ariaChangeLog)}
              tooltip={c.viewHistory}
              size="sm"
              onClick={() => onChangeLog(g)}
            />
          ) : null}
          {onEdit && can("guests.update") ? (
            <ActionIconButton
              icon={Pencil}
              label={withName(c.ariaEdit)}
              tooltip={t.common.edit}
              size="sm"
              disabled={busy}
              onClick={() => onEdit(g)}
            />
          ) : null}
          {onToggleVip && can("guests.mark_vip") ? (
            <ActionIconButton
              icon={Star}
              variant={g.is_vip ? "subtle" : "ghost"}
              label={withName(g.is_vip ? c.ariaUnmarkVip : c.ariaMarkVip)}
              tooltip={g.is_vip ? t.guests.vip.unmark : t.guests.vip.mark}
              size="sm"
              disabled={busy}
              onClick={() => onToggleVip(g)}
            />
          ) : null}
          {onBlock && can("guests.block") ? (
            <ActionIconButton
              icon={g.is_blocked ? ShieldCheck : Ban}
              label={withName(g.is_blocked ? c.ariaUnblock : c.ariaBlock)}
              tooltip={g.is_blocked ? t.guests.block.unblock : t.guests.block.block}
              size="sm"
              disabled={busy}
              onClick={() => onBlock(g)}
            />
          ) : null}
        </div>
      </div>
    </article>
  );
}
