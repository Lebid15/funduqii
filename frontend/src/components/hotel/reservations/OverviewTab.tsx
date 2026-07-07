"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CalendarCheck,
  CalendarClock,
  CalendarX,
  ClipboardList,
  PlaneLanding,
  PlaneTakeoff,
} from "lucide-react";

import { Badge, Card, ErrorState, LoadingState, StatCard } from "@/components/ui";
import { getReservationOverview } from "@/lib/api/reservations";
import { messageForError } from "@/lib/api/errors";
import type { Reservation, ReservationOverview } from "@/lib/api/types";
import { formatDate, reservationStatusTone } from "@/lib/format";
import { reservationStatusLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** Reservation counts plus upcoming arrivals/departures (view only — no
 * check-in/check-out actions in Phase 6). */
export function OverviewTab() {
  const { t, locale } = useI18n();
  const [data, setData] = useState<ReservationOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getReservationOverview());
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingState label={t.common.loading} />;
  if (error) {
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={error}
        retryLabel={t.common.retry}
        onRetry={load}
      />
    );
  }

  return (
    <div className="stack">
      <section className="stat-grid">
        <StatCard label={t.reservations.overview.total} value={data?.total ?? "—"} icon={ClipboardList} tone="primary" />
        <StatCard label={t.reservations.overview.confirmed} value={data?.confirmed ?? "—"} icon={CalendarCheck} tone="success" />
        <StatCard label={t.reservations.overview.held} value={data?.held ?? "—"} icon={CalendarClock} tone="warning" />
        <StatCard label={t.reservations.overview.cancelled} value={data?.cancelled ?? "—"} icon={CalendarX} tone="neutral" />
      </section>

      <div className="two-col">
        <ArrivalsCard
          title={t.reservations.overview.arrivals}
          icon={PlaneLanding}
          empty={t.reservations.overview.arrivalsEmpty}
          rows={data?.arrivals ?? []}
          dateOf={(r) => r.check_in_date}
          locale={locale}
        />
        <ArrivalsCard
          title={t.reservations.overview.departures}
          icon={PlaneTakeoff}
          empty={t.reservations.overview.departuresEmpty}
          rows={data?.departures ?? []}
          dateOf={(r) => r.check_out_date}
          locale={locale}
        />
      </div>
    </div>
  );
}

function ArrivalsCard({
  title,
  icon: IconCmp,
  empty,
  rows,
  dateOf,
  locale,
}: {
  title: string;
  icon: typeof PlaneLanding;
  empty: string;
  rows: Reservation[];
  dateOf: (r: Reservation) => string;
  locale: Parameters<typeof formatDate>[1];
}) {
  const { t } = useI18n();
  return (
    <Card>
      <div className="mini-list__head">
        <IconCmp size={18} aria-hidden />
        <h3>{title}</h3>
      </div>
      {rows.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <ul className="mini-list">
          {rows.map((r) => (
            <li key={r.id} className="mini-list__row">
              <span className="mini-list__main">
                <strong>{r.reservation_number}</strong>
                <span className="muted">{r.primary_guest_name}</span>
              </span>
              <span className="mini-list__side">
                <span>{formatDate(dateOf(r), locale)}</span>
                <Badge tone={reservationStatusTone(r.status)}>
                  {reservationStatusLabel(r.status, t)}
                </Badge>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
