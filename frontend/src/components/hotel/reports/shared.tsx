"use client";

/** Small shared pieces for the report tabs: a generic loader wrapper and
 * bucket/day tables built from the central DataTable. Labels are resolved by
 * the caller (translated); raw backend keys are shown only as a fallback. */
import { useCallback, useEffect, useState, type ReactNode } from "react";

import {
  Alert,
  Badge,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  SectionHeader,
  type BadgeTone,
  type Column,
} from "@/components/ui";
import { messageForError } from "@/lib/api/errors";
import type {
  FinanceSourceStatus,
  ReportBucket,
  ReportDayRow,
} from "@/lib/api/types";
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

const SOURCE_TONE: Record<FinanceSourceStatus, BadgeTone> = {
  live: "success",
  snapshot: "info",
  mixed: "warning",
  none: "neutral",
};

/** Source-of-truth badge + data-completeness notes shared by every finance
 * view. `daysMissingClose` = days in range not yet closed; `reportingMissing`
 * = closed days that predate the historical finance block. `manualRoomOnly`
 * surfaces the ADR/RevPAR data-quality caveat. */
export function FinanceMeta({
  sourceStatus,
  daysMissingClose,
  reportingMissing,
  manualRoomOnly,
}: {
  sourceStatus?: FinanceSourceStatus;
  daysMissingClose?: string[];
  reportingMissing?: string[];
  manualRoomOnly?: boolean;
}) {
  const { t } = useI18n();
  const f = t.reports.fin;
  const statusLabel: Record<FinanceSourceStatus, string> = {
    live: f.sourceLive,
    snapshot: f.sourceSnapshot,
    mixed: f.sourceMixed,
    none: f.sourceNone,
  };
  return (
    <>
      {sourceStatus ? (
        <div className="cluster">
          <Badge tone={SOURCE_TONE[sourceStatus]}>
            {`${f.sourceStatus}: ${statusLabel[sourceStatus]}`}
          </Badge>
        </div>
      ) : null}
      {daysMissingClose && daysMissingClose.length > 0 ? (
        <Alert tone="warning">
          {`${f.missingClose} (${daysMissingClose.join(", ")})`}
        </Alert>
      ) : null}
      {reportingMissing && reportingMissing.length > 0 ? (
        <Alert tone="info">
          {`${f.missingReporting} (${reportingMissing.join(", ")})`}
        </Alert>
      ) : null}
      {manualRoomOnly ? <Alert tone="info">{f.dataQualityRoom}</Alert> : null}
    </>
  );
}

/** Translate a revenue-category key (room/restaurant/.../total). */
export function useRevenueLabel(): (key: string) => string {
  const { t } = useI18n();
  const f = t.reports.fin;
  const map: Record<string, string> = {
    room: f.catRoom,
    restaurant: f.catRestaurant,
    cafe: f.catCafe,
    services: f.catServices,
    other: f.catOther,
    adjustments: f.catAdjustments,
    discounts: f.catDiscounts,
    taxes: f.catTaxes,
    total: f.catTotal,
  };
  return (key: string) => map[key] ?? key;
}

/** A key → amount table (payments by_method, expenses by_category, revenue by
 * category). Amounts are decimal strings, rendered verbatim, aligned to end. */
export function AmountTable({
  title,
  data,
  keyHeader,
  valueHeader,
  labelFor,
}: {
  title: string;
  data: Record<string, string>;
  keyHeader: string;
  valueHeader: string;
  labelFor?: (key: string) => string;
}) {
  const { t } = useI18n();
  const r = t.reports.common;
  const rows = Object.entries(data).map(([key, value]) => ({ key, value }));
  const columns: Column<{ key: string; value: string }>[] = [
    {
      key: "key",
      header: keyHeader,
      render: (row) => (labelFor ? labelFor(row.key) : row.key),
    },
    { key: "value", header: valueHeader, align: "end" },
  ];
  return (
    <Card>
      <SectionHeader title={title} />
      {rows.length === 0 ? (
        <EmptyState title={r.empty} hint={r.emptyHint} />
      ) : (
        <DataTable
          caption={title}
          columns={columns}
          rows={rows}
          rowKey={(row) => row.key}
        />
      )}
    </Card>
  );
}
