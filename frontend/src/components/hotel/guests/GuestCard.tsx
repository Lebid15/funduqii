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
  Pencil,
  Phone,
  ShieldCheck,
  Star,
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
 *   (1) Header — a status-badge row (VIP / banned / in-house+room / has-upcoming /
 *       needs-review / past / inactive) then the focal name (a plain heading — the
 *       comprehensive profile modal was removed, so the card IS the interface and
 *       its action icons open each record sub-modal directly).
 *   (2) Identity facts — phone / nationality / document number. Phone + document
 *       are IDENTIFIERS: rendered verbatim (never localised digits) inside a
 *       `<bdi dir="ltr">` so an RTL layout can never reorder them. The document
 *       number is shown exactly as the server sent it — a masked value stays
 *       masked (the card never unmasks client-side).
 *   (3) Stay stats — stays count + repeat/first-time chip, total nights (only when
 *       at least one stay exists), and the last / current stay date. Counts use
 *       the locale numerals (`formatQuantity`); the date uses `formatDateOnly`
 *       (no UTC day-shift).
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
          {needsReview ? (
            <Badge tone="warning" icon={AlertTriangle}>
              {t.guests.needsReview}
            </Badge>
          ) : null}
          {g.is_resident ? (
            <Badge tone="success" variant="filled" icon={DoorOpen}>
              {t.guests.directory.resident}
              {g.current_room_number ? <>{" · "}<bdi dir={IDENTIFIER_DIR}>{g.current_room_number}</bdi></> : ""}
            </Badge>
          ) : null}
          {hasUpcoming ? (
            <Badge tone="info" icon={CalendarRange}>
              {c.upcomingBadge}
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

      {/* 3) Stay stats — localised counts + repeat chip; date without a UTC shift. */}
      <dl className="guest-card__facts">
        <div className="guest-card__fact">
          <dt>{t.guests.directory.stays}</dt>
          <dd className="guest-card__stat">
            {formatQuantity(g.stays_count, locale)}
            <Badge tone={g.is_repeat ? "info" : "neutral"}>
              {g.is_repeat ? t.guests.directory.repeat : t.guests.directory.firstTime}
            </Badge>
          </dd>
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
