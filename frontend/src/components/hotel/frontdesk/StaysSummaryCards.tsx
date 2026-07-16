"use client";

import {
  AlertTriangle,
  BedDouble,
  CalendarClock,
  DoorOpen,
  LogIn,
  LogOut,
  type LucideIcon,
} from "lucide-react";

import { Icon } from "@/components/ui";
import type { StaysOverview } from "@/lib/api/stays";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { cx } from "@/lib/utils";

/** Which operational summary card is active (applies its filter to the list). */
export type OpsCardKey =
  | "arriving"
  | "awaiting"
  | "checked_in_today"
  | "residents"
  | "departing"
  | "attention";

type CountKey = Exclude<keyof StaysOverview, "business_date">;
type LabelKey =
  | "arriving"
  | "awaiting"
  | "checkedInToday"
  | "residents"
  | "departing"
  | "attention";
type CaptionKey =
  | "arrivingCaption"
  | "awaitingCaption"
  | "checkedInTodayCaption"
  | "residentsCaption"
  | "departingCaption"
  | "attentionCaption";

interface CardDef {
  key: OpsCardKey;
  countKey: CountKey;
  labelKey: LabelKey;
  captionKey: CaptionKey;
  icon: LucideIcon;
  tone: string;
}

const CARDS: CardDef[] = [
  { key: "arriving", countKey: "arriving_today", labelKey: "arriving", captionKey: "arrivingCaption", icon: CalendarClock, tone: "primary" },
  { key: "awaiting", countKey: "awaiting_check_in", labelKey: "awaiting", captionKey: "awaitingCaption", icon: LogIn, tone: "info" },
  { key: "checked_in_today", countKey: "checked_in_today", labelKey: "checkedInToday", captionKey: "checkedInTodayCaption", icon: DoorOpen, tone: "success" },
  { key: "residents", countKey: "current_residents", labelKey: "residents", captionKey: "residentsCaption", icon: BedDouble, tone: "primary" },
  { key: "departing", countKey: "departing_today", labelKey: "departing", captionKey: "departingCaption", icon: LogOut, tone: "warning" },
  { key: "attention", countKey: "needs_attention", labelKey: "attention", captionKey: "attentionCaption", icon: AlertTriangle, tone: "danger" },
];

/**
 * The six smart cards for the operations page (§6). The numbers come from the
 * backend overview; clicking a card applies its filter to the list. Color is
 * never the only signal — each card carries an icon + label + caption, and the
 * active card is marked with ``aria-pressed`` + a visible ring.
 */
export function StaysSummaryCards({
  overview,
  active,
  onSelect,
}: {
  overview: StaysOverview | null;
  active: OpsCardKey | null;
  onSelect: (card: OpsCardKey) => void;
}) {
  const { t } = useI18n();
  const c = t.frontDesk.cards;

  return (
    <div className="board-stats" role="group" aria-label={c.groupLabel}>
      {CARDS.map((card) => {
        const isActive = active === card.key;
        const value = overview ? overview[card.countKey] : null;
        return (
          <button
            key={card.key}
            type="button"
            className={cx("board-stat", isActive && "board-stat--active")}
            aria-pressed={isActive}
            onClick={() => onSelect(card.key)}
          >
            <span className="board-stat__head">
              <span
                className={cx(
                  "board-stat__icon",
                  `board-stat__icon--${card.tone}`,
                )}
              >
                <Icon icon={card.icon} size="md" />
              </span>
            </span>
            <span className="board-stat__value">{value ?? "…"}</span>
            <span className="board-stat__label">{c[card.labelKey]}</span>
            <span className="board-stat__caption">{c[card.captionKey]}</span>
          </button>
        );
      })}
    </div>
  );
}
