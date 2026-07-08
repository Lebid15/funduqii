"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, ExternalLink } from "lucide-react";

import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  Pagination,
  SectionHeader,
  Select,
  type Column,
} from "@/components/ui";
import { listActivity } from "@/lib/api/notifications";
import { messageForError } from "@/lib/api/errors";
import type {
  ActivityCategory,
  ActivityEventRow,
  ActivitySeverity,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

const PAGE_SIZE = 25;
const CATEGORIES: ActivityCategory[] = [
  "reservation", "stay", "guest", "room", "finance", "service",
  "operation", "shift", "staff", "report", "system",
];
const SEVERITIES: ActivitySeverity[] = ["info", "success", "warning", "danger"];

function severityTone(severity: ActivitySeverity) {
  return severity === "info" ? "neutral" : severity;
}

export function ActivityTab() {
  const { t, locale } = useI18n();
  const n = t.notifications;

  const [rows, setRows] = useState<ActivityEventRow[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState("");
  const [date, setDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listActivity({
        page,
        category: category || undefined,
        severity: severity || undefined,
        date: date || undefined,
      });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, category, severity, date, t]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: n.categories[c] }));
  const severityOptions = SEVERITIES.map((s) => ({ value: s, label: n.severities[s] }));
  const eventTypeLabels = n.eventTypes as Record<string, string>;

  const columns: Column<ActivityEventRow>[] = [
    { key: "event_number", header: n.activity.type },
    {
      key: "event_type",
      header: n.activity.type,
      render: (r) => eventTypeLabels[r.event_type] ?? r.event_type,
    },
    {
      key: "title",
      header: n.inbox.title,
      render: (r) => (
        <span>
          <strong>{r.title}</strong>
          {r.message ? <span className="muted small"> — {r.message}</span> : null}
        </span>
      ),
    },
    {
      key: "category",
      header: n.filters.category,
      render: (r) => <Badge tone="neutral">{n.categories[r.category]}</Badge>,
    },
    {
      key: "severity",
      header: n.filters.severity,
      render: (r) => <Badge tone={severityTone(r.severity)}>{n.severities[r.severity]}</Badge>,
    },
    {
      key: "actor_name",
      header: n.activity.actor,
      render: (r) => r.actor_name || n.activity.system,
    },
    {
      key: "occurred_at",
      header: n.activity.time,
      render: (r) => formatDateTime(r.occurred_at, locale),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) =>
        r.related_url ? (
          <Link href={r.related_url}>
            <Button size="sm" variant="secondary" icon={ExternalLink}>
              {n.inbox.open}
            </Button>
          </Link>
        ) : (
          <span className="muted small">—</span>
        ),
    },
  ];

  return (
    <Card>
      <SectionHeader title={n.activity.title} />
      <FilterBar>
        <FormField label={n.filters.category} htmlFor="act-category">
          <Select
            id="act-category"
            value={category}
            placeholder={t.common.all}
            options={categoryOptions}
            onChange={(e) => {
              setPage(1);
              setCategory(e.target.value);
            }}
          />
        </FormField>
        <FormField label={n.filters.severity} htmlFor="act-severity">
          <Select
            id="act-severity"
            value={severity}
            placeholder={t.common.all}
            options={severityOptions}
            onChange={(e) => {
              setPage(1);
              setSeverity(e.target.value);
            }}
          />
        </FormField>
        <FormField label={n.filters.date} htmlFor="act-date">
          <Input
            id="act-date"
            type="date"
            value={date}
            onChange={(e) => {
              setPage(1);
              setDate(e.target.value);
            }}
          />
        </FormField>
      </FilterBar>
      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? (
        <ErrorState
          title={t.states.errorTitle}
          message={error}
          retryLabel={t.common.retry}
          onRetry={load}
        />
      ) : null}
      {!loading && !error ? (
        rows.length === 0 ? (
          <EmptyState
            title={n.activity.empty}
            hint={n.activity.emptyHint}
            icon={Activity}
          />
        ) : (
          <>
            <DataTable
              caption={n.activity.title}
              columns={columns}
              rows={rows}
              rowKey={(r) => r.id}
            />
            <Pagination
              page={page}
              totalPages={totalPages}
              onPageChange={setPage}
              labels={{
                previous: t.pagination.previous,
                next: t.pagination.next,
                status: t.pagination.page
                  .replace("{page}", String(page))
                  .replace("{total}", String(totalPages)),
              }}
            />
          </>
        )
      ) : null}
    </Card>
  );
}
