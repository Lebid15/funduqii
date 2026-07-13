"use client";

import {
  CalendarCheck,
  CalendarX2,
  CheckCircle2,
  Clock3,
  Globe,
  type LucideIcon,
} from "lucide-react";

import { Icon } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { cx } from "@/lib/utils";

/** Which summary card is active. "" is the Total card (clears status AND
 * source); "website" is a SOURCE card (source=public_website), not a status. */
export type SummaryCardKey = "" | "confirmed" | "held" | "cancelled" | "website";

export interface ReservationCounts {
  total?: number;
  confirmed?: number;
  held?: number;
  cancelled?: number;
  /** SOURCE subset — public_website reservations, already inside the statuses. */
  website?: number;
}

interface CardDef {
  key: SummaryCardKey;
  /** A status card filters by status; a source card filters by source. */
  dimension: "status" | "source";
  countKey: keyof ReservationCounts;
  labelKey: "total" | "confirmed" | "pending" | "cancelled" | "website";
  captionKey:
    | "totalCaption"
    | "confirmedCaption"
    | "pendingCaption"
    | "cancelledCaption"
    | "websiteCaption";
  icon: LucideIcon;
  tone: string;
}

const CARDS: CardDef[] = [
  {
    key: "",
    dimension: "status",
    countKey: "total",
    labelKey: "total",
    captionKey: "totalCaption",
    icon: CalendarCheck,
    tone: "primary",
  },
  {
    key: "confirmed",
    dimension: "status",
    countKey: "confirmed",
    labelKey: "confirmed",
    captionKey: "confirmedCaption",
    icon: CheckCircle2,
    tone: "success",
  },
  {
    key: "held",
    dimension: "status",
    countKey: "held",
    labelKey: "pending",
    captionKey: "pendingCaption",
    icon: Clock3,
    tone: "warning",
  },
  {
    key: "cancelled",
    dimension: "status",
    countKey: "cancelled",
    labelKey: "cancelled",
    captionKey: "cancelledCaption",
    icon: CalendarX2,
    tone: "danger",
  },
  {
    key: "website",
    dimension: "source",
    countKey: "website",
    labelKey: "website",
    captionKey: "websiteCaption",
    icon: Globe,
    tone: "info",
  },
];

/** EXACTLY five clickable summary cards (reservations rework): Total /
 * Confirmed / Pending / Cancelled are STATUS quick-filters; Website is a SOURCE
 * quick-filter (public_website). The Website count is a subset of Total already
 * distributed across the status counts — it is NEVER summed into the status
 * math, which the caption + the group hint make explicit. Each card highlights
 * with text/icon/ring (never colour alone). Clicking Total (or the active card)
 * clears both status and source. */
export function ReservationSummaryCards({
  counts,
  active,
  onSelect,
}: {
  counts: ReservationCounts;
  /** The active card key, or null when a non-card status (e.g. expired) or a
   * non-website source is applied — then no card is highlighted. */
  active: SummaryCardKey | null;
  onSelect: (card: SummaryCardKey) => void;
}) {
  const { t } = useI18n();
  const c = t.reservations.cards;

  return (
    <div className="stack-tight">
      <div className="board-stats board-stats--5" role="group" aria-label={c.groupLabel}>
        {CARDS.map((card) => {
          const isActive = active === card.key;
          const value = counts[card.countKey];
          const isSource = card.dimension === "source";
          return (
            <button
              key={card.labelKey}
              type="button"
              className={cx(
                "board-stat",
                isSource && "board-stat--source",
                isActive && "board-stat--active",
              )}
              aria-pressed={isActive}
              onClick={() => onSelect(card.key)}
            >
              <span className="board-stat__head">
                <span className={cx("board-stat__icon", `board-stat__icon--${card.tone}`)}>
                  <Icon icon={card.icon} size="md" />
                </span>
                {isSource ? (
                  <span className="board-stat__tag">{c.sourceTag}</span>
                ) : null}
              </span>
              <span className="board-stat__value">{value ?? "…"}</span>
              <span className="board-stat__label">{c[card.labelKey]}</span>
              <span className="board-stat__caption">{c[card.captionKey]}</span>
            </button>
          );
        })}
      </div>
      <p className="board-stats__hint muted small">{c.sourceHint}</p>
    </div>
  );
}
