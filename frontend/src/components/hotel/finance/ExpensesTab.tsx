"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  Ban,
  CalendarDays,
  CreditCard,
  Pencil,
  PiggyBank,
  Plus,
  Printer,
  RotateCcw,
  SearchX,
  UserRound,
  Wallet,
} from "lucide-react";

import { useQuickAction } from "@/lib/useQuickAction";

import {
  Alert, Badge, Button, Card, EmptyState, ErrorState, FilterBar, FormField,
  Input, LoadingState, Modal, Pagination, PrintDocumentLayout, SectionHeader,
  Select, Textarea, useToast,
} from "@/components/ui";
import {
  OperationCard,
  type OperationFact,
  type OperationMenuItem,
} from "@/components/hotel/operations/OperationCard";
import {
  createExpense, getExpenseVoucher, listExpenses, reverseExpense, updateExpense, voidExpense,
  type ExpenseBody, type ExpenseUpdateBody,
} from "@/lib/api/finance";
import { isApiError, messageForError } from "@/lib/api/errors";
import type { Expense, HotelHeader } from "@/lib/api/types";
import { formatDate, formatDateTime, formatMoney, postingStatusTone } from "@/lib/format";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { PrintModal, VoidDialog } from "./shared";

const PAGE_SIZE = 25;
const CATEGORIES = ["operations", "maintenance", "supplies", "marketing", "salary", "utilities", "other"] as const;
const METHODS = ["cash", "card", "bank_transfer", "electronic", "other"] as const;

/** Cosmetic permission gate — every API re-checks server-side regardless. */
function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

