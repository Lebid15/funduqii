"use client";

import {
  AlertTriangle,
  BedDouble,
  DoorOpen,
  Users,
  type LucideIcon,
} from "lucide-react";

import { Icon } from "@/components/ui";
import type { RoomBoardCounts } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { cx } from "@/lib/utils";

/** The three CLICKABLE quick-filter cards (Total is the fourth card and
 * clears them). Occupancy vs. operational axes stay independent — these map
 * onto the board's underlying filter state. */
export type BoardCardKey = "available" | "occupied" | "attention";

const CARDS: Array<{
  key: BoardCardKey;
  countKey: keyof RoomBoardCounts;
  labelKey: "availableNow" | "occupiedNow" | "needsAction";
  captionKey: "availableNowCaption" | "occupiedNowCaption" | "needsActionCaption";
  icon: LucideIcon;
  tone: string;
}> = [
  {
    key: "available",
    countKey: "available_now",
    labelKey: "availableNow",
    captionKey: "availableNowCaption",
    icon: DoorOpen,
    tone: "success",
  },
  {
    key: "occupied",
    countKey: "occupied",
    labelKey: "occupiedNow",
    captionKey: "occupiedNowCaption",
    icon: Users,
    tone: "info",
  },
  {
    key: "attention",
    countKey: "attention",
    labelKey: "needsAction",
    captionKey: "needsActionCaption",
    icon: AlertTriangle,
    tone: "danger",
  },
];

/** EXACTLY four summary cards (owner spec): Total / Available now / Occupied
 * now / Needs action. Each is a calm, clickable filter; clicking again clears.
 * Any other metric lives in the filter row, never here. */
export function RoomSummaryCards({
  summary,
  active,
  onSelect,
}: {
  summary: RoomBoardCounts;
  active: BoardCardKey | null;
  onSelect: (key: BoardCardKey | "total") => void;
}) {
  const { t } = useI18n();
  const c = t.rooms.cards;

  return (
    <div className="board-stats board-stats--4" role="group" aria-label={c.groupLabel}>
      <button
        type="button"
        className={cx("board-stat", active === null && "board-stat--active")}
        aria-pressed={active === null}
        onClick={() => onSelect("total")}
      >
        <span className="board-stat__icon board-stat__icon--primary">
          <Icon icon={BedDouble} size="md" />
        </span>
        <span className="board-stat__value">{summary.total}</span>
        <span className="board-stat__label">{c.total}</span>
        <span className="board-stat__caption">{c.totalCaption}</span>
      </button>
      {CARDS.map((card) => (
        <button
          key={card.key}
          type="button"
          className={cx("board-stat", active === card.key && "board-stat--active")}
          aria-pressed={active === card.key}
          onClick={() => onSelect(card.key)}
        >
          <span className={cx("board-stat__icon", `board-stat__icon--${card.tone}`)}>
            <Icon icon={card.icon} size="md" />
          </span>
          <span className="board-stat__value">{summary[card.countKey]}</span>
          <span className="board-stat__label">{c[card.labelKey]}</span>
          <span className="board-stat__caption">{c[card.captionKey]}</span>
        </button>
      ))}
    </div>
  );
}
