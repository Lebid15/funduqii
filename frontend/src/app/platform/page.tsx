"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  Badge,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  SectionHeader,
  StatCard,
  type Column,
} from "@/components/ui";
import { PageContainer } from "@/components/layout/PageContainer";
import { fetchOverview } from "@/lib/api/platform";
import { messageForError } from "@/lib/api/errors";
import type { Hotel, HotelSubscription, PlatformOverview } from "@/lib/api/types";
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
  const [overview, setOverview] = useState<PlatformOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Await-first: no synchronous setState runs on the effect tick (the initial
  // `loading` state already covers the first paint; user-initiated refetches
  // set the spinner from their own handlers).
  const load = useCallback(async () => {
    try {
      const data = await fetchOverview();
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

  return (
    <PageContainer>
      <PageHeader title={t.dashboard.title} subtitle={t.dashboard.subtitle} />

      {loading ? <LoadingState label={t.common.loading} /> : null}

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
            <StatCard label={t.dashboard.hotelsTotal} value={overview.hotels.total} />
            <StatCard label={t.dashboard.hotelsActive} value={overview.hotels.active} />
            <StatCard label={t.dashboard.hotelsSetup} value={overview.hotels.setup} />
            <StatCard
              label={t.dashboard.hotelsSuspended}
              value={overview.hotels.suspended}
            />
            <StatCard
              label={t.dashboard.activeTrials}
              value={overview.subscriptions.active_trials}
            />
            <StatCard
              label={t.dashboard.activeSubscriptions}
              value={overview.subscriptions.active}
            />
            <StatCard
              label={t.dashboard.expiringSoon}
              value={overview.subscriptions.expiring_soon}
            />
            <StatCard
              label={t.dashboard.expired}
              value={overview.subscriptions.expired}
            />
          </section>

          <Card>
            <SectionHeader
              title={t.dashboard.recentHotels}
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
              actions={
                <Link
                  className="btn btn--ghost btn--sm"
                  href="/platform/subscriptions"
                >
                  {t.subscriptions.title}
                </Link>
              }
            />
            {overview.recent_subscriptions.length === 0 ? (
              <EmptyState title={t.dashboard.noSubscriptions} />
            ) : (
              <DataTable
                caption={t.dashboard.recentSubscriptions}
                columns={subColumns}
                rows={overview.recent_subscriptions}
                rowKey={(row) => row.id}
              />
            )}
          </Card>
        </>
      ) : null}
    </PageContainer>
  );
}