export function ExpensesTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const e = t.finance.expenses;
  const can = useCan();

  const [rows, setRows] = useState<Expense[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState("");
  // `search` is what the user is typing; `appliedSearch` is what the SERVER is
  // currently filtered by. Only the latter drives a request.
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Flips true after the FIRST settled load — the initial load owns the full
  // LoadingState/ErrorState; later fetches keep the cards mounted (a11y).
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  const [creating, setCreating] = useState(false);
  const [editTarget, setEditTarget] = useState<Expense | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Expense | null>(null);
  const [voucher, setVoucher] = useState<{ hotel: HotelHeader; expense: Expense } | null>(null);

  // Topbar quick action: ?action=new opens the EXISTING expense modal once.
  useQuickAction("new", () => setCreating(true));

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
      const data = await listExpenses({
        page,
        category: category || undefined,
        search: appliedSearch || undefined,
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
  }, [page, category, appliedSearch, t, notify]);

  useEffect(() => { load(); }, [load]);

  // DEBOUNCE the search (~350ms after typing stops) so a five-letter term is one
  // round-trip, not five. Applying the term and resetting to page 1 in the SAME
  // tick keeps it to a single render/fetch; the seq-guard discards stale replies.
  useEffect(() => {
    const id = setTimeout(() => {
      setAppliedSearch(search.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(id);
  }, [search]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // After an ACTION-triggered reload settles, restore focus to the stable results
  // anchor if the acting control (a card menu item) unmounted.
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

  const filtering = appliedSearch !== "" || category !== "";
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: t.finance.categories[c] }));

  const showInitialLoading = loading && !hasLoadedOnce;
  const showInitialError = !showInitialLoading && !hasLoadedOnce && error !== null;
  const backgroundRefreshing = loading && hasLoadedOnce;

  // DEBOUNCED live-region text: announce only once the result has SETTLED and
  // stayed settled for ~450ms so typing does not fire a burst of announcements.
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

  async function openVoucher(id: number) {
    try { const r = await getExpenseVoucher(id); setVoucher({ hotel: r.hotel, expense: r.expense }); }
    catch (err) { notify(messageForError(err, t), "error"); }
  }

  /**
   * UNIFIED CANCEL (UI-only). The user sees ONE "Cancel expense" action; the
   * backend decides which endpoint applies because the void / reverse windows are
   * MUTUALLY EXCLUSIVE (same open business day => void; day rolled over/closed =>
   * reverse). We try the endpoint the caller is primarily permitted for and, on
   * the SPECIFIC typed window-409, transparently retry the other with the same
   * reason. Any other error propagates to VoidDialog's messageForError.
   */
  async function cancelExpense(target: Expense, reason: string) {
    const canVoid = can("expenses.void");
    const canReverse = can("expenses.reverse");
    if (canVoid) {
      try {
        await voidExpense(target.id, reason);
        return;
      } catch (err) {
        // Same business day rolled over → the void window is CLOSED and the
        // reversal endpoint is the one that now applies. Retry transparently.
        if (isApiError(err) && err.code === "void_window_closed" && canReverse) {
          await reverseExpense(target.id, reason);
          return;
        }
        throw err;
      }
    }
    // The caller can only reverse (the button gate guarantees at least one of the
    // two permissions before we ever get here).
    try {
      await reverseExpense(target.id, reason);
    } catch (err) {
      // Symmetric guard: the day is still OPEN so reverse is rejected — fall back
      // to void only if permitted (unreachable while !canVoid; kept for symmetry).
      if (isApiError(err) && err.code === "void_window_open" && canVoid) {
        await voidExpense(target.id, reason);
        return;
      }
      throw err;
    }
  }

  function renderCard(r: Expense) {
    const facts: OperationFact[] = [
      {
        key: "amount",
        label: e.amount,
        value: <bdi dir="ltr">{formatMoney(r.amount, r.currency, locale)}</bdi>,
        icon: Wallet,
      },
      {
        key: "date",
        label: e.date,
        value: formatDate(r.business_date ?? r.paid_at, locale),
        icon: CalendarDays,
      },
      {
        key: "method",
        label: e.method,
        value: t.finance.methods[r.method],
        icon: CreditCard,
      },
      {
        key: "employee",
        label: e.employee,
        value: r.created_by ? <bdi>{r.created_by}</bdi> : "—",
        icon: UserRound,
      },
    ];
    // Reversal-link indicators — only surface on a reversed/reversal voucher.
    if (r.reverses_number) {
      facts.push({
        key: "reversalOf",
        label: e.reversalOf,
        value: <bdi dir="ltr">↩ {r.reverses_number}</bdi>,
        icon: RotateCcw,
      });
    }
    if (r.reversed_by_number) {
      facts.push({
        key: "reversedBy",
        label: e.reversedBy,
        value: <bdi dir="ltr">↩ {r.reversed_by_number}</bdi>,
        icon: RotateCcw,
      });
    }

    // ONE primary affordance (Print, always) + a "More" menu for the rest — never
    // a wall of buttons. Edit/Cancel are gated cosmetically; the API re-checks.
    const menu: OperationMenuItem[] = [];
    if (r.status === "posted" && can("expenses.update")) {
      menu.push({ key: "edit", label: e.edit, icon: Pencil, onSelect: () => setEditTarget(r) });
    }
    // Show "Cancel expense" on a faithful union of the two original gates: void
    // was offered on any posted row, but reverse was NOT offered on a row that is
    // itself a reversal or has already been reversed. Preserving that guard keeps
    // a reverse-only user from clicking a cancel the backend can only reject.
    const canReverseThis = can("expenses.reverse") && r.reverses === null && !r.reversed_by_number;
    if (r.status === "posted" && (can("expenses.void") || canReverseThis)) {
      menu.push({ key: "cancel", label: e.cancel, icon: Ban, danger: true, onSelect: () => setCancelTarget(r) });
    }

    return (
      <OperationCard
        accent={r.status === "voided" ? "danger" : "primary"}
        number={r.expense_number}
        title={t.finance.categories[r.category]}
        ariaLabel={`${t.finance.tabs.expenses} ${r.expense_number}`}
        moreLabel={e.more}
        badges={<Badge tone={postingStatusTone(r.status)}>{t.finance.postingStatus[r.status]}</Badge>}
        facts={facts}
        note={r.description || null}
        primary={{ label: e.voucher, icon: Printer, variant: "secondary", onClick: () => openVoucher(r.id) }}
        menu={menu}
      />
    );
  }

  return (
    <>
      <Card>
        <SectionHeader title={t.finance.tabs.expenses} />
        <form onSubmit={(ev) => { ev.preventDefault(); setAppliedSearch(search.trim()); setPage(1); }}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="exp-search">
              <Input id="exp-search" value={search} placeholder={e.searchPlaceholder} onChange={(ev) => setSearch(ev.target.value)} />
            </FormField>
            <FormField label={e.category} htmlFor="exp-cat">
              <Select id="exp-cat" value={category} placeholder={t.common.all} options={categoryOptions} onChange={(ev) => { setPage(1); setCategory(ev.target.value); }} />
            </FormField>
            <div className="filter-bar__actions cluster">
              <Button icon={Plus} onClick={() => setCreating(true)}>{e.add}</Button>
            </div>
          </FilterBar>
        </form>

        {/* STABLE polite live region — always mounted; announces the settled
            result count by a text change. */}
        <div className="sr-only" aria-live="polite" aria-atomic="true" data-testid="exp-results-announce">
          {announcement}
        </div>

        {showInitialLoading ? <LoadingState label={t.common.loading} /> : null}
        {showInitialError ? (
          <ErrorState title={t.states.errorTitle} message={error ?? ""} retryLabel={t.common.retry} onRetry={load} />
        ) : null}
        {!showInitialLoading && !showInitialError ? (
          <div className="op-results" ref={resultsRef} tabIndex={-1} aria-label={t.finance.tabs.expenses}>
            <div className="op-results__status" role="status" aria-live="polite">
              {backgroundRefreshing ? (
                <span className="op-results__searching">
                  <span className="spinner" aria-hidden="true" />
                  <span>{t.operations.updating}</span>
                </span>
              ) : null}
            </div>
            {rows.length === 0 ? (
              // A search/filter that matched nothing is NOT the same as an empty
              // ledger — saying "No expenses yet" while a filter is active hides
              // the way out (clear the search or category).
              filtering ? (
                <EmptyState title={e.noMatches} hint={e.noMatchesHint} icon={SearchX} />
              ) : (
                <EmptyState
                  title={e.empty}
                  hint={e.emptyHint}
                  icon={PiggyBank}
                  action={<Button icon={Plus} onClick={() => setCreating(true)}>{e.add}</Button>}
                />
              )
            ) : (
              <div className="op-grid" role="list" aria-label={t.finance.tabs.expenses} aria-busy={backgroundRefreshing}>
                {rows.map((r) => (
                  <div role="listitem" key={r.id}>
                    {renderCard(r)}
                  </div>
                ))}
              </div>
            )}
            {/* Pagination stays MOUNTED whenever a filter is active, even on an
                empty result, so a user who filtered on page N still has a control
                to get back. Hidden only for a genuinely empty, unfiltered ledger. */}
            {rows.length > 0 || filtering ? (
              <Pagination
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                labels={{
                  previous: t.pagination.previous,
                  next: t.pagination.next,
                  status: t.pagination.page.replace("{page}", String(page)).replace("{total}", String(totalPages)),
                }}
              />
            ) : null}
          </div>
        ) : null}
      </Card>

      <ExpenseModal open={creating} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); notify(t.finance.saved); setPage(1); load(); }} />
      <ExpenseEditModal expense={editTarget} onClose={() => setEditTarget(null)} onSaved={() => { setEditTarget(null); notify(t.finance.saved); reloadAfterAction(); }} />

      {/* UNIFIED CANCEL — single reason-required dialog; the routing happens in
          cancelExpense(). Never two technical Void/Reverse buttons. */}
      <VoidDialog
        open={cancelTarget !== null}
        title={e.cancel}
        confirmLabel={e.cancel}
        description={e.cancelHint}
        onClose={() => setCancelTarget(null)}
        onConfirm={async (reason) => {
          if (!cancelTarget) return;
          await cancelExpense(cancelTarget, reason);
          setCancelTarget(null);
          notify(e.cancelled);
          reloadAfterAction();
        }}
      />

      <PrintModal open={voucher !== null} title={t.finance.print.voucherTitle} onClose={() => setVoucher(null)}>
        {voucher ? (
          <PrintDocumentLayout
            hotelName={voucher.hotel.hotel_name}
            hotelAddress={voucher.hotel.address}
            hotelPhone={voucher.hotel.phone}
            docTitle={t.finance.print.voucherTitle}
            docNumber={voucher.expense.expense_number}
            meta={[
              { label: t.finance.print.vendor, value: voucher.expense.vendor_name || "—" },
              { label: e.category, value: t.finance.categories[voucher.expense.category] },
              { label: t.finance.print.status, value: t.finance.postingStatus[voucher.expense.status] },
              { label: t.finance.print.businessDate, value: formatDate(voucher.expense.business_date ?? voucher.expense.paid_at, locale) },
              { label: t.finance.print.executedAt, value: formatDateTime(voucher.expense.paid_at, locale) },
              ...(voucher.expense.shift_number
                ? [{ label: t.finance.print.shift, value: voucher.expense.shift_number }]
                : []),
              { label: t.finance.print.method, value: t.finance.methods[voucher.expense.method] },
              { label: t.finance.print.amount, value: <strong>{formatMoney(voucher.expense.amount, voucher.expense.currency, locale)}</strong> },
              { label: e.description, value: voucher.expense.description },
              ...(voucher.expense.reference
                ? [{ label: t.finance.print.reference, value: voucher.expense.reference }]
                : []),
              ...(voucher.expense.reverses_number
                ? [{ label: t.finance.print.reversalOf, value: voucher.expense.reverses_number }]
                : []),
              ...(voucher.expense.reversed_by_number
                ? [{ label: t.finance.print.reversedBy, value: voucher.expense.reversed_by_number }]
                : []),
              ...(voucher.expense.status === "voided"
                ? [
                    { label: t.finance.print.voidReason, value: voucher.expense.void_reason || "—" },
                    { label: t.finance.print.voidedBy, value: voucher.expense.voided_by || "—" },
                  ]
                : []),
              ...(voucher.expense.created_by
                ? [{ label: t.finance.print.createdBy, value: voucher.expense.created_by }]
                : []),
            ]}
            notes={voucher.expense.notes || undefined}
            notesLabel={t.finance.print.notes}
            signatureLabel={t.finance.print.signature}
          />
        ) : null}
      </PrintModal>
    </>
  );
}

