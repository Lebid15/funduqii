"use client";

import {
  Archive,
  BedDouble,
  Building2,
  Eye,
  Pencil,
  RefreshCw,
  Users,
  Wallet,
} from "lucide-react";

import { ActionIconButton, Button, Icon, StatusBadge } from "@/components/ui";
import type { RoomBoardRoom } from "@/lib/api/types";
import { formatCapacity, formatDate, formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { cx } from "@/lib/utils";

import { AmenityChips } from "./AmenityChips";
import {
  bookabilityIcon,
  bookabilityTone,
  occupancyIcon,
  occupancyTone,
  occupancyVariant,
  operationalIcon,
  operationalTone,
  operationalVariant,
} from "./boardShared";

/** One room on the operational board (owner polish round): a larger, calmer
 * card split into clear, quietly-divided regions —
 *   (1) header: TWO rows (mirrors ReservationCard, §6.2). Row 1 = STATUS badges
 *       ONLY — the three independent axes (occupancy + operational + the §6.3
 *       bookability badge from `available_now`), central StatusBadge, icon+text
 *       always. Row 2 = the room number (focal point, opens details) + an
 *       explicit Eye ActionIconButton;
 *   (2) room data: type · floor · capacity · nightly price + currency, each
 *       with a unified accompanying icon;
 *   (3) amenities: the top few EFFECTIVE features as chips (full list in the
 *       drawer), hidden entirely when there are none;
 *   (4) current status: the status-specific operational line;
 *   (5) actions: EXACTLY three permission-aware controls — edit, archive
 *       (confirm; hidden when archived) and change status.
 * No delete, no contextual deep-links — those live in the drawer. The number
 * button is a sibling of the action row (never nested), so there is no
 * nested-interactive a11y anti-pattern. */
export function RoomOperationalCard({
  room,
  currency,
  onDetails,
  onEdit,
  onArchive,
  onChangeStatus,
}: {
  room: RoomBoardRoom;
  /** Hotel currency from the board response — the single price source. */
  currency: string;
  onDetails: (room: RoomBoardRoom) => void;
  onEdit: (room: RoomBoardRoom) => void;
  onArchive: (room: RoomBoardRoom) => void;
  onChangeStatus: (room: RoomBoardRoom) => void;
}) {
  const { t, locale } = useI18n();
  const access = useHotelAccess();
  const b = t.rooms.board;
  const p = t.rooms.page;
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));

  const canEdit = can("rooms.update");
  const canStatus = can("rooms.status_update");
  const isArchived = room.operational_status === "archived";

  return (
    <article
      // The accent bar intentionally reflects the effective `display_status`
      // (the calm at-a-glance tone), while the archive badge/action key off the
      // raw `operational_status` — this divergence is by design, do not unify.
      className={cx("room-op-card", `room-op-card--${room.display_status}`)}
      aria-label={`${p.roomLabel} ${room.number}`}
    >
      {/* 1) Header — two stacked rows (mirrors ReservationCard, §6.2). */}
      <div className="room-op-card__header">
        {/* Row 1 — STATUS badges ONLY: occupancy + operational + the §6.3
         * bookability badge. Three axes, each its own StatusBadge (icon+text,
         * never colour alone); the room number is NOT on this row. */}
        <div className="room-op-card__status-row">
          <StatusBadge
            tone={occupancyTone(room.occupancy_status)}
            variant={occupancyVariant(room.occupancy_status)}
            icon={occupancyIcon(room.occupancy_status)}
            label={t.rooms.occupancy[room.occupancy_status]}
          />
          <StatusBadge
            tone={operationalTone(room.operational_status)}
            variant={operationalVariant(room.operational_status)}
            icon={operationalIcon(room.operational_status)}
            label={b.status[room.operational_status]}
          />
          <StatusBadge
            tone={bookabilityTone(room.available_now)}
            variant="outline"
            icon={bookabilityIcon(room.available_now)}
            label={room.available_now ? b.bookableNow : b.notBookable}
          />
        </div>
        {/* Row 2 — the room number (focal; opens details) + an explicit Eye
         * control. The number stays start-aligned and the control end-aligned so
         * their position is stable across every card regardless of badge count.
         * The number button is a sibling of the actions (never nested). */}
        <div className="room-op-card__idrow">
          <button
            type="button"
            className="room-op-card__open"
            onClick={() => onDetails(room)}
            aria-label={`${b.roomDetails} — ${p.roomLabel} ${room.number} · ${room.room_type_name}`}
          >
            <span className="room-op-card__number">{room.number}</span>
          </button>
          <div className="room-op-card__idactions">
            <ActionIconButton
              icon={Eye}
              label={`${b.roomDetails} — ${p.roomLabel} ${room.number}`}
              tooltip={b.roomDetails}
              size="sm"
              variant="ghost"
              onClick={() => onDetails(room)}
            />
          </div>
        </div>
      </div>

      {/* 2) Room data — type · floor · capacity · nightly price, each with a
       * unified icon accompanying (never replacing) the text. */}
      <dl className="room-op-card__facts">
        <div className="room-op-card__fact">
          <dt>
            <Icon icon={BedDouble} size="sm" />
            {b.detailType}
          </dt>
          <dd>{room.room_type_name}</dd>
        </div>
        <div className="room-op-card__fact">
          <dt>
            <Icon icon={Building2} size="sm" />
            {b.detailFloor}
          </dt>
          <dd>{room.floor_name}</dd>
        </div>
        <div className="room-op-card__fact">
          <dt>
            <Icon icon={Users} size="sm" />
            {b.capacity}
          </dt>
          <dd>{formatCapacity(room.base_capacity, room.max_capacity, t, locale)}</dd>
        </div>
        {room.base_rate ? (
          <div className="room-op-card__fact">
            <dt>
              <Icon icon={Wallet} size="sm" />
              {b.pricePerNight}
            </dt>
            <dd>{formatMoney(room.base_rate, currency, locale)}</dd>
          </div>
        ) : null}
      </dl>

      {/* 3) Amenities — top few EFFECTIVE features as chips (§6.1: type defaults
       * − exclusions + additions; full list lives in the details drawer);
       * nothing renders when the room has no effective features. */}
      <AmenityChips amenities={room.amenities} max={4} label={b.roomFeatures} />

      {/* 4) Current status — resident / upcoming / status line. */}
      <OperationalLine room={room} locale={locale} />

      {/* 5) Actions — exactly three, each permission-gated. */}
      <div className="room-op-card__actions">
        {canEdit ? (
          <Button variant="ghost" size="sm" icon={Pencil} onClick={() => onEdit(room)}>
            {t.common.edit}
          </Button>
        ) : null}
        {canStatus && !isArchived ? (
          <Button
            variant="ghost"
            size="sm"
            icon={Archive}
            onClick={() => onArchive(room)}
          >
            {p.archiveRoom}
          </Button>
        ) : null}
        {canStatus ? (
          <Button
            variant="ghost"
            size="sm"
            icon={RefreshCw}
            onClick={() => onChangeStatus(room)}
          >
            {b.changeStatus}
          </Button>
        ) : null}
      </div>
    </article>
  );
}

