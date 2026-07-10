"use client";

import { useEffect, useState } from "react";
import {
  CalendarCheck,
  CalendarPlus,
  CalendarX2,
  CheckCircle2,
  Clock3,
  Globe,
  CalendarRange,
  type LucideIcon,
} from "lucide-react";

import { Icon } from "@/components/ui";
import { listReservations } from "@/lib/api/reservations";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { cx } from "@/lib/utils";

import {
  RESERVATION_VIEWS,
  VIEW_PARAMS,
  type ReservationView,
} from "./reservationViews";

const ICONS: Record<ReservationView, LucideIcon> = {
  all: CalendarCheck,
  today: CalendarPlus,
  website: Globe,
  future: CalendarRange,
  pending: Clock3,
  confirmed: CheckCircle2,
  closed: CalendarX2,
};

const TONES: Record<ReservationView, string> = {
  all: "primary",
  today: "info",
  website: "info",
  future: "neutral",
  pending: "warning",
  confirmed: "success",
  closed: "danger",
};

/** Clickable counters over the seven reservation views (owner reorg) —
 * clicking a card activates its tab. Counts come from seven page_size=1
 * list queries (the paginator count), so they always match the tabs. */
export function ReservationSummaryCards({
  active,
  onSelect,
  reloadKey,
}: {
  active: ReservationView;
  onSelect: (view: ReservationView) => void;
  reloadKey: number;
}) {
  const { t } = useI18n();
  const v = t.reservations.views;
  const [counts, setCounts] = useState<Partial<Record<ReservationView, number>>>({});

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      RESERVATION_VIEWS.map((view) =>
        listReservations({ ...VIEW_PARAMS[view], page_size: 1 })
          .then((data) => [view, data.count] as const)
          .catch(() => [view, undefined] as const),
      ),
    ).then((entries) => {
      if (cancelled) return;
      const next: Partial<Record<ReservationView, number>> = {};
      for (const [view, count] of entries) {
        if (count !== undefined) next[view] = count;
      }
      setCounts(next);
    });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  return (
    <div className="board-stats" role="group" aria-label={t.reservations.title}>
      {RESERVATION_VIEWS.map((view) => (
        <button
          key={view}
          type="button"
          className={cx("board-stat", active === view && "board-stat--active")}
          aria-pressed={active === view}
          onClick={() => onSelect(view)}
        >
          <span className={cx("board-stat__icon", `board-stat__icon--${TONES[view]}`)}>
            <Icon icon={ICONS[view]} size="md" />
          </span>
          <span className="board-stat__value">{counts[view] ?? "…"}</span>
          <span className="board-stat__label">{v.tabs[view]}</span>
        </button>
      ))}
    </div>
  );
}
