"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Archive, Bell, CheckCheck, Check, ExternalLink } from "lucide-react";

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
  useToast,
  type Column,
} from "@/components/ui";
import {
  archiveNotification,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/api/notifications";
import { messageForError } from "@/lib/api/errors";
import type {
  ActivityCategory,
  ActivitySeverity,
  HotelNotification,
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

export function InboxTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const n = t.notifications;

  const [rows, setRows] = useState<HotelNotification[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [archived, setArchived] = useState(false);
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState("");
  const [date, setDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listNotifications({
        page,
        archived: archived ? "true" : undefined,
        unread: onlyUnread ? "true" : undefined,
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
  }, [page, archived, onlyUnread, category, severity, date, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(id: number, action: () => Promise<unknown>, msg: string) {
    setBusyId(id);
    try {
      await action();
      notify(msg);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusyId(null);
    }
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: n.categories[c] }));
  const severityOptions = SEVERITIES.map((s) => ({ value: s, label: n.severities[s] }));

  const columns: Column<HotelNotification>[] = [
    {
      key: "title",
      header: n.inbox.title,
      render: (r) => (
        <span className={r.is_read ? "muted" : undefined}>
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
      key: "created_at",
      header: t.common.createdAt,
      render: (r) => formatDateTime(r.created_at, locale),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => (
        <div className="table__actions">
          {r.related_url ? (
            <Link href={r.related_url}>
              <Button size="sm" variant="secondary" icon={ExternalLink}>
                {n.inbox.open}
              </Button>
            </Link>
          ) : null}
          {!r.is_read ? (
            <Button
              size="sm"
              variant="secondary"
              icon={Check}
              loading={busyId === r.id}
              onClick={() => run(r.id, () => markNotificationRead(r.id), n.inbox.readMsg)}
            >
              {n.inbox.markRead}
            </Button>
          ) : null}
          {!r.is_archived ? (
            <Button
              size="sm"
              variant="secondary"
              icon={Archive}
              loading={busyId === r.id}
              onClick={() => run(r.id, () => archiveNotification(r.id), n.inbox.archivedMsg)}
            >
              {n.inbox.archiveBtn}
            </Button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <Card>
      <SectionHeader
        title={n.inbox.title}
        actions={
          <Button
            variant="secondary"
            icon={CheckCheck}
            onClick={() =>
              run(0, () => markAllNotificationsRead(), n.inbox.allReadMsg)
            }
          >
            {n.inbox.markAllRead}
          </Button>
        }
      />
      <FilterBar>
        <FormField label={n.filters.category} htmlFor="nf-category">
          <Select
            id="nf-category"
            value={category}
            placeholder={t.common.all}
            options={categoryOptions}
            onChange={(e) => {
              setPage(1);
              setCategory(e.target.value);
            }}
          />
        </FormField>
        <FormField label={n.filters.severity} htmlFor="nf-severity">
          <Select
            id="nf-severity"
            value={severity}
            placeholder={t.common.all}
            options={severityOptions}
            onChange={(e) => {
              setPage(1);
              setSeverity(e.target.value);
            }}
          />
        </FormField>
        <FormField label={n.filters.date} htmlFor="nf-date">
          <Input
            id="nf-date"
            type="date"
            value={date}
            onChange={(e) => {
              setPage(1);
              setDate(e.target.value);
            }}
          />
        </FormField>
      </FilterBar>
      <div className="cluster">
        <Button
          size="sm"
          variant={onlyUnread ? "primary" : "secondary"}
          onClick={() => {
            setPage(1);
            setOnlyUnread((v) => !v);
          }}
        >
          {n.inbox.onlyUnread}
        </Button>
        <Button
          size="sm"
          variant={archived ? "primary" : "secondary"}
          onClick={() => {
            setPage(1);
            setArchived((v) => !v);
          }}
        >
          {n.inbox.showArchived}
        </Button>
      </div>
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
          <EmptyState title={n.inbox.empty} hint={n.inbox.emptyHint} icon={Bell} />
        ) : (
          <>
            <DataTable
              caption={n.inbox.title}
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
