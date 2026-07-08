"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Clock, PlayCircle } from "lucide-react";

import {
  Alert,
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
  Modal,
  Pagination,
  SectionHeader,
  Select,
  useToast,
  type Column,
} from "@/components/ui";
import { cancelShift, getShiftSummary, listShifts } from "@/lib/api/shifts";
import { messageForError } from "@/lib/api/errors";
import type { ShiftCashSummary, ShiftListItem, ShiftStatus } from "@/lib/api/types";
import { formatDateTime, shiftStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useCurrentUser } from "@/lib/session/CurrentUserContext";
import { CloseShiftModal, OpenShiftModal } from "./CurrentShiftTab";

const PAGE_SIZE = 25;
const STATUSES: ShiftStatus[] = ["open", "closed", "cancelled"];

export function ShiftsTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const me = useCurrentUser();
  const l = t.shifts.list;

  const [rows, setRows] = useState<ShiftListItem[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [date, setDate] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [openModal, setOpenModal] = useState(false);
  const [closeTarget, setCloseTarget] = useState<{
    shift: ShiftListItem;
    expected: string;
  } | null>(null);
  const [cancelTarget, setCancelTarget] = useState<ShiftListItem | null>(null);
  const [summaryTarget, setSummaryTarget] = useState<{
    shift: ShiftListItem;
    summary: ShiftCashSummary;
  } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listShifts({
        page,
        search: query || undefined,
        status: status || undefined,
        business_date: date || undefined,
      });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, query, status, date, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function openSummary(row: ShiftListItem, forClose: boolean) {
    try {
      const data = await getShiftSummary(row.id);
      if (forClose) {
        setCloseTarget({ shift: row, expected: data.cash_summary.expected_cash });
      } else {
        setSummaryTarget({ shift: row, summary: data.cash_summary });
      }
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: t.shifts.status[s] }));

  const columns: Column<ShiftListItem>[] = [
    { key: "shift_number", header: l.number },
    { key: "business_date", header: l.businessDate },
    { key: "responsible_name", header: l.responsible },
    {
      key: "status",
      header: t.common.status,
      render: (r) => (
        <Badge tone={shiftStatusTone(r.status)}>{t.shifts.status[r.status]}</Badge>
      ),
    },
    {
      key: "opened_at",
      header: l.openedAt,
      render: (r) => formatDateTime(r.opened_at, locale),
    },
    { key: "opening_cash_amount", header: l.opening },
    {
      key: "actual_cash_amount",
      header: l.actual,
      render: (r) => r.actual_cash_amount ?? "—",
    },
    {
      key: "cash_difference",
      header: l.difference,
      render: (r) =>
        r.status === "closed" ? (
          <Badge tone={r.cash_difference === "0.00" ? "success" : "warning"}>
            {r.cash_difference}
          </Badge>
        ) : (
          "—"
        ),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => (
        <div className="table__actions">
          <Button size="sm" variant="secondary" onClick={() => openSummary(r, false)}>
            {l.summary}
          </Button>
          {r.status === "open" ? (
            <>
              <Button size="sm" onClick={() => openSummary(r, true)}>
                {t.shifts.current.close}
              </Button>
              <Button size="sm" variant="danger" onClick={() => setCancelTarget(r)}>
                {t.common.cancel}
              </Button>
            </>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <Card>
        <SectionHeader
          title={l.title}
          actions={
            <Button icon={PlayCircle} onClick={() => setOpenModal(true)}>
              {t.shifts.current.open}
            </Button>
          }
        />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            setQuery(search);
          }}
        >
          <FilterBar>
            <FormField label={t.common.search} htmlFor="sh-search">
              <Input
                id="sh-search"
                value={search}
                placeholder={l.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
              />
            </FormField>
            <FormField label={t.common.status} htmlFor="sh-status">
              <Select
                id="sh-status"
                value={status}
                placeholder={t.common.all}
                options={statusOptions}
                onChange={(e) => {
                  setPage(1);
                  setStatus(e.target.value);
                }}
              />
            </FormField>
            <FormField label={l.businessDate} htmlFor="sh-date">
              <Input
                id="sh-date"
                type="date"
                value={date}
                onChange={(e) => {
                  setPage(1);
                  setDate(e.target.value);
                }}
              />
            </FormField>
          </FilterBar>
        </form>
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
            <EmptyState title={l.empty} hint={l.emptyHint} icon={Clock} />
          ) : (
            <>
              <DataTable caption={l.title} columns={columns} rows={rows} rowKey={(r) => r.id} />
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

      <OpenShiftModal
        open={openModal}
        onClose={() => setOpenModal(false)}
        onDone={() => {
          setOpenModal(false);
          notify(t.shifts.msgs.opened);
          load();
        }}
      />
      {closeTarget ? (
        <CloseShiftModal
          open
          shift={closeTarget.shift}
          expected={closeTarget.expected}
          onClose={() => setCloseTarget(null)}
          onDone={() => {
            setCloseTarget(null);
            notify(t.shifts.msgs.closed);
            load();
          }}
        />
      ) : null}
      <CancelShiftModal
        shift={cancelTarget}
        onClose={() => setCancelTarget(null)}
        onDone={() => {
          setCancelTarget(null);
          notify(t.shifts.msgs.cancelled);
          load();
        }}
      />
      <SummaryModal
        state={summaryTarget}
        onClose={() => setSummaryTarget(null)}
      />
      {me ? null : null}
    </>
  );
}

function CancelShiftModal({
  shift,
  onClose,
  onDone,
}: {
  shift: ShiftListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (shift) {
      setReason("");
      setError(null);
    }
  }, [shift]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!shift) return;
    if (!reason.trim()) return setError(t.errors.validation);
    setBusy(true);
    setError(null);
    try {
      await cancelShift(shift.id, reason.trim());
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={shift !== null}
      onClose={onClose}
      title={t.shifts.form.cancelTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.close}
          </Button>
          <Button form="shift-cancel-form" type="submit" variant="danger" loading={busy}>
            {t.common.cancel}
          </Button>
        </>
      }
    >
      <form id="shift-cancel-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={t.shifts.form.cancelReason} htmlFor="shc-reason">
          <Input id="shc-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}

function SummaryModal({
  state,
  onClose,
}: {
  state: { shift: ShiftListItem; summary: ShiftCashSummary } | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const c = t.shifts.current;
  if (!state) return null;
  const { shift, summary } = state;
  return (
    <Modal
      open
      onClose={onClose}
      title={`${t.shifts.list.summary} — ${shift.shift_number}`}
      closeLabel={t.common.close}
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t.common.close}
        </Button>
      }
    >
      <div className="stack">
        <div className="form-grid">
          <FormField label={c.openingCash} htmlFor="sum-open">
            <Input id="sum-open" value={summary.opening_cash} readOnly disabled />
          </FormField>
          <FormField label={c.expectedCash} htmlFor="sum-exp">
            <Input id="sum-exp" value={summary.expected_cash} readOnly disabled />
          </FormField>
          <FormField label={c.cashIn} htmlFor="sum-in">
            <Input
              id="sum-in"
              value={`${summary.cash_payments_total} (${summary.payments_count})`}
              readOnly
              disabled
            />
          </FormField>
          <FormField label={c.cashOut} htmlFor="sum-out">
            <Input
              id="sum-out"
              value={`${summary.cash_expenses_total} (${summary.expenses_count})`}
              readOnly
              disabled
            />
          </FormField>
        </div>
        <div className="cluster">
          {Object.entries(summary.payments_by_method).map(([method, info]) => (
            <Badge key={`p-${method}`} tone="info">
              {method}: {info.total} ({info.count})
            </Badge>
          ))}
          {Object.entries(summary.expenses_by_method).map(([method, info]) => (
            <Badge key={`e-${method}`} tone="warning">
              {method}: {info.total} ({info.count})
            </Badge>
          ))}
        </div>
      </div>
    </Modal>
  );
}
