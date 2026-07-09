"use client";

import { Building2 } from "lucide-react";

import { Icon } from "@/components/ui";
import type { RoomBoardFloor } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { cx } from "@/lib/utils";

/** Clickable floor cards (owner spec): each shows the floor's own counts and
 * availability rate; clicking toggles the floor filter (combinable with the
 * status filter above). */
export function FloorSummaryCards({
  floors,
  active,
  onToggle,
}: {
  floors: RoomBoardFloor[];
  active: number | null;
  onToggle: (id: number | null) => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;

  if (floors.length === 0) return null;

  return (
    <div className="floor-cards" role="group" aria-label={b.floors}>
      {floors.map((floor) => (
        <button
          key={floor.id}
          type="button"
          className={cx("floor-card", active === floor.id && "floor-card--active")}
          aria-pressed={active === floor.id}
          onClick={() => onToggle(active === floor.id ? null : floor.id)}
        >
          <span className="floor-card__head">
            <span className="floor-card__icon">
              <Icon icon={Building2} size="sm" />
            </span>
            <span className="floor-card__name">
              {floor.name}
              {floor.number ? ` · ${floor.number}` : ""}
            </span>
            <span className="floor-card__rate">
              {b.availabilityRate.replace("{rate}", String(floor.availability_rate))}
            </span>
          </span>
          <span className="floor-card__counts">
            <span className="floor-chip">{b.totalShort}: {floor.total}</span>
            <span className="floor-chip floor-chip--success">{b.status.available}: {floor.available}</span>
            <span className="floor-chip floor-chip--info">{b.status.occupied}: {floor.occupied}</span>
            <span className="floor-chip floor-chip--warning">{b.status.reserved}: {floor.reserved}</span>
            {floor.dirty > 0 ? (
              <span className="floor-chip floor-chip--warning">{b.status.dirty}: {floor.dirty}</span>
            ) : null}
            {floor.cleaning > 0 ? (
              <span className="floor-chip floor-chip--info">{b.status.cleaning}: {floor.cleaning}</span>
            ) : null}
            {floor.maintenance > 0 ? (
              <span className="floor-chip floor-chip--danger">{b.status.maintenance}: {floor.maintenance}</span>
            ) : null}
            {floor.out_of_service > 0 ? (
              <span className="floor-chip">{b.status.out_of_service}: {floor.out_of_service}</span>
            ) : null}
          </span>
        </button>
      ))}
    </div>
  );
}
