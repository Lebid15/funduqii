"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  Ban,
  CalendarDays,
  ClipboardList,
  Clock,
  Coins,
  Lock,
  PlayCircle,
  Printer,
  Scale,
  SearchX,
  Wallet,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
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
} from "@/components/ui";
import {
  OperationCard,
  type OperationFact,
  type OperationMenuItem,
  type OperationPrimaryAction,
} from "@/components/hotel/operations/OperationCard";
import { cancelShift, getShiftStatement, getShiftSummary, listShifts } from "@/lib/api/shifts";
import { messageForError } from "@/lib/api/errors";
import type { ShiftCashSummary, ShiftListItem, ShiftStatement, ShiftStatus } from "@/lib/api/types";
import { formatDateTime, shiftStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { CloseShiftModal, OpenShiftModal, ShiftStatementPrintModal } from "./CurrentShiftTab";

const PAGE_SIZE = 25;
const STATUSES: ShiftStatus[] = ["open", "closed", "cancelled"];

export function ShiftsTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
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
  const [announcement, setAnnouncement] = useState("");
  // Flips true after the FIRST settled load — the initial load owns the full
  // LoadingState/ErrorState; later fetches keep the cards mounted (a11y).
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

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
  const [statementTarget, setStatementTarget] = useState<ShiftStatement | null>(null);

  const loadedOnceRef = useRef(false);
  const mountedRef = useRef(true);
  const seqRef = useRef(0);
  const resultsRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef(false);

  const load = useCallback(async () => {
    const seq = (seqRef.current += 1);
    setLoading(true);
    setError(null);
    try {
      const data = await listShifts({
        page,
        search: query || undefined,
        status: status || undefined,
        business_date: date || undefined,
      });
      if (seqRef.current !== seq) return;
      setRows(data.results);
      setCount(data.count);
      loadedOnceRef.current = true;
      setHasLoadedOnce(true);
    } catch (err) {
      if (seqRef.current !== seq) return;
      const message = messageForError(err, t);
      // BACKGROUND refetch failure keeps the cards + a non-blocking toast; the
      // full ErrorState + retry is reserved for the initial load.
      if (loadedOnceRef.current) notify(message, "error");
      else setError(message);
    } finally {
      if (mountedRef.current && seqRef.current === seq) setLoading(false);
    }
  }, [page, query, status, date, t, notify]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // After an ACTION-triggered reload settles, restore focus to the stable
  // results anchor if the acting control unmounted.
  useEffect(() => {
    if (loading || !restoreFocusRef.current) return;
    restoreFocusRef.current = false;
    const active = document.activeElement as HTMLElement | null;
    if (!active || active === document.body || !active.isConnected) {
      resultsRef.current?.focus();
    }
  }, [rows, loading]);

  const reloadAfterAction = useCallback(() => {
    restoreFocusRef.current = true;
    return load();
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

  async function openStatement(row: ShiftListItem) {
    try {
      setStatementTarget(await getShiftStatement(row.id));
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  const filtering = query !== "" || status !== "" || date !== "";
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: t.shifts.status[s] }));

  const showInitialLoading = loading && !hasLoadedOnce;
  const showInitialError = !showInitialLoading && !hasLoadedOnce && error !== null;
  const backgroundRefreshing = loading && hasLoadedOnce;

  // DEBOUNCED settled-count live region (announce once the list stops moving).
  const settledCount = !loading && hasLoadedOnce ? rows.length : null;
  useEffect(() => {
    if (settledCount === null) return;
    const id = setTimeout(() => {
      setAnnouncement(
        settledCount === 0
          ? t.operations.noResults
          : t.operations.resultsCount.replace("{count}", String(settledCount)),
      );
    }, 450);
    return () => clearTimeout(id);
  }, [settledCount, t]);

  function renderCard(row: ShiftListItem) {
    const facts: OperationFact[] = [
      { key: "date", label: l.businessDate, value: row.business_date, icon: CalendarDays },
      {
        key: "opened",
        label: l.openedAt,
        value: formatDateTime(row.opened_at, locale),
        icon: Clock,
      },
    ];
    if (row.closed_at) {
      facts.push({
        key: "closed",
        label: l.closedAt,
        value: formatDateTime(row.closed_at, locale),
        icon: Lock,
      });
    }
    facts.push(
      {
        key: "opening",
        label: l.opening,
        value: <bdi dir="ltr">{row.opening_cash_amount}</bdi>,
        icon: Wallet,
      },
      {
        key: "expected",
        label: l.expected,
        value: <bdi dir="ltr">{row.expected_cash_amount}</bdi>,
        icon: Coins,
      },
      {
        key: "actual",
        label: l.actual,
        value: <bdi dir="ltr">{row.actual_cash_amount ?? "—"}</bdi>,
        icon: Coins,
      },
      {
        key: "difference",
        label: l.difference,
        icon: Scale,
        // The difference is only meaningful once the drawer is counted (closed):
        // for an open/cancelled shift the server value carries no settled meaning.
        value:
          row.status === "closed" ? (
            <Badge tone={row.cash_difference === "0.00" ? "success" : "warning"}>
              {row.cash_difference}
            </Badge>
          ) : (
            "—"
          ),
      },
    );

    const printItem: OperationMenuItem = {
      key: "print",
      label: t.shifts.print.printStatement,
      icon: Printer,
      onSelect: () => openStatement(row),
    };

    let primary: OperationPrimaryAction | null;
    const menu: OperationMenuItem[] = [];
    if (row.status === "open") {
      // The one operational next step for an open shift is to close it.
      primary = {
        label: t.shifts.current.close,
        icon: Lock,
        onClick: () => openSummary(row, true),
      };
      menu.push(
        {
          key: "summary",
          label: l.summary,
          icon: ClipboardList,
          onSelect: () => openSummary(row, false),
        },
        printItem,
        {
          key: "cancel",
          label: t.common.cancel,
          icon: Ban,
          danger: true,
          onSelect: () => setCancelTarget(row),
        },
      );
    } else {
      primary = {
        label: l.summary,
        icon: ClipboardList,
        variant: "secondary",
        onClick: () => openSummary(row, false),
      };
      menu.push(printItem);
    }

    return (
      <OperationCard
        accent={shiftStatusTone(row.status)}
        number={row.shift_number}
        title={<bdi>{row.responsible_name || "—"}</bdi>}
        ariaLabel={`${l.title} ${row.shift_number}`}
        moreLabel={t.operations.moreActions}
        badges={
          <Badge tone={shiftStatusTone(row.status)}>{t.shifts.status[row.status]}</Badge>
        }
        facts={facts}
        primary={primary}
        menu={menu}
      />
    );
  }

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
            setQuery(search.trim());
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

        {/* STABLE polite live region — announces the settled result count. */}
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          {announcement}
        </div>

        {showInitialLoading ? <LoadingState label={t.common.loading} /> : null}
        {showInitialError ? (
          <ErrorState
            title={t.states.errorTitle}
            message={error ?? ""}
            retryLabel={t.common.retry}
            onRetry={load}
          />
        ) : null}
        {!showInitialLoading && !showInitialError ? (
          <div className="op-results" ref={resultsRef} tabIndex={-1} aria-label={l.title}>
            <div className="op-results__status" role="status" aria-live="polite">
              {backgroundRefreshing ? (
                <span className="op-results__searching">
                  <span className="spinner" aria-hidden="true" />
                  <span>{t.operations.updating}</span>
                </span>
              ) : null}
            </div>
            {rows.length === 0 ? (
              filtering ? (
                <EmptyState title={l.noMatches} hint={l.noMatchesHint} icon={SearchX} />
              ) : (
                <EmptyState title={l.empty} hint={l.emptyHint} icon={Clock} />
              )
            ) : (
              <div
                className="op-grid"
                role="list"
                aria-label={l.title}
                aria-busy={backgroundRefreshing}
              >
                {rows.map((row) => (
                  <div role="listitem" key={row.id}>
                    {renderCard(row)}
                  </div>
                ))}
              </div>
            )}
            {rows.length > 0 || filtering ? (
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
            ) : null}
          </div>
        ) : null}
      </Card>

      <OpenShiftModal
        open={openModal}
        onClose={() => setOpenModal(false)}
        onDone={() => {
          setOpenModal(false);
          notify(t.shifts.msgs.opened);
          reloadAfterAction();
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
            reloadAfterAction();
          }}
        />
      ) : null}
      <CancelShiftModal
        shift={cancelTarget}
        onClose={() => setCancelTarget(null)}
        onDone={() => {
          setCancelTarget(null);
          notify(t.shifts.msgs.cancelled);
          reloadAfterAction();
        }}
      />
      <SummaryModal state={summaryTarget} onClose={() => setSummaryTarget(null)} />
      <ShiftStatementPrintModal
        statement={statementTarget}
        onClose={() => setStatementTarget(null)}
      />
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
