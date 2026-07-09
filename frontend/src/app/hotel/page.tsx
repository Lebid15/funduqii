"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BedDouble,
  CalendarCheck,
  ClipboardList,
  DoorOpen,
  LogIn,
  LogOut,
  Sparkles,
  Users,
  UtensilsCrossed,
  Wallet,
  Wrench,
} from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import {
  Alert,
  Icon,
  PageHeader,
  SectionHeader,
  Skeleton,
  StatCard,
} from "@/components/ui";
import {
  hotelNavItems,
  visibleHotelNavItems,
} from "@/components/layout/hotelNav";
import { getOverviewReport } from "@/lib/api/reports";
import { messageForError } from "@/lib/api/errors";
import type { OverviewReport } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

/**
 * Hotel dashboard (owner spec): a FAST daily-management screen — today's
 * numbers on top, permission-aware shortcuts to every section below. No big
 * tables, no BI, no new backend: the stats are ONE call to the existing
 * Phase 13 overview report scoped to today, and the shortcuts reuse the
 * sidebar's official nav config and Phase 11 visibility filter verbatim.
 */
export default function HotelDashboardPage() {
  const { t } = useI18n();
  const access = useHotelAccess();

  // Stats need reports.view (the overview API enforces it server-side); the
  // shortcuts section below still serves members without it.
  const canStats =
    access !== null && !access.loading && access.can("reports.view");
  const accessLoading = access !== null && access.loading;

  const [report, setReport] = useState<OverviewReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!canStats) return;
    let cancelled = false;
    // The user's own calendar date — the quick "today" glance; exact ranged
    // reporting (hotel business date) lives in /hotel/reports.
    const today = new Intl.DateTimeFormat("en-CA").format(new Date());
    getOverviewReport({ date_from: today, date_to: today })
      .then((data) => {
        if (!cancelled) {
          setReport(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(messageForError(err, t));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t is stable per locale
  }, [canStats]);

  const shortcuts = visibleHotelNavItems(hotelNavItems(t), access).filter(
    (item) => item.href !== "/hotel",
  );
  const d = t.hotelDashboard;

  return (
    <PageContainer>
      <PageHeader title={d.title} subtitle={d.subtitle} />

      {canStats || accessLoading ? (
        <section className="stack" aria-label={d.todayHeading}>
          <SectionHeader title={d.todayHeading} />
          {error ? (
            <Alert tone="error">{error}</Alert>
          ) : report ? (
            <div className="stat-grid">
              <StatCard
                label={d.cards.roomsTotal}
                value={report.rooms_total}
                icon={BedDouble}
                tone="primary"
              />
              <StatCard
                label={d.cards.roomsAvailable}
                value={report.rooms_available}
                icon={DoorOpen}
                tone="success"
              />
              <StatCard
                label={d.cards.inHouse}
                value={report.in_house_count}
                icon={Users}
                tone="info"
              />
              <StatCard
                label={d.cards.roomsDirty}
                value={report.rooms_dirty}
                icon={Sparkles}
                tone="warning"
              />
              <StatCard
                label={d.cards.roomsMaintenance}
                value={report.rooms_maintenance}
                icon={Wrench}
                tone="danger"
              />
              <StatCard
                label={d.cards.todayReservations}
                value={report.reservations_count}
                icon={CalendarCheck}
                tone="primary"
              />
              <StatCard
                label={d.cards.todayArrivals}
                value={report.arrivals_count}
                icon={LogIn}
                tone="success"
              />
              <StatCard
                label={d.cards.todayDepartures}
                value={report.departures_count}
                icon={LogOut}
                tone="neutral"
              />
              <StatCard
                label={d.cards.todayPayments}
                value={report.total_payments}
                icon={Wallet}
                tone="success"
              />
              <StatCard
                label={d.cards.todayExpenses}
                value={report.total_expenses}
                icon={Wallet}
                tone="warning"
              />
              <StatCard
                label={d.cards.todayOrders}
                value={report.service_orders_total}
                icon={UtensilsCrossed}
                tone="info"
              />
              <StatCard
                label={d.cards.openHousekeeping}
                value={report.open_housekeeping_tasks}
                icon={ClipboardList}
                tone="warning"
              />
              <StatCard
                label={d.cards.openMaintenance}
                value={report.open_maintenance_requests}
                icon={Wrench}
                tone="danger"
              />
            </div>
          ) : (
            <div className="stat-grid" aria-hidden="true">
              {Array.from({ length: 8 }, (_, i) => (
                <Skeleton key={i} height="6rem" radius="var(--radius-lg)" />
              ))}
            </div>
          )}
        </section>
      ) : null}

      <section className="stack" aria-label={d.quickAccess}>
        <SectionHeader title={d.quickAccess} />
        <div className="shortcut-grid">
          {shortcuts.map((item) => (
            <Link key={item.href} href={item.href} className="shortcut-card">
              <span className="shortcut-card__icon">
                <Icon icon={item.icon} size="lg" />
              </span>
              <span className="shortcut-card__label">{item.label}</span>
            </Link>
          ))}
        </div>
      </section>
    </PageContainer>
  );
}
