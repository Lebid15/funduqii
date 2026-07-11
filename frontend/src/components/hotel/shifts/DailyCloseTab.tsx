"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarCheck2, FileSearch, Lock, Printer } from "lucide-react";

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
  PrintDocumentLayout,
  SectionHeader,
  StatCard,
  useToast,
  type BadgeTone,
  type Column,
} from "@/components/ui";
import {
  closeBusinessDay,
  getDailyCloseStatement,
  listDailyCloses,
  prepareDailyClose,
} from "@/lib/api/shifts";
import { messageForError } from "@/lib/api/errors";
import type {
  DailyCloseException,
  DailyCloseListItem,
  DailyClosePreview,
  DailyCloseStatement,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { PrintModal } from "../finance/shared";

export function DailyCloseTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const d = t.shifts.dc;

  const codeLabel = useCallback(
    (code: string) => (d.codes as Record<string, string>)[code] ?? code,
    [d],
  );

  const [rows, setRows] = useState<DailyCloseListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState<DailyClosePreview | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [closing, setClosing] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [statement, setStatement] = useState<DailyCloseStatement | null>(null);

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
      const result = await prepareDailyClose();
      setPreview(result);
      notify(d.preparedMsg);
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setPreparing(false);
    }
  }

  async function doClose() {
    if (!preview) return;
    setClosing(true);
    try {
      await closeBusinessDay(preview.business_date, notes);
      notify(d.closedMsg);
      setPreview(null);
      setNotes("");
      load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setClosing(false);
      setConfirmClose(false);
    }
  }

  async function openStatement(pk: number) {
    try {
      setStatement(await getDailyCloseStatement(pk));
    } catch (err) {
      notify(messageForError(err, t), "error");
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
      key: "expected",
      header: d.expectedCash,
      render: (r) => r.totals_json?.expected_cash_total ?? "—",
    },
    {
      key: "actual",
      header: d.actualCash,
      render: (r) => r.totals_json?.actual_cash_total ?? "—",
    },
    {
      key: "difference",
      header: d.difference,
      render: (r) => r.totals_json?.difference_total ?? "—",
    },
    {
      key: "closed_by_name",
      header: d.closedBy,
      render: (r) => r.closed_by_name || "—",
    },
    {
      key: "closed_at",
      header: d.closedAt,
      render: (r) => formatDateTime(r.closed_at, locale),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) =>
        r.status === "closed" ? (
          <Button
            size="sm"
            variant="ghost"
            icon={Printer}
            onClick={() => openStatement(r.id)}
          >
            {t.shifts.print.printStatement}
          </Button>
        ) : (
          "—"
        ),
    },
  ];

  const p = preview;
  const totals = p?.preview_totals;
  const noExceptions =
    p !== null &&
    p.blocking_errors.length === 0 &&
    p.warnings.length === 0 &&
    p.informational_alerts.length === 0;
  const confirmBody = p
    ? [
        d.confirmDate.replace("{date}", p.business_date),
        d.confirmWarnings.replace("{count}", String(p.warnings.length)),
        d.confirmFinal,
        d.confirmAdvance,
      ].join(" ")
    : "";

  return (
    <>
      <Card>
        <SectionHeader title={d.title} />
        <FilterBar>
          <FormField label={d.notes} htmlFor="dc-notes">
            <Input
              id="dc-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
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
          <Button
            icon={Lock}
            disabled={!p || !p.can_close}
            onClick={() => setConfirmClose(true)}
          >
            {d.close}
          </Button>
        </div>
        <Alert tone="warning">{d.closeWarning}</Alert>
      </Card>

      {p && totals ? (
        <Card>
          <SectionHeader
            title={`${d.preview} — ${p.business_date}`}
            actions={
              <Badge tone={p.can_close ? "success" : "danger"}>
                {p.can_close ? d.canClose : d.cannotClose}
              </Badge>
            }
          />
          <div className="stack">
            <ExceptionGroup
              title={d.blockingTitle}
              tone="danger"
              items={p.blocking_errors}
              codeLabel={codeLabel}
            />
            <ExceptionGroup
              title={d.warningsTitle}
              tone="warning"
              items={p.warnings}
              codeLabel={codeLabel}
            />
            <ExceptionGroup
              title={d.infoTitle}
              tone="neutral"
              items={p.informational_alerts}
              codeLabel={codeLabel}
            />
            {noExceptions ? <p className="muted">{d.allClear}</p> : null}
          </div>
          <div className="workflow-grid">
            <StatCard label={d.paymentsCash} value={totals.payments_cash_total} />
            <StatCard label={d.paymentsNonCash} value={totals.payments_non_cash_total} />
            <StatCard label={d.expensesCash} value={totals.expenses_cash_total} />
            <StatCard label={d.expensesNonCash} value={totals.expenses_non_cash_total} />
            <StatCard label={d.restaurantSales} value={totals.restaurant_sales} />
            <StatCard label={d.cafeSales} value={totals.cafe_sales} />
            <StatCard label={d.shiftsCount} value={totals.shifts_count} />
            <StatCard label={d.expectedCash} value={totals.expected_cash_total} />
            <StatCard label={d.actualCash} value={totals.actual_cash_total} />
            <StatCard label={d.difference} value={totals.difference_total} />
          </div>
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
            <DataTable
              caption={d.closedDays}
              columns={columns}
              rows={rows}
              rowKey={(r) => r.id}
            />
          )
        ) : null}
      </Card>

      <ConfirmDialog
        open={confirmClose}
        title={d.closeTitle}
        body={confirmBody}
        confirmLabel={d.close}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        busy={closing}
        onClose={() => setConfirmClose(false)}
        onConfirm={doClose}
      />

      <DailyCloseStatementPrintModal
        statement={statement}
        onClose={() => setStatement(null)}
      />
    </>
  );
}