function ExpenseModal({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const e = t.finance.expenses;
  const [form, setForm] = useState<ExpenseBody>({ category: "supplies", description: "", amount: "", method: "cash" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setForm({ category: "supplies", description: "", amount: "", method: "cash", vendor_name: "", reference: "", notes: "" }); setError(null); }
  }, [open]);

  function set<K extends keyof ExpenseBody>(k: K, v: ExpenseBody[K]) { setForm((p) => ({ ...p, [k]: v })); }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!form.description?.trim() || !form.amount) return setError(t.errors.validation);
    setBusy(true);
    try {
      await createExpense({ ...form, description: form.description.trim() });
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: t.finance.categories[c] }));
  const methodOptions = METHODS.map((m) => ({ value: m, label: t.finance.methods[m] }));

  return (
    <Modal open={open} onClose={onClose} title={e.createTitle} closeLabel={t.common.close}
      footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button><Button form="exp-form" type="submit" loading={busy}>{e.submit}</Button></>}>
      <form id="exp-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={e.category} htmlFor="e-cat"><Select id="e-cat" value={form.category ?? "other"} options={categoryOptions} onChange={(ev) => set("category", ev.target.value)} /></FormField>
          <FormField label={e.amount} htmlFor="e-amt"><Input id="e-amt" type="number" step="0.01" value={form.amount ?? ""} onChange={(ev) => set("amount", ev.target.value)} /></FormField>
          <FormField label={e.method} htmlFor="e-method"><Select id="e-method" value={form.method ?? "cash"} options={methodOptions} onChange={(ev) => set("method", ev.target.value)} /></FormField>
          <FormField label={e.vendor} htmlFor="e-vendor"><Input id="e-vendor" value={form.vendor_name ?? ""} onChange={(ev) => set("vendor_name", ev.target.value)} /></FormField>
          <FormField label={e.reference} htmlFor="e-ref"><Input id="e-ref" value={form.reference ?? ""} onChange={(ev) => set("reference", ev.target.value)} /></FormField>
        </div>
        <FormField label={e.description} htmlFor="e-desc"><Input id="e-desc" value={form.description ?? ""} onChange={(ev) => set("description", ev.target.value)} /></FormField>
        <FormField label={t.finance.folios.notes} htmlFor="e-notes"><Textarea id="e-notes" value={form.notes ?? ""} onChange={(ev) => set("notes", ev.target.value)} /></FormField>
        {/* The employee, time, business date and shift are DERIVED by the server —
            surface that as read-only context so the user knows they cannot set
            them here (currency is server-derived too; no picker). */}
        <p className="muted">{e.autoNote}</p>
      </form>
    </Modal>
  );
}

