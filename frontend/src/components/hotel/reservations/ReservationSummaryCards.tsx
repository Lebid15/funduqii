"use client";

import {
  CalendarCheck,
  CalendarX2,
  CheckCircle2,
  Clock3,
  type LucideIcon,
} from "lucide-react";

import { Icon } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { cx } from "@/lib/utils";

/** The status a summary card maps onto — "" is the Total card (clears status). */
export type StatusCard = "" | "confirmed" | "held" | "cancelled";

export interface ReservationCounts {
  total?: number;
  confirmed?: number;
  held?: number;
  cancelled?: number;
}

const CARDS: Array<{
  key: StatusCard;
  countKey: keyof ReservationCounts;
  labelKey: "total" | "confirmed" | "pending" | "cancelled";
  captionKey: "totalCaption" | "confirmedCaption" | "pendingCaption" | "cancelledCaption";
  icon: LucideIcon;
  tone: string;
}> = [
  {
    key: "",
    countKey: "total",
    labelKey: "total",
    captionKey: "totalCaption",
    icon: CalendarCheck,
    tone: "primary",
  },
  {
    key: "confirmed",
    countKey: "confirmed",
    labelKey: "confirmed",
    captionKey: "confirmedCaption",
    icon: CheckCircle2,
    tone: "success",
  },
  {
    key: "held",
    countKey: "held",
    labelKey: "pending",
    captionKey: "pendingCaption",
    icon: Clock3,
    tone: "warning",
  },
  {
    key: "cancelled",
    countKey: "cancelled",
    labelKey: "cancelled",
    captionKey: "cancelledCaption",
    icon: CalendarX2,
    tone: "danger",
  },
];

/** EXACTLY four clickable summary cards (reservations rework): Total /
 * Confirmed / Pending / Cancelled, driven by the real hotel-scoped overview
 * counts. Each card is a status quick-filter; the active card highlights the
 * active filter, and clicking Total (or the active card) clears it. */
export function ReservationSummaryCards({
  counts,
  active,
  onSelect,
}: {
  counts: ReservationCounts;
  /** The active status filter, or null when a non-card status (e.g. expired)
   * is applied — then no card (not even Total) is highlighted. */
  active: StatusCard | null;
  onSelect: (status: StatusCard) => void;
}) {
  const { t } = useI18n();
  const c = t.reservations.cards;

  return (
    <div className="board-stats board-stats--4" role="group" aria-label={c.groupLabel}>
      {CARDS.map((card) => {
        const isActive = active === card.key;
        const value = counts[card.countKey];
        return (
          <button
            key={card.labelKey}
            type="button"
            className={cx("board-stat", isActive && "board-stat--active")}
            aria-pressed={isActive}
            onClick={() => onSelect(card.key)}
          >
            <span className={cx("board-stat__icon", `board-stat__icon--${card.tone}`)}>
              <Icon icon={card.icon} size="md" />
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
