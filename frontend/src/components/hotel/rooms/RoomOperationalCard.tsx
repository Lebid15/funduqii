"use client";

import Link from "next/link";
import { Info, RefreshCw } from "lucide-react";

import { Badge, Button, Icon } from "@/components/ui";
import type { RoomBoardRoom } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { cx } from "@/lib/utils";

import { buildRoomLinks, displayStatusTone } from "./boardShared";

/** One room on the operational board (owner spec): big number + status badge
 * + colour cue, the essentials, the status-specific operational line, and
 * status-appropriate permission-aware actions (max two links on the card —
 * everything else lives in the details drawer). */
export function RoomOperationalCard({
  room,
  onDetails,
  onChangeStatus,
}: {
  room: RoomBoardRoom;
  onDetails: (room: RoomBoardRoom) => void;
  onChangeStatus: (room: RoomBoardRoom) => void;
}) {
  const { t, locale } = useI18n();
  const access = useHotelAccess();
  const b = t.rooms.board;
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));

  const links = buildRoomLinks(room, t, can).slice(0, 2);
  const canStatus =
    room.display_status !== "occupied" &&
    room.display_status !== "reserved" &&
    can("rooms.status_update");

  return (
    <article className={cx("room-op-card", `room-op-card--${room.display_status}`)}>
      <div className="room-op-card__head">
        <span className="room-op-card__number">{room.number}</span>
        <Badge tone={displayStatusTone(room.display_status)}>
          {b.status[room.display_status]}
        </Badge>
      </div>

      <div className="room-op-card__meta">
        <span>
          {room.room_type_name} · {room.floor_name}
        </span>
        <span>
          {b.capacity}: {room.base_capacity}–{room.max_capacity}
          {room.base_rate ? ` · ${b.baseRate}: ${room.base_rate}` : ""}
        </span>
        {room.display_name ? <span>{room.display_name}</span> : null}
      </div>

      <OperationalLine room={room} locale={locale} />

      <div className="room-op-card__actions">
        {links.map((link) => (
          <Link key={link.key} href={link.href} className="btn btn--secondary btn--sm">
            <Icon icon={link.icon} size="sm" />
            {link.label}
          </Link>
        ))}
        {canStatus ? (
          <Button variant="ghost" size="sm" icon={RefreshCw} onClick={() => onChangeStatus(room)}>
            {b.changeStatus}
          </Button>
        ) : null}
        <Button variant="ghost" size="sm" icon={Info} onClick={() => onDetails(room)}>
          {b.details}
        </Button>
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
        <strong>{b.currentGuest}</strong>
        <span>{room.current_stay.guest_name}</span>
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
        <strong>{b.upcomingReservation}</strong>
        <span>{room.next_reservation.guest_name}</span>
        <span className="muted">
          {formatDate(room.next_reservation.check_in_date, locale)} ←{" "}
          {formatDate(room.next_reservation.check_out_date, locale)} ·{" "}
          {room.next_reservation.reservation_number}
        </span>
      </div>
    );
  }
  if (room.display_status === "available") {
    return (
      <div className="room-op-card__line">
        <span className="muted">{b.readyToBook}</span>
      </div>
    );
  }
  // dirty / cleaning / maintenance / out_of_service / archived
  return (
    <div className="room-op-card__line">
      {room.status_note ? <span>{room.status_note}</span> : null}
      {room.status_changed_at ? (
        <span className="muted">
          {b.lastStatusChange}: {formatDate(room.status_changed_at, locale)}
        </span>
      ) : null}
      {!room.status_note && !room.status_changed_at ? (
        <span className="muted">{b.status[room.display_status]}</span>
      ) : null}
    </div>
  );
}
