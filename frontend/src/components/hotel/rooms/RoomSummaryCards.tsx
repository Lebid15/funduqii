"use client";

import {
  AlertTriangle,
  BedDouble,
  Brush,
  CalendarClock,
  CircleSlash,
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

/** The clickable status filters — `attention` is the composite bucket. */
export type BoardStatusFilter =
  | "available"
  | "occupied"
  | "reserved"
  | "dirty"
  | "cleaning"
  | "maintenance"
  | "out_of_service"
  | "attention";

const CARDS: Array<{
  key: BoardStatusFilter;
  icon: LucideIcon;
  tone: string;
}> = [
  { key: "available", icon: DoorOpen, tone: "success" },
  { key: "occupied", icon: Users, tone: "info" },
  { key: "reserved", icon: CalendarClock, tone: "warning" },
  { key: "dirty", icon: Sparkles, tone: "warning" },
  { key: "cleaning", icon: Brush, tone: "info" },
  { key: "maintenance", icon: Wrench, tone: "danger" },
  { key: "out_of_service", icon: CircleSlash, tone: "neutral" },
  { key: "attention", icon: AlertTriangle, tone: "danger" },
];

/** Top summary row (owner spec): total + one CLICKABLE card per display
 * status — clicking filters the grid, clicking again clears the filter. */
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
          <span className="board-stat__value">{summary[card.key]}</span>
          <span className="board-stat__label">{b.status[card.key]}</span>
        </button>
      ))}
    </div>
  );
}
