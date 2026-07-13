"use client";

import { Archive, Eye, Pencil, RefreshCw } from "lucide-react";

import { Badge, Button, Icon } from "@/components/ui";
import type { RoomBoardRoom } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { cx } from "@/lib/utils";

import {
  occupancyIcon,
  occupancyTone,
  operationalIcon,
  operationalTone,
} from "./boardShared";

/** One room on the operational board (owner redesign round): a larger, calmer
 * card split into clear sections — (1) title (room number + type) that doubles
 * as the focusable control opening the details drawer, (2) the two independent
 * badges, (3) the core facts, (4) the status-specific operational line, then
 * (5) EXACTLY three permission-aware actions: edit, archive (confirm), and
 * change status. No delete, no contextual deep-links — those live in the
 * drawer. The title button is a sibling of the actions row (never nested), so
 * there is no nested-interactive a11y anti-pattern. */
export function RoomOperationalCard({
  room,
  onDetails,
  onEdit,
  onArchive,
  onChangeStatus,
}: {
  room: RoomBoardRoom;
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
      {/* 1) Title — the focal point AND the drawer affordance (a real button,
       * kept a sibling of the action row so nothing interactive is nested). */}
      <button
        type="button"
        className="room-op-card__open"
        onClick={() => onDetails(room)}
        aria-label={`${b.roomDetails} — ${p.roomLabel} ${room.number} · ${room.room_type_name}`}
      >
        <span className="room-op-card__title">
          <span className="room-op-card__number">{room.number}</span>
          {/* Persistent, subtle cue that the header opens the details drawer —
           * touch has no hover. Decorative (the aria-label carries meaning); it
           * is NOT a 4th action button. */}
          <Icon icon={Eye} size="sm" className="room-op-card__open-cue" />
        </span>
        <span className="room-op-card__type">{room.room_type_name}</span>
      </button>

      {/* 2) Badges — occupancy + operational, text + icon + colour. */}
      <div className="room-op-card__badges">
        <Badge tone={occupancyTone(room.occupancy_status)}>
          <Icon icon={occupancyIcon(room.occupancy_status)} size="sm" />
          {t.rooms.occupancy[room.occupancy_status]}
        </Badge>
        <Badge tone={operationalTone(room.operational_status)}>
          <Icon icon={operationalIcon(room.operational_status)} size="sm" />
          {b.status[room.operational_status]}
        </Badge>
      </div>

      {/* 3) Core facts — floor · capacity · price. */}
      <dl className="room-op-card__facts">
        <div className="room-op-card__fact">
          <dt>{b.detailFloor}</dt>
          <dd>{room.floor_name}</dd>
        </div>
        <div className="room-op-card__fact">
          <dt>{b.capacity}</dt>
          <dd>
            {room.base_capacity}–{room.max_capacity}
          </dd>
        </div>
        {room.base_rate ? (
          <div className="room-op-card__fact">
            <dt>{b.pricePerNight}</dt>
            <dd>{room.base_rate}</dd>
          </div>
        ) : null}
      </dl>

      {/* 4) Status — resident / upcoming / status line. */}
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
