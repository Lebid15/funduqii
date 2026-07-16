"use client";

import {
  AlertTriangle,
  BedDouble,
  DoorOpen,
  Users,
  type LucideIcon,
} from "lucide-react";

import { SmartStatCard, type SmartStatTone } from "@/components/ui";
import type { RoomBoardCounts } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

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
  tone: SmartStatTone;
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
 * Any other metric lives in the filter row, never here. Rendered via the central
 * {@link SmartStatCard}; the grid container + Total-clear logic stay here. */
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
      <SmartStatCard
        icon={BedDouble}
        tone="primary"
        value={summary.total}
        label={c.total}
        caption={c.totalCaption}
        active={active === null}
        onClick={() => onSelect("total")}
      />
      {CARDS.map((card) => (
        <SmartStatCard
          key={card.key}
          icon={card.icon}
          tone={card.tone}
          value={summary[card.countKey]}
          label={c[card.labelKey]}
          caption={c[card.captionKey]}
          active={active === card.key}
          onClick={() => onSelect(card.key)}
        />
      ))}
    </div>
  );
}
