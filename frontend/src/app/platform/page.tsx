"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Building2,
  CircleCheck,
  CirclePause,
  CircleX,
  Clock,
  CreditCard,
  Gift,
  Globe,
  Hotel as HotelIcon,
  Package,
  TriangleAlert,
  Wallet,
} from "lucide-react";

import {
  Badge,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  Icon,
  SectionHeader,
  Skeleton,
  StatCard,
  type Column,
} from "@/components/ui";
import { useCurrentUser } from "@/lib/session/CurrentUserContext";
import { PageContainer } from "@/components/layout/PageContainer";
import { fetchDashboard } from "@/lib/api/platform";
import { messageForError } from "@/lib/api/errors";
import type { Hotel, HotelSubscription, PlatformDashboard } from "@/lib/api/types";
import {
  formatDate,
  hotelStatusLabel,
  hotelStatusTone,
  subscriptionStatusLabel,
  subscriptionStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function DashboardPage() {
  const { t, locale } = useI18n();
  const user = useCurrentUser();
  const [overview, setOverview] = useState<PlatformDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Await-first: no synchronous setState runs on the effect tick (the initial
  // `loading` state already covers the first paint; user-initiated refetches
  // set the spinner from their own handlers).
  const load = useCallback(async () => {
    try {
      const data = await fetchDashboard();
      setOverview(data);
      setError(null);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const reload = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);

  const hotelColumns: Column<Hotel>[] = [
    { key: "name", header: t.hotels.name },
    { key: "slug", header: t.hotels.slug },
    {
      key: "status",
      header: t.common.status,
      render: (row) => (
        <Badge tone={hotelStatusTone(row.status)}>
          {hotelStatusLabel(row.status, t)}
        </Badge>
      ),
    },
    {
      key: "created_at",
      header: t.common.createdAt,
      render: (row) => formatDate(row.created_at, locale),
    },
  ];

  const subColumns: Column<HotelSubscription>[] = [
    { key: "hotel_name", header: t.subscriptions.hotel },
    { key: "plan_name", header: t.subscriptions.plan },
    {
      key: "status",
      header: t.common.status,
      render: (row) => (
        <Badge tone={subscriptionStatusTone(row.status)}>
          {subscriptionStatusLabel(row.status, t)}
        </Badge>
      ),
    },
    {
      key: "created_at",
      header: t.common.createdAt,
      render: (row) => formatDate(row.created_at, locale),
    },
  ];

  const firstName = (user?.full_name ?? "").trim().split(/\s+/)[0] || t.app.name;

  return (
    <PageContainer>
      <section className="hero">
        <div className="hero__content">
          <span className="hero__eyebrow">{t.dashboard.eyebrow}</span>
          <h1 className="hero__title">
            {t.dashboard.welcome.replace("{name}", firstName)}
          </h1>
          <p className="hero__subtitle">{t.dashboard.welcomeHint}</p>
        </div>
        <span className="hero__mark" aria-hidden="true">
          <Icon icon={HotelIcon} size="lg" />
        </span>
      </section>

      {loading ? <DashboardSkeleton /> : null}

      {!loading && error ? (
        <ErrorState
          title={t.states.errorTitle}
          message={error}
          retryLabel={t.common.retry}
          onRetry={reload}
        />
      ) : null}

      {!loading && !error && overview ? (
        <>
          <section className="stat-grid">
            <StatCard
              label={t.dashboard.hotelsTotal}
              value={overview.total_hotels}
              caption={t.dashboard.captions.hotelsTotal}
              icon={Building2}
              tone="primary"
            />
            <StatCard
              label={t.dashboard.hotelsActive}
              value={overview.active_hotels}
              caption={t.dashboard.captions.hotelsActive}
              icon={CircleCheck}
              tone="success"
            />
            <StatCard
              label={t.dashboard.hotelsSetup}
              value={overview.setup_hotels}
              caption={t.dashboard.captions.hotelsSetup}
              icon={Clock}
              tone="neutral"
            />
            <StatCard
              label={t.dashboard.hotelsSuspended}
              value={overview.suspended_hotels}
              caption={t.dashboard.captions.hotelsSuspended}
              icon={CirclePause}
              tone="danger"
            />
            <StatCard
              label={t.dashboard.trialHotels}
              value={overview.trial_hotels}
              caption={t.dashboard.captions.trialHotels}
              icon={Gift}
              tone="info"
            />
            <StatCard
              label={t.dashboard.paidHotels}
              value={overview.paid_hotels}
              caption={t.dashboard.captions.paidHotels}
              icon={CreditCard}
              tone="success"
            />
            <StatCard
              label={t.dashboard.expiringSoon}
              value={overview.expiring_soon_subscriptions}
              caption={t.dashboard.captions.expiringSoon}
              icon={TriangleAlert}
              tone="warning"
            />
            <StatCard
              label={t.dashboard.expired}
              value={overview.expired_subscriptions}
              caption={t.dashboard.captions.expired}
              icon={CircleX}
              tone="neutral"
            />
            <StatCard
              label={t.dashboard.publicListed}
              value={overview.public_listed_hotels}
              caption={t.dashboard.captions.publicListed}
              icon={Globe}
              tone="info"
            />
            <StatCard
              label={t.dashboard.totalPlans}
              value={overview.total_plans}
              caption={t.dashboard.captions.totalPlans}
              icon={Package}
              tone="neutral"
            />
          </section>

          {/* Estimated recurring revenue — an administrative indicator from
              manually activated subscriptions; deliberately NEVER "profit". */}
          <Card>
            <SectionHeader
              title={t.dashboard.revenueTitle}
              description={t.dashboard.revenueHint}
              icon={Wallet}
            />
            {Object.keys(overview.estimated_monthly_recurring_revenue).length ===
            0 ? (
              <p className="muted">{t.dashboard.revenueEmpty}</p>
            ) : (
              <div className="cluster">
                {Object.entries(overview.estimated_monthly_recurring_revenue).map(
                  ([currency, amount]) => (
                    <span className="revenue-figure" key={currency}>
                      {amount} <span className="muted">{currency}</span>
                    </span>
                  ),
                )}
              </div>
            )}
          </Card>

          <Card>
            <SectionHeader
              title={t.dashboard.recentHotels}
              icon={Building2}
              actions={
                <Link className="btn btn--ghost btn--sm" href="/platform/hotels">
                  {t.hotels.title}
                </Link>
              }
            />
            {overview.recent_hotels.length === 0 ? (
              <EmptyState title={t.dashboard.noHotels} />
            ) : (
              <DataTable
                caption={t.dashboard.recentHotels}
                columns={hotelColumns}
                rows={overview.recent_hotels}
                rowKey={(row) => row.id}
              />
            )}
          </Card>

          <Card>
            <SectionHeader
              title={t.dashboard.recentSubscriptions}
              icon={CreditCard}
              actions={
                <Link
                  className="btn btn--ghost btn--sm"
                  href="/platform/subscriptions"
                >
                  {t.subscriptions.title}
                </Link>
              }
            />
            {overview.recent_subscription_events.length === 0 ? (
              <EmptyState title={t.dashboard.noSubscriptions} />
            ) : (
              <DataTable
                caption={t.dashboard.recentSubscriptions}
                columns={subColumns}
                rows={overview.recent_subscription_events}
                rowKey={(row) => row.id}
              />
            )}
          </Card>
        </>
      ) : null}
    </PageContainer>
  );
}

/** Loading placeholder that mirrors the dashboard layout. */
function DashboardSkeleton() {
  return (
    <>
      <div className="skeleton-stat-grid">
        {Array.from({ length: 8 }).map((_, i) => (
          <div className="skeleton-card" key={i}>
            <Skeleton width="2.75rem" height="2.75rem" radius="var(--radius-md)" />
            <div className="stack" style={{ gap: "var(--space-2)", flex: 1 }}>
              <Skeleton width="60%" height="0.75rem" />
              <Skeleton width="40%" height="1.25rem" />
            </div>
          </div>
        ))}
      </div>
      <Card>
        <div className="stack">
          <Skeleton width="14rem" height="1.25rem" />
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} height="1.5rem" />
          ))}
        </div>
      </Card>
    </>
  );
}