/** Edits the four descriptive fields only — the server rejects anything else
 *  and enforces the open-business-day window (409 void_window_closed). */
function ExpenseEditModal({ expense, onClose, onSaved }: { expense: Expense | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const e = t.finance.expenses;
  const [form, setForm] = useState<ExpenseUpdateBody>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (expense) {
      setForm({ description: expense.description, notes: expense.notes, reference: expense.reference, vendor_name: expense.vendor_name });
      setError(null);
    }
  }, [expense]);

  function set<K extends keyof ExpenseUpdateBody>(k: K, v: ExpenseUpdateBody[K]) { setForm((p) => ({ ...p, [k]: v })); }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!expense) return;
    setError(null);
    if (!form.description?.trim()) return setError(t.errors.validation);
    setBusy(true);
    try {
      await updateExpense(expense.id, { ...form, description: form.description.trim() });
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={expense !== null} onClose={onClose} title={e.editTitle} closeLabel={t.common.close}
      footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button><Button form="exp-edit-form" type="submit" loading={busy}>{e.editSave}</Button></>}>
      <form id="exp-edit-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={e.description} htmlFor="ee-desc"><Input id="ee-desc" value={form.description ?? ""} onChange={(ev) => set("description", ev.target.value)} /></FormField>
        <div className="form-grid">
          <FormField label={e.vendor} htmlFor="ee-vendor"><Input id="ee-vendor" value={form.vendor_name ?? ""} onChange={(ev) => set("vendor_name", ev.target.value)} /></FormField>
          <FormField label={e.reference} htmlFor="ee-ref"><Input id="ee-ref" value={form.reference ?? ""} onChange={(ev) => set("reference", ev.target.value)} /></FormField>
        </div>
        <FormField label={t.finance.folios.notes} htmlFor="ee-notes"><Textarea id="ee-notes" value={form.notes ?? ""} onChange={(ev) => set("notes", ev.target.value)} /></FormField>
      </form>
    </Modal>
  );
}
