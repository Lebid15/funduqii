"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarCheck2, FileSearch, Lock } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  SectionHeader,
  StatCard,
  useToast,
  type Column,
} from "@/components/ui";
import {
  closeBusinessDay,
  listDailyCloses,
  prepareDailyClose,
} from "@/lib/api/shifts";
import { messageForError } from "@/lib/api/errors";
import type { DailyClose, DailyCloseListItem } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

export function DailyCloseTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const d = t.shifts.dc;

  const [rows, setRows] = useState<DailyCloseListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [businessDate, setBusinessDate] = useState("");
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState<DailyClose | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDailyCloses({});
      setRows(data.results);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  async function prepare() {
    setPreparing(true);
    try {
      const close = await prepareDailyClose(businessDate || undefined, notes);
      setPreview(close);
      notify(d.preparedMsg);
      load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setPreparing(false);
    }
  }

  const columns: Column<DailyCloseListItem>[] = [
    { key: "close_number", header: d.number },
    { key: "business_date", header: d.businessDate },
    {
      key: "status",
      header: t.common.status,
      render: (r) => (
        <Badge tone={r.status === "closed" ? "success" : "warning"}>
          {t.shifts.dcStatus[r.status]}
        </Badge>
      ),
    },
    {
      key: "totals",
      header: d.payments,
      render: (r) => r.totals_json?.payments_total ?? "—",
    },
    {
      key: "expenses",
      header: d.expenses,
      render: (r) => r.totals_json?.expenses_total ?? "—",
    },
    { key: "closed_by_name", header: d.closedBy, render: (r) => r.closed_by_name || "—" },
    {
      key: "closed_at",
      header: d.closedAt,
      render: (r) => formatDateTime(r.closed_at, locale),
    },
  ];

  const snapshot = preview?.snapshot_json;
  return (
    <>
      <Card>
        <SectionHeader title={d.title} />
        <FilterBar>
          <FormField label={d.businessDate} htmlFor="dc-date">
            <Input
              id="dc-date"
              type="date"
              value={businessDate}
              onChange={(e) => setBusinessDate(e.target.value)}
            />
          </FormField>
          <FormField label={d.notes} htmlFor="dc-notes">
            <Input id="dc-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </FormField>
        </FilterBar>
        <div className="cluster">
          <Button
            variant="secondary"
            icon={FileSearch}
            loading={preparing}
            onClick={prepare}
          >
            {d.prepare}
          </Button>
          <Button icon={Lock} onClick={() => setConfirmClose(true)}>
            {d.close}
          </Button>
        </div>
        <Alert tone="warning">{d.closeWarning}</Alert>
      </Card>

      {snapshot ? (
        <Card>
          <SectionHeader
            title={`${d.preview} — ${snapshot.business_date}`}
            actions={
              <Badge tone={preview!.status === "closed" ? "success" : "warning"}>
                {t.shifts.dcStatus[preview!.status]}
              </Badge>
            }
          />
          <div className="workflow-grid">
            <StatCard
              label={d.payments}
              value={snapshot.payments.total}
              caption={`${d.count}: ${snapshot.payments.count} · ${d.cashTotal}: ${snapshot.payments.cash_total} · ${d.voided}: ${snapshot.payments.voided_count}`}
            />
            <StatCard
              label={d.expenses}
              value={snapshot.expenses.total}
              caption={`${d.count}: ${snapshot.expenses.count} · ${d.cashTotal}: ${snapshot.expenses.cash_total} · ${d.voided}: ${snapshot.expenses.voided_count}`}
            />
            <StatCard
              label={d.servicePostings}
              value={snapshot.service_postings.total}
              caption={`${d.count}: ${snapshot.service_postings.count}`}
            />
            <StatCard label={d.arrivals} value={snapshot.stays.arrivals} />
            <StatCard label={d.departures} value={snapshot.stays.departures} />
            <StatCard label={d.pendingHandovers} value={snapshot.pending_handovers} />
            <StatCard
              label={d.unassigned}
              value={
                snapshot.unassigned_movements.payments_count +
                snapshot.unassigned_movements.expenses_count
              }
              caption={`${d.payments}: ${snapshot.unassigned_movements.payments_total} · ${d.expenses}: ${snapshot.unassigned_movements.expenses_total}`}
            />
          </div>
          {snapshot.shifts.length > 0 ? (
            <div className="cluster">
              {snapshot.shifts.map((s) => (
                <Badge
                  key={s.shift_number}
                  tone={s.status === "open" ? "warning" : "neutral"}
                >
                  {s.shift_number} · {t.shifts.status[s.status]} · {s.responsible}
                </Badge>
              ))}
            </div>
          ) : null}
        </Card>
      ) : null}

      <Card>
        <SectionHeader title={d.closedDays} />
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
            <EmptyState title={d.empty} hint={d.emptyHint} icon={CalendarCheck2} />
          ) : (
            <DataTable caption={d.closedDays} columns={columns} rows={rows} rowKey={(r) => r.id} />
          )
        ) : null}
      </Card>

      <ConfirmDialog
        open={confirmClose}
        title={d.closeTitle}
        body={d.closeWarning}
        confirmLabel={d.close}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        onClose={() => setConfirmClose(false)}
        onConfirm={async () => {
          try {
            const close = await closeBusinessDay(businessDate || undefined, notes);
            setPreview(close);
            notify(d.closedMsg);
            load();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setConfirmClose(false);
          }
        }}
      />
    </>
  );
}
