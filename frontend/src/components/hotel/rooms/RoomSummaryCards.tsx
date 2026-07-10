"use client";

import {
  AlertTriangle,
  BedDouble,
  Brush,
  CalendarClock,
  DoorOpen,
  Sparkles,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import { Icon } from "@/components/ui";
import type { RoomBoardCounts } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { cx } from "@/lib/utils";

/** Clickable status filters — `attention` and `maintenance_oos` are
 * composite buckets (display-only, computed client-side). */
export type BoardStatusFilter =
  | "available"
  | "occupied"
  | "reserved"
  | "dirty"
  | "cleaning"
  | "maintenance"
  | "out_of_service"
  | "maintenance_oos"
  | "attention";

const CARDS: Array<{
  key: BoardStatusFilter;
  labelKey: "availableForBooking" | "occupiedNow" | "reserved" | "dirty" | "cleaning" | "maintOos" | "attention";
  captionKey: string;
  icon: LucideIcon;
  tone: string;
}> = [
  { key: "available", labelKey: "availableForBooking", captionKey: "captionAvailable", icon: DoorOpen, tone: "success" },
  { key: "occupied", labelKey: "occupiedNow", captionKey: "captionOccupied", icon: Users, tone: "info" },
  { key: "reserved", labelKey: "reserved", captionKey: "captionReserved", icon: CalendarClock, tone: "warning" },
  { key: "dirty", labelKey: "dirty", captionKey: "captionDirty", icon: Sparkles, tone: "warning" },
  { key: "cleaning", labelKey: "cleaning", captionKey: "captionCleaning", icon: Brush, tone: "info" },
  { key: "maintenance_oos", labelKey: "maintOos", captionKey: "captionMaintOos", icon: Wrench, tone: "neutral" },
  { key: "attention", labelKey: "attention", captionKey: "captionAttention", icon: AlertTriangle, tone: "danger" },
];

function cardValue(summary: RoomBoardCounts, key: BoardStatusFilter): number {
  if (key === "maintenance_oos") {
    return summary.maintenance + summary.out_of_service;
  }
  return summary[key as keyof RoomBoardCounts];
}

/** Top summary row (owner spec): total + one CLICKABLE card per bucket —
 * big number, clear label, small caption; clicking filters the grid,
 * clicking again clears. Calm palette, active card clearly selected. */
export function RoomSummaryCards({
  summary,
  active,
  onToggle,
}: {
  summary: RoomBoardCounts;
  active: BoardStatusFilter | null;
  onToggle: (key: BoardStatusFilter | null) => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  const labels: Record<string, string> = {
    availableForBooking: b.availableForBooking,
    occupiedNow: b.occupiedNow,
    reserved: b.status.reserved,
    dirty: b.status.dirty,
    cleaning: b.status.cleaning,
    maintOos: b.maintOos,
    attention: b.status.attention,
  };
  const captions = b.captions as Record<string, string>;

  return (
    <div className="board-stats" role="group" aria-label={b.tabTitle}>
      <button
        type="button"
        className={cx("board-stat", active === null && "board-stat--active")}
        onClick={() => onToggle(null)}
      >
        <span className="board-stat__icon board-stat__icon--primary">
          <Icon icon={BedDouble} size="md" />
        </span>
        <span className="board-stat__value">{summary.total}</span>
        <span className="board-stat__label">{b.totalRooms}</span>
        <span className="board-stat__caption">{captions.captionTotal}</span>
      </button>
      {CARDS.map((card) => (
        <button
          key={card.key}
          type="button"
          className={cx(
            "board-stat",
            active === card.key && "board-stat--active",
          )}
          aria-pressed={active === card.key}
          onClick={() => onToggle(active === card.key ? null : card.key)}
        >
          <span className={cx("board-stat__icon", `board-stat__icon--${card.tone}`)}>
            <Icon icon={card.icon} size="md" />
          </span>
          <span className="board-stat__value">{cardValue(summary, card.key)}</span>
          <span className="board-stat__label">{labels[card.labelKey]}</span>
          <span className="board-stat__caption">{captions[card.captionKey]}</span>
        </button>
      ))}
    </div>
  );
}
