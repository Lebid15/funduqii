"use client";

/** Small shared pieces for the report tabs: a generic loader wrapper and
 * bucket/day tables built from the central DataTable. Labels are resolved by
 * the caller (translated); raw backend keys are shown only as a fallback. */
import { useCallback, useEffect, useState, type ReactNode } from "react";

import {
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  SectionHeader,
  type Column,
} from "@/components/ui";
import { messageForError } from "@/lib/api/errors";
import type { ReportBucket, ReportDayRow } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import type { ReportRange } from "@/lib/api/reports";

export function useReport<T>(
  loader: (range: ReportRange) => Promise<T>,
  range: ReportRange,
) {
  const { t } = useI18n();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await loader(range));
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range.date_from, range.date_to, range.page, t]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, error, loading, reload: load };
}

export function ReportState({
  loading,
  error,
  onRetry,
  children,
}: {
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  children: ReactNode;
}) {
  const { t } = useI18n();
  if (loading) return <LoadingState label={t.common.loading} />;
  if (error)
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={error}
        retryLabel={t.common.retry}
        onRetry={onRetry}
      />
    );
  return <>{children}</>;
}

export function BucketTable({
  title,
  rows,
  labelFor,
  showTotal,
}: {
  title: string;
  rows: ReportBucket[];
  labelFor?: (key: string) => string;
  showTotal?: boolean;
}) {
  const { t } = useI18n();
  const r = t.reports.common;
  const columns: Column<ReportBucket>[] = [
    {
      key: "key",
      header: r.key,
      render: (row) => (labelFor ? labelFor(row.key) : row.key),
    },
    { key: "count", header: r.count },
  ];
  if (showTotal) {
    columns.push({ key: "total", header: r.total, render: (row) => row.total ?? "—" });
  }
  return (
    <Card>
      <SectionHeader title={title} />
      {rows.length === 0 ? (
        <EmptyState title={r.empty} hint={r.emptyHint} />
      ) : (
        <DataTable caption={title} columns={columns} rows={rows} rowKey={(row) => row.key} />
      )}
    </Card>
  );
}

export function DayTable({ title, rows }: { title: string; rows: ReportDayRow[] }) {
  const { t } = useI18n();
  const r = t.reports.common;
  const columns: Column<ReportDayRow>[] = [
    { key: "date", header: r.date },
    { key: "count", header: r.count },
    { key: "total", header: r.total },
  ];
  return (
    <Card>
      <SectionHeader title={title} />
      {rows.length === 0 ? (
        <EmptyState title={r.empty} hint={r.emptyHint} />
      ) : (
        <DataTable caption={title} columns={columns} rows={rows} rowKey={(row) => row.date} />
      )}
    </Card>
  );
}

export function CountsByDayTable({
  title,
  days,
}: {
  title: string;
  days: Record<string, number>;
}) {
  const { t } = useI18n();
  const r = t.reports.common;
  const rows = Object.entries(days).map(([date, count]) => ({ date, count }));
  const columns: Column<{ date: string; count: number }>[] = [
    { key: "date", header: r.date },
    { key: "count", header: r.count },
  ];
  return (
    <Card>
      <SectionHeader title={title} />
      {rows.length === 0 ? (
        <EmptyState title={r.empty} hint={r.emptyHint} />
      ) : (
        <DataTable caption={title} columns={columns} rows={rows} rowKey={(row) => row.date} />
      )}
    </Card>
  );
}
