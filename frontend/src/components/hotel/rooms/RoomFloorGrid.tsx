"use client";

import { Building2 } from "lucide-react";

import { Icon } from "@/components/ui";
import type { RoomBoardFloor, RoomBoardRoom } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { RoomOperationalCard } from "./RoomOperationalCard";

/** Rooms grouped by floor (owner spec): a heading per floor with its own
 * mini summary, then a grid of room cards. Floors with no rooms after
 * filtering are skipped — the parent shows the empty state when ALL are. */
export function RoomFloorGrid({
  floors,
  rooms,
  onDetails,
  onChangeStatus,
}: {
  floors: RoomBoardFloor[];
  rooms: RoomBoardRoom[];
  onDetails: (room: RoomBoardRoom) => void;
  onChangeStatus: (room: RoomBoardRoom) => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;

  return (
    <div className="stack">
      {floors.map((floor) => {
        const floorRooms = rooms.filter((room) => room.floor === floor.id);
        if (floorRooms.length === 0) return null;
        return (
          <section key={floor.id} className="floor-section" aria-label={floor.name}>
            <div className="floor-section__head">
              <span className="floor-section__title">
                <Icon icon={Building2} size="sm" />
                {floor.name}
                {floor.number ? ` · ${floor.number}` : ""}
              </span>
              <span className="floor-section__summary">
                <span>{b.totalShort}: {floor.total}</span>
                <span>{b.status.available}: {floor.available}</span>
                <span>{b.status.occupied}: {floor.occupied}</span>
                <span>{b.status.reserved}: {floor.reserved}</span>
                <span>{b.status.dirty}: {floor.dirty}</span>
                <span>{b.status.maintenance}: {floor.maintenance}</span>
              </span>
            </div>
            <div className="room-op-grid">
              {floorRooms.map((room) => (
                <RoomOperationalCard
                  key={room.id}
                  room={room}
                  onDetails={onDetails}
                  onChangeStatus={onChangeStatus}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