/** The status-specific line: who is in, who is coming, or what is wrong. */
function OperationalLine({
  room,
  locale,
}: {
  room: RoomBoardRoom;
  locale: Parameters<typeof formatDate>[1];
}) {
  const { t } = useI18n();
  const b = t.rooms.board;

  if (room.display_status === "occupied" && room.current_stay) {
    return (
      <div className="room-op-card__line">
        <strong>
          {b.residentLabel}: {room.current_stay.guest_name}
        </strong>
        <span className="muted">
          {b.plannedCheckOut}: {formatDate(room.current_stay.planned_check_out_date, locale)}
          {room.current_stay.reservation_number
            ? ` · ${room.current_stay.reservation_number}`
            : ""}
        </span>
      </div>
    );
  }
  if (room.display_status === "reserved" && room.next_reservation) {
    return (
      <div className="room-op-card__line">
        <strong>
          {b.upcomingLabel}: {room.next_reservation.guest_name}
        </strong>
        <span className="muted">
          {formatDate(room.next_reservation.check_in_date, locale)} –{" "}
          {formatDate(room.next_reservation.check_out_date, locale)} ·{" "}
          {room.next_reservation.reservation_number}
        </span>
      </div>
    );
  }

  const statusLine: Partial<Record<typeof room.display_status, string>> = {
    available: b.readyNow,
    dirty: b.dirtyLine,
    cleaning: b.cleaningLine,
    maintenance: b.maintenanceLine,
    out_of_service: b.oosLine,
  };
  return (
    <div className="room-op-card__line">
      <span className="muted">
        {statusLine[room.display_status] ?? b.status[room.display_status]}
      </span>
      {room.status_note ? <span>{room.status_note}</span> : null}
      {room.status_changed_at ? (
        <span className="muted">
          {b.lastStatusChange}: {formatDate(room.status_changed_at, locale)}
        </span>
      ) : null}
    </div>
  );
}