/** A labelled group of exception pills; renders nothing when empty. */
function ExceptionGroup({
  title,
  tone,
  items,
  codeLabel,
}: {
  title: string;
  tone: BadgeTone;
  items: DailyCloseException[];
  codeLabel: (code: string) => string;
}) {
  if (items.length === 0) return null;
  return (
    <div className="stack">
      <p className="muted small">{title}</p>
      <div className="cluster">
        {items.map((it) => {
          const extra =
            it.count !== undefined
              ? it.count
              : it.total_balance ?? it.net_cash ?? null;
          return (
            <Badge key={it.code} tone={tone}>
              {codeLabel(it.code)}
              {extra !== null ? ` · ${extra}` : ""}
            </Badge>
          );
        })}
      </div>
    </div>
  );
}

/** Print-friendly daily-close statement, rendered entirely from the stored
 *  snapshot returned by GET /shifts/daily-close/<pk>/statement. */
export function DailyCloseStatementPrintModal({
  statement,
  onClose,
}: {
  statement: DailyCloseStatement | null;
  onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const d = t.shifts.dc;
  if (!statement) return null;

  const { close } = statement;
  const s = close.snapshot_json;
  const id = s.identity;
  const um = s.exceptions.unassigned_movements;

  const codeLabel = (code: string) =>
    (d.codes as Record<string, string>)[code] ?? code;
  const statusLabel = (status: string) =>
    (t.shifts.status as Record<string, string>)[status] ?? status;

  const meta = [
    { label: t.common.status, value: t.shifts.dcStatus[close.status] },
    { label: d.businessDate, value: id.business_date },
    { label: d.nextBusinessDate, value: id.next_business_date },
    { label: d.timezone, value: id.timezone },
    { label: d.currency, value: id.currency },
    { label: d.closedBy, value: close.closed_by_name || "—" },
    { label: d.closedAt, value: formatDateTime(close.closed_at, locale) },
  ];

  return (
    <PrintModal open={statement !== null} title={d.statementTitle} onClose={onClose}>
      <PrintDocumentLayout
        hotelName={statement.hotel.hotel_name}
        hotelAddress={statement.hotel.address}
        hotelPhone={statement.hotel.phone}
        docTitle={d.statementTitle}
        docNumber={close.close_number}
        meta={meta}
        notes={close.notes || undefined}
        notesLabel={d.notes}
        signatureLabel={t.finance.print.signature}
      >
        <p className="muted">{d.shiftsSummary}</p>
        <dl className="print-grid">
          <div>
            <dt>{d.shiftsCount}</dt>
            <dd>{s.shifts.closed_shifts_count}</dd>
          </div>
          <div>
            <dt>{d.expectedCash}</dt>
            <dd>{s.shifts.expected_cash_total}</dd>
          </div>
          <div>
            <dt>{d.actualCash}</dt>
            <dd>{s.shifts.actual_cash_total}</dd>
          </div>
          <div>
            <dt>{d.difference}</dt>
            <dd>{s.shifts.difference_total}</dd>
          </div>
        </dl>
        {s.shifts.items.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>{t.shifts.list.number}</th>
                <th>{t.common.status}</th>
                <th>{t.shifts.list.responsible}</th>
                <th>{t.shifts.list.opening}</th>
                <th>{t.shifts.list.expected}</th>
                <th>{t.shifts.list.actual}</th>
                <th>{t.shifts.list.difference}</th>
              </tr>
            </thead>
            <tbody>
              {s.shifts.items.map((it) => (
                <tr key={it.shift_number}>
                  <td>{it.shift_number}</td>
                  <td>{statusLabel(it.status)}</td>
                  <td>{it.responsible}</td>
                  <td>{it.opening_cash}</td>
                  <td>{it.expected_cash}</td>
                  <td>{it.actual_cash}</td>
                  <td>{it.cash_difference}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}

        <p className="muted">{d.payments}</p>
        <dl className="print-grid">
          <div>
            <dt>{d.cashTotal}</dt>
            <dd>{s.payments.cash_total}</dd>
          </div>
          <div>
            <dt>{d.nonCashTotal}</dt>
            <dd>{s.payments.non_cash_total}</dd>
          </div>
          <div>
            <dt>{d.voided}</dt>
            <dd>
              {s.payments.voided_count} · {s.payments.voided_total}
            </dd>
          </div>
          <div>
            <dt>{d.reversals}</dt>
            <dd>
              {s.payments.reversals_count} · {s.payments.reversals_total}
            </dd>
          </div>
        </dl>

        <p className="muted">{d.expenses}</p>
        <dl className="print-grid">
          <div>
            <dt>{d.cashTotal}</dt>
            <dd>{s.expenses.cash_total}</dd>
          </div>
          <div>
            <dt>{d.nonCashTotal}</dt>
            <dd>{s.expenses.non_cash_total}</dd>
          </div>
          <div>
            <dt>{d.voided}</dt>
            <dd>
              {s.expenses.voided_count} · {s.expenses.voided_total}
            </dd>
          </div>
          <div>
            <dt>{d.reversals}</dt>
            <dd>
              {s.expenses.reversals_count} · {s.expenses.reversals_total}
            </dd>
          </div>
        </dl>

        <p className="muted">{d.restaurant}</p>
        <dl className="print-grid">
          <div>
            <dt>{d.restaurantSales}</dt>
            <dd>{s.restaurant.restaurant_sales}</dd>
          </div>
          <div>
            <dt>{d.cafeSales}</dt>
            <dd>{s.restaurant.cafe_sales}</dd>
          </div>
          <div>
            <dt>{d.settlements}</dt>
            <dd>
              {s.restaurant.direct_settlements.count} ·{" "}
              {s.restaurant.direct_settlements.total}
            </dd>
          </div>
          <div>
            <dt>{d.folioPostings}</dt>
            <dd>
              {s.restaurant.folio_postings.count} · {s.restaurant.folio_postings.total}
            </dd>
          </div>
        </dl>

        <p className="muted">{d.folios}</p>
        <dl className="print-grid">
          <div>
            <dt>{d.openFoliosCount}</dt>
            <dd>{s.folios.open_folios_count}</dd>
          </div>
          <div>
            <dt>{d.totalBalance}</dt>
            <dd>{s.folios.total_balance}</dd>
          </div>
          <div>
            <dt>{d.positiveBalance}</dt>
            <dd>
              {s.folios.positive_balance_count} · {s.folios.positive_balance_amount}
            </dd>
          </div>
          <div>
            <dt>{d.negativeBalance}</dt>
            <dd>
              {s.folios.negative_balance_count} · {s.folios.negative_balance_amount}
            </dd>
          </div>
          <div>
            <dt>{d.zeroBalance}</dt>
            <dd>{s.folios.zero_balance_count}</dd>
          </div>
        </dl>

        <p className="muted">{d.unassigned}</p>
        <dl className="print-grid">
          <div>
            <dt>{d.netCash}</dt>
            <dd>{um.net_cash}</dd>
          </div>
          <div>
            <dt>{d.paymentsCash}</dt>
            <dd>
              {um.cash_payments.count} · {um.cash_payments.total}
            </dd>
          </div>
          <div>
            <dt>{d.expensesCash}</dt>
            <dd>
              {um.cash_expenses.count} · {um.cash_expenses.total}
            </dd>
          </div>
          <div>
            <dt>{d.reversals}</dt>
            <dd>
              {um.cash_payment_reversals.total} / {um.cash_expense_reversals.total}
            </dd>
          </div>
        </dl>

        <p className="muted">{d.operations}</p>
        <dl className="print-grid">
          <div>
            <dt>{codeLabel("in_house_stays")}</dt>
            <dd>{s.operations.in_house_stays}</dd>
          </div>
          <div>
            <dt>{codeLabel("arrivals_not_checked_in")}</dt>
            <dd>{s.operations.arrivals_not_checked_in}</dd>
          </div>
          <div>
            <dt>{codeLabel("overdue_departures")}</dt>
            <dd>{s.operations.overdue_departures}</dd>
          </div>
          <div>
            <dt>{codeLabel("open_housekeeping_tasks")}</dt>
            <dd>{s.operations.open_housekeeping_tasks}</dd>
          </div>
          <div>
            <dt>{codeLabel("open_maintenance_requests")}</dt>
            <dd>{s.operations.open_maintenance_requests}</dd>
          </div>
          <div>
            <dt>{codeLabel("not_ready_rooms")}</dt>
            <dd>{s.operations.not_ready_rooms}</dd>
          </div>
          <div>
            <dt>{codeLabel("open_lost_found_records")}</dt>
            <dd>{s.operations.open_lost_found_records}</dd>
          </div>
        </dl>

        {s.exceptions.warnings.length > 0 ? (
          <>
            <p className="muted">{d.warningsTitle}</p>
            <dl className="print-grid">
              {s.exceptions.warnings.map((w, i) => (
                <div key={`w-${i}`}>
                  <dt>{codeLabel(w.code)}</dt>
                  <dd>{w.count ?? "—"}</dd>
                </div>
              ))}
            </dl>
          </>
        ) : null}
        {s.exceptions.informational_alerts.length > 0 ? (
          <>
            <p className="muted">{d.infoTitle}</p>
            <dl className="print-grid">
              {s.exceptions.informational_alerts.map((a, i) => (
                <div key={`i-${i}`}>
                  <dt>{codeLabel(a.code)}</dt>
                  <dd>{a.count ?? a.total_balance ?? a.net_cash ?? "—"}</dd>
                </div>
              ))}
            </dl>
          </>
        ) : null}
      </PrintDocumentLayout>
    </PrintModal>
  );
}
