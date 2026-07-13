"use client";

import { useState } from "react";
import { Building2, ChevronDown, Plus } from "lucide-react";

import { Button, Icon } from "@/components/ui";
import type { RoomBoardFloor, RoomBoardRoom } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { cx } from "@/lib/utils";

import { RoomOperationalCard } from "./RoomOperationalCard";

/** Rooms grouped by floor in COLLAPSIBLE sections (owner spec): each floor
 * name/number appears once with a compact counter folded into the header, then
 * a grid of room cards. A truly empty floor shows a small "add room here"
 * action (create modal, floor pre-filled). Floors whose rooms are all filtered
 * out are hidden so the view stays calm. */
export function RoomFloorGrid({
  floors,
  rooms,
  canCreate,
  hasFilters,
  onDetails,
  onEdit,
  onAddRoomToFloor,
}: {
  floors: RoomBoardFloor[];
  rooms: RoomBoardRoom[];
  canCreate: boolean;
  /** When filters are active, empty floors are hidden (their add-prompt is noise). */
  hasFilters: boolean;
  onDetails: (room: RoomBoardRoom) => void;
  onEdit: (room: RoomBoardRoom) => void;
  onAddRoomToFloor: (floorId: number) => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  const p = t.rooms.page;
  const [collapsed, setCollapsed] = useState<ReadonlySet<number>>(new Set());

  function toggle(id: number) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="stack">
      {floors.map((floor) => {
        const floorRooms = rooms.filter((room) => room.floor === floor.id);
        const isEmpty = floor.total === 0;
        // A non-empty floor with nothing matching the active filters is hidden.
        if (floorRooms.length === 0 && !isEmpty) return null;
        // While filtering, a genuinely-empty floor's "add here" prompt is noise.
        if (isEmpty && hasFilters) return null;

        const isCollapsed = collapsed.has(floor.id);
        const bodyId = `floor-body-${floor.id}`;

        return (
          <section key={floor.id} className="floor-section" aria-label={floor.name}>
            <div className="floor-section__head">
              <button
                type="button"
                className="floor-section__toggle"
                aria-expanded={!isCollapsed}
                aria-controls={bodyId}
                onClick={() => toggle(floor.id)}
              >
                <Icon
                  icon={ChevronDown}
                  size="sm"
                  className={cx(
                    "floor-section__chevron",
                    isCollapsed && "floor-section__chevron--collapsed",
                  )}
                />
                <span className="floor-section__title">
                  <Icon icon={Building2} size="sm" />
                  {floor.name}
                  {floor.number ? ` · ${floor.number}` : ""}
                </span>
              </button>
              <span className="floor-section__summary">
                <span>{b.totalShort}: {floor.total}</span>
                <span className="floor-chip floor-chip--success">
                  {p.availableNowShort}: {floor.available_now}
                </span>
                <span className="floor-chip floor-chip--info">
                  {b.status.occupied}: {floor.occupied}
                </span>
                {floor.attention > 0 ? (
                  <span className="floor-chip floor-chip--danger">
                    {b.status.attention}: {floor.attention}
                  </span>
                ) : null}
              </span>
            </div>

            {/* The controlled node stays in the DOM (hidden when collapsed) so
             * aria-controls always resolves; heavy children are skipped. */}
            <div id={bodyId} hidden={isCollapsed}>
              {isCollapsed ? null : isEmpty ? (
                <div className="floor-section__empty">
                  <span className="muted">{p.floorEmpty}</span>
                  {canCreate ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={Plus}
                      onClick={() => onAddRoomToFloor(floor.id)}
                    >
                      {p.addRoomToFloor}
                    </Button>
                  ) : null}
                </div>
              ) : (
                <div className="room-op-grid">
                  {floorRooms.map((room) => (
                    <RoomOperationalCard
                      key={room.id}
                      room={room}
                      onDetails={onDetails}
                      onEdit={onEdit}
                    />
                  ))}
                </div>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
