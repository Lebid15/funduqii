"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import {
  Ban,
  CalendarDays,
  CreditCard,
  Paperclip,
  Pencil,
  PiggyBank,
  Plus,
  Printer,
  RotateCcw,
  SearchX,
  Trash2,
  Upload,
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
import { PrintModal, VoidDialog } from "@/components/hotel/finance/shared";
import {
  createExpense, deleteExpenseAttachment, getExpenseAttachmentBlobUrl, getExpenseMeta,
  getExpenseVoucher, listExpenses, listExpenseTypes, mintIdempotencyKey, reverseExpense,
  updateExpense, uploadExpenseAttachment, voidExpense,
  type ExpenseCreateBody, type ExpenseUpdateBody,
} from "@/lib/api/expenses";
import { messageForError } from "@/lib/api/errors";
import type { Expense, ExpenseType, HotelHeader } from "@/lib/api/types";
import { formatDate, formatDateTime, formatMoney, postingStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { EXPENSE_METHODS, RECEIPT_ACCEPT, useCan } from "./shared";

const PAGE_SIZE = 25;

/** Show the base amount, plus the ORIGINAL amount+currency when the expense was
 * entered in a foreign currency (RTL-safe LTR money via <bdi>). */
function AmountValue({ r }: { r: Expense }) {
  const { locale } = useI18n();
  const base = <bdi dir="ltr">{formatMoney(r.amount, r.currency, locale)}</bdi>;
  if (r.original_currency && r.original_currency !== r.currency && r.original_amount) {
    return (
      <span>
        {base}{" "}
        <span className="muted">
          (<bdi dir="ltr">{formatMoney(r.original_amount, r.original_currency, locale)}</bdi>)
        </span>
      </span>
    );
  }
  return base;
}

export function ExpensesTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const e = t.expenses;
  const can = useCan();

  const [rows, setRows] = useState<Expense[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [typeFilter, setTypeFilter] = useState("");
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [types, setTypes] = useState<ExpenseType[]>([]);
  const [announcement, setAnnouncement] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  const [creating, setCreating] = useState(false);
  const [editTarget, setEditTarget] = useState<Expense | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Expense | null>(null);
  const [correctTarget, setCorrectTarget] = useState<Expense | null>(null);
  const [voucher, setVoucher] = useState<{ hotel: HotelHeader; expense: Expense } | null>(null);

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
        expense_type: typeFilter ? Number(typeFilter) : undefined,
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
      if (loadedOnceRef.current) notify(message, "error");
      else setError(message);
    } finally {
      if (mountedRef.current && seqRef.current === seq) setLoading(false);
    }
  }, [page, typeFilter, appliedSearch, t, notify]);

  useEffect(() => { load(); }, [load]);

  // Active types for the filter dropdown (and available to modals via props).
  useEffect(() => {
    listExpenseTypes().then((list) => { if (mountedRef.current) setTypes(list); }).catch(() => {});
  }, []);

  useEffect(() => {
    const id = setTimeout(() => { setAppliedSearch(search.trim()); setPage(1); }, 350);
    return () => clearTimeout(id);
  }, [search]);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

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

  const filtering = appliedSearch !== "" || typeFilter !== "";
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const typeOptions = useMemo(
    () => types.map((ty) => ({ value: String(ty.id), label: ty.name })),
    [types],
  );

  const showInitialLoading = loading && !hasLoadedOnce;
  const showInitialError = !showInitialLoading && !hasLoadedOnce && error !== null;
  const backgroundRefreshing = loading && hasLoadedOnce;

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

  async function openAttachment(id: number) {
    try {
      const url = await getExpenseAttachmentBlobUrl(id);
      // NOTE: passing "noopener" to window.open makes it return null BY SPEC, so
      // it can never be used to detect a blocked pop-up. Open without the
      // feature and sever `opener` manually — same protection, real detection.
      const win = window.open(url, "_blank");
      if (win) {
        win.opener = null;
        // Revoke once the viewer has had a chance to load the bytes.
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      } else {
        URL.revokeObjectURL(url);
        notify(e.attachmentPopupBlocked, "error");
      }
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  // Attach / replace / remove the receipt (before close; the backend enforces
  // the open-day window and returns a clear error otherwise). The hidden picker
  // is triggered by a stable DOM id (no React ref reachable from render), and
  // the target expense is held in state so the change handler reads the latest.
  const RECEIPT_PICKER_ID = "exp-receipt-picker";
  const [replaceTargetId, setReplaceTargetId] = useState<number | null>(null);
  function beginReplace(id: number) {
    setReplaceTargetId(id);
    (document.getElementById(RECEIPT_PICKER_ID) as HTMLInputElement | null)?.click();
  }
  async function onReplaceFile(ev: ChangeEvent<HTMLInputElement>) {
    const file = ev.target.files?.[0];
    ev.target.value = "";
    if (!file || replaceTargetId === null) return;
    try {
      await uploadExpenseAttachment(replaceTargetId, file);
      notify(e.attachmentSaved);
      reloadAfterAction();
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }
  async function removeReceipt(id: number) {
    try {
      await deleteExpenseAttachment(id);
      notify(e.attachmentRemoved);
      // Optimistic local update (avoids a full reload from a menu action).
      setRows((prev) => prev.map((x) => (x.id === id ? { ...x, has_attachment: false } : x)));
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  function renderCard(r: Expense) {
    const facts: OperationFact[] = [
      { key: "amount", label: e.amount, value: <AmountValue r={r} />, icon: Wallet },
      { key: "date", label: e.date, value: formatDate(r.business_date ?? r.paid_at, locale), icon: CalendarDays },
      { key: "method", label: e.method, value: t.finance.methods[r.method], icon: CreditCard },
      { key: "employee", label: e.employee, value: r.created_by ? <bdi>{r.created_by}</bdi> : "—", icon: UserRound },
    ];
    if (r.reverses_number) {
      facts.push({ key: "reversalOf", label: e.reversalOf, value: <bdi dir="ltr">↩ {r.reverses_number}</bdi>, icon: RotateCcw });
    }
    if (r.reversed_by_number) {
      facts.push({ key: "reversedBy", label: e.reversedBy, value: <bdi dir="ltr">↩ {r.reversed_by_number}</bdi>, icon: RotateCcw });
    }

    const menu: OperationMenuItem[] = [];
    if (r.has_attachment) {
      menu.push({ key: "attachment", label: e.openAttachment, icon: Paperclip, onSelect: () => openAttachment(r.id) });
    }
    const editable = r.status === "posted" && r.reverses === null && can("expenses.update");
    if (editable) {
      menu.push({ key: "edit", label: e.edit, icon: Pencil, onSelect: () => setEditTarget(r) });
      menu.push({
        key: "replaceAttach",
        label: r.has_attachment ? e.replaceAttachment : e.addAttachment,
        icon: Upload,
        onSelect: () => beginReplace(r.id),
      });
      if (r.has_attachment) {
        menu.push({ key: "removeAttach", label: e.removeAttachment, icon: Trash2, danger: true, onSelect: () => removeReceipt(r.id) });
      }
    }
    // Distinct correction actions — NEVER an auto void→reverse fallback (owner
    // decision). "Cancel" = void inside the open day; "Corrective movement" =
    // a linked counter-voucher AFTER the day closed. The backend enforces which
    // one applies and returns a clear typed error for the other.
    if (r.status === "posted" && can("expenses.void")) {
      menu.push({ key: "cancel", label: e.cancel, icon: Ban, danger: true, onSelect: () => setCancelTarget(r) });
    }
    const canCorrect = can("expenses.reverse") && r.reverses === null && !r.reversed_by_number;
    if (r.status === "posted" && canCorrect) {
      menu.push({ key: "correct", label: e.corrective, icon: RotateCcw, onSelect: () => setCorrectTarget(r) });
    }

    return (
      <OperationCard
        accent={r.status === "voided" ? "danger" : "primary"}
        number={r.expense_number}
        title={r.expense_type_name ?? "—"}
        ariaLabel={`${e.tabs.expenses} ${r.expense_number}`}
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
      {/* Hidden picker for attach/replace receipt actions (triggered by id). */}
      <input id={RECEIPT_PICKER_ID} type="file" accept={RECEIPT_ACCEPT} style={{ display: "none" }} onChange={onReplaceFile} />
      <Card>
        <SectionHeader title={e.tabs.expenses} />
        <form onSubmit={(ev) => { ev.preventDefault(); setAppliedSearch(search.trim()); setPage(1); }}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="exp-search">
              <Input id="exp-search" value={search} placeholder={e.searchPlaceholder} onChange={(ev) => setSearch(ev.target.value)} />
            </FormField>
            <FormField label={e.type} htmlFor="exp-type">
              <Select id="exp-type" value={typeFilter} placeholder={t.common.all} options={typeOptions} onChange={(ev) => { setPage(1); setTypeFilter(ev.target.value); }} />
            </FormField>
            {can("expenses.create") ? (
              <div className="filter-bar__actions cluster">
                <Button icon={Plus} onClick={() => setCreating(true)}>{e.add}</Button>
              </div>
            ) : null}
          </FilterBar>
        </form>

        <div className="sr-only" aria-live="polite" aria-atomic="true" data-testid="exp-results-announce">
          {announcement}
        </div>

        {showInitialLoading ? <LoadingState label={t.common.loading} /> : null}
        {showInitialError ? (
          <ErrorState title={t.states.errorTitle} message={error ?? ""} retryLabel={t.common.retry} onRetry={load} />
        ) : null}
        {!showInitialLoading && !showInitialError ? (
          <div className="op-results" ref={resultsRef} tabIndex={-1} aria-label={e.tabs.expenses}>
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
                <EmptyState title={e.noMatches} hint={e.noMatchesHint} icon={SearchX} />
              ) : (
                <EmptyState
                  title={e.empty}
                  hint={e.emptyHint}
                  icon={PiggyBank}
                  action={can("expenses.create") ? <Button icon={Plus} onClick={() => setCreating(true)}>{e.add}</Button> : undefined}
                />
              )
            ) : (
              <div className="op-grid" role="list" aria-label={e.tabs.expenses} aria-busy={backgroundRefreshing}>
                {rows.map((r) => (
                  <div role="listitem" key={r.id}>{renderCard(r)}</div>
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
                  status: t.pagination.page.replace("{page}", String(page)).replace("{total}", String(totalPages)),
                }}
              />
            ) : null}
          </div>
        ) : null}
      </Card>

      <ExpenseModal
        open={creating}
        types={types}
        onClose={() => setCreating(false)}
        onSaved={() => { setCreating(false); notify(e.created); setPage(1); load(); }}
      />
      <ExpenseEditModal
        expense={editTarget}
        types={types}
        onClose={() => setEditTarget(null)}
        onSaved={() => { setEditTarget(null); notify(e.updated); reloadAfterAction(); }}
      />

      {/* Distinct CANCEL (void, before close) — its own reason dialog. */}
      <VoidDialog
        open={cancelTarget !== null}
        title={e.cancelTitle}
        confirmLabel={e.cancel}
        description={e.cancelHint}
        onClose={() => setCancelTarget(null)}
        onConfirm={async (reason) => {
          if (!cancelTarget) return;
          await voidExpense(cancelTarget.id, reason);
          setCancelTarget(null);
          notify(e.cancelled);
          reloadAfterAction();
        }}
      />

      {/* Distinct CORRECTIVE MOVEMENT (reverse, after close) — a linked
          counter-voucher, deliberately separate from cancel. */}
      <VoidDialog
        open={correctTarget !== null}
        title={e.correctiveTitle}
        confirmLabel={e.corrective}
        description={e.correctiveHint}
        onClose={() => setCorrectTarget(null)}
        onConfirm={async (reason) => {
          if (!correctTarget) return;
          await reverseExpense(correctTarget.id, reason);
          setCorrectTarget(null);
          notify(e.corrected);
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
              { label: e.type, value: voucher.expense.expense_type_name ?? "—" },
              { label: t.finance.print.status, value: t.finance.postingStatus[voucher.expense.status] },
              { label: t.finance.print.businessDate, value: formatDate(voucher.expense.business_date ?? voucher.expense.paid_at, locale) },
              { label: t.finance.print.executedAt, value: formatDateTime(voucher.expense.paid_at, locale) },
              ...(voucher.expense.shift_number ? [{ label: t.finance.print.shift, value: voucher.expense.shift_number }] : []),
              { label: t.finance.print.method, value: t.finance.methods[voucher.expense.method] },
              { label: t.finance.print.amount, value: <strong><bdi dir="ltr">{formatMoney(voucher.expense.amount, voucher.expense.currency, locale)}</bdi></strong> },
              ...(voucher.expense.original_currency && voucher.expense.original_currency !== voucher.expense.currency && voucher.expense.original_amount
                ? [
                    { label: e.originalAmount, value: <bdi dir="ltr">{formatMoney(voucher.expense.original_amount, voucher.expense.original_currency, locale)}</bdi> },
                    { label: e.exchangeRate, value: voucher.expense.exchange_rate ?? "—" },
                  ]
                : []),
              { label: e.description, value: voucher.expense.description },
              ...(voucher.expense.reverses_number ? [{ label: t.finance.print.reversalOf, value: voucher.expense.reverses_number }] : []),
              ...(voucher.expense.reversed_by_number ? [{ label: t.finance.print.reversedBy, value: voucher.expense.reversed_by_number }] : []),
              ...(voucher.expense.status === "voided"
                ? [
                    { label: t.finance.print.voidReason, value: voucher.expense.void_reason || "—" },
                    { label: t.finance.print.voidedBy, value: voucher.expense.voided_by || "—" },
                  ]
                : []),
              ...(voucher.expense.created_by ? [{ label: t.finance.print.createdBy, value: voucher.expense.created_by }] : []),
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

/** Base + accepted currencies for the FX picker. Read from the expenses-gated
 * meta endpoint (NOT hotel settings) so an expenses clerk without
 * `settings.view` can still enter a foreign-currency expense. */
function useHotelCurrencies(open: boolean) {
  const [base, setBase] = useState("");
  const [accepted, setAccepted] = useState<string[]>([]);
  useEffect(() => {
    if (!open) return;
    let alive = true;
    getExpenseMeta()
      .then((m) => {
        if (!alive) return;
        const def = (m.base_currency || "").toUpperCase();
        const all = Array.from(
          new Set([def, ...(m.accepted_currencies || []).map((c) => c.toUpperCase())]),
        ).filter(Boolean);
        setBase(def);
        setAccepted(all);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [open]);
  return { base, accepted };
}

function ExpenseModal({
  open, types, onClose, onSaved,
}: { open: boolean; types: ExpenseType[]; onClose: () => void; onSaved: () => void }) {
  const { t, locale } = useI18n();
  const e = t.expenses;
  const { base, accepted } = useHotelCurrencies(open);

  const [expenseType, setExpenseType] = useState("");
  const [description, setDescription] = useState("");
  const [method, setMethod] = useState("cash");
  const [currency, setCurrency] = useState("");
  const [amount, setAmount] = useState("");
  const [originalAmount, setOriginalAmount] = useState("");
  const [exchangeRate, setExchangeRate] = useState("");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const keyRef = useRef<string>("");

  useEffect(() => {
    if (open) {
      setExpenseType(""); setDescription(""); setMethod("cash"); setCurrency("");
      setAmount(""); setOriginalAmount(""); setExchangeRate(""); setNotes("");
      setFile(null); setError(null);
      keyRef.current = mintIdempotencyKey();
    }
  }, [open]);

  const effectiveCurrency = (currency || base).toUpperCase();
  const isForeign = base !== "" && effectiveCurrency !== base;
  const derivedBase = useMemo(() => {
    if (!isForeign) return null;
    const oa = Number(originalAmount), rate = Number(exchangeRate);
    if (!oa || !rate || oa <= 0 || rate <= 0) return null;
    return (oa * rate).toFixed(2);
  }, [isForeign, originalAmount, exchangeRate]);

  const valid = expenseType !== "" && description.trim() !== "" &&
    (isForeign ? (Number(originalAmount) > 0 && Number(exchangeRate) > 0) : Number(amount) > 0);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!valid) return setError(t.errors.validation);
    setBusy(true);
    try {
      const body: ExpenseCreateBody = {
        expense_type: Number(expenseType),
        description: description.trim(),
        method,
        notes: notes.trim() || undefined,
        idempotency_key: keyRef.current,
      };
      if (isForeign) {
        body.currency = effectiveCurrency;
        body.original_amount = originalAmount;
        body.exchange_rate = exchangeRate;
      } else {
        body.amount = amount;
      }
      const created = await createExpense(body);
      if (file) {
        try {
          await uploadExpenseAttachment(created.id, file);
        } catch (err) {
          // The VOUCHER is saved; only the receipt failed. Keep the modal open
          // showing the error instead of closing with a success toast (which
          // would hide the loss). Re-submitting is safe: the idempotency key
          // replays the SAME voucher and retries only the upload.
          setError(messageForError(err, t));
          return;
        }
      }
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const typeOptions = types.filter((ty) => ty.is_active).map((ty) => ({ value: String(ty.id), label: ty.name }));
  const methodOptions = EXPENSE_METHODS.map((m) => ({ value: m, label: t.finance.methods[m] }));
  const currencyOptions = accepted.map((c) => ({ value: c, label: c }));

  return (
    <Modal open={open} onClose={onClose} title={e.createTitle} closeLabel={t.common.close}
      footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button><Button form="exp-form" type="submit" loading={busy} disabled={!valid}>{e.submit}</Button></>}>
      <form id="exp-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={e.type} htmlFor="e-type">
            <Select id="e-type" value={expenseType} placeholder={e.selectType} options={typeOptions} onChange={(ev) => setExpenseType(ev.target.value)} />
          </FormField>
          <FormField label={e.method} htmlFor="e-method">
            <Select id="e-method" value={method} options={methodOptions} onChange={(ev) => setMethod(ev.target.value)} />
          </FormField>
          <FormField label={e.currency} htmlFor="e-cur">
            <Select id="e-cur" value={effectiveCurrency} options={currencyOptions.length ? currencyOptions : [{ value: base, label: base }]} onChange={(ev) => setCurrency(ev.target.value)} />
          </FormField>
          {isForeign ? (
            <>
              <FormField label={e.originalAmount} htmlFor="e-oamt">
                <Input id="e-oamt" type="number" step="0.01" min="0" value={originalAmount} onChange={(ev) => setOriginalAmount(ev.target.value)} />
              </FormField>
              <FormField label={e.exchangeRate} htmlFor="e-rate" hint={e.exchangeRateHint}>
                <Input id="e-rate" type="number" step="0.00000001" min="0" value={exchangeRate} onChange={(ev) => setExchangeRate(ev.target.value)} />
              </FormField>
            </>
          ) : (
            <FormField label={e.amount} htmlFor="e-amt">
              <Input id="e-amt" type="number" step="0.01" min="0" value={amount} onChange={(ev) => setAmount(ev.target.value)} />
            </FormField>
          )}
        </div>
        {isForeign && derivedBase ? (
          <p className="muted">{e.baseEquivalent}: <bdi dir="ltr">{formatMoney(derivedBase, base, locale)}</bdi></p>
        ) : null}
        <FormField label={e.description} htmlFor="e-desc"><Input id="e-desc" value={description} onChange={(ev) => setDescription(ev.target.value)} /></FormField>
        <FormField label={e.notes} htmlFor="e-notes"><Textarea id="e-notes" value={notes} onChange={(ev) => setNotes(ev.target.value)} /></FormField>
        <FormField label={e.attachment} htmlFor="e-file" hint={e.attachmentHint}>
          <input id="e-file" type="file" accept={RECEIPT_ACCEPT} onChange={(ev) => setFile(ev.target.files?.[0] ?? null)} />
        </FormField>
        <p className="muted">{e.autoNote}</p>
      </form>
    </Modal>
  );
}

/** Atomic financial edit — money re-derived server-side. Only inside the open
 *  business date (409 otherwise). */
function ExpenseEditModal({
  expense, types, onClose, onSaved,
}: { expense: Expense | null; types: ExpenseType[]; onClose: () => void; onSaved: () => void }) {
  const { t, locale } = useI18n();
  const e = t.expenses;
  const open = expense !== null;
  const { base, accepted } = useHotelCurrencies(open);

  const [expenseType, setExpenseType] = useState("");
  const [description, setDescription] = useState("");
  const [method, setMethod] = useState("cash");
  const [currency, setCurrency] = useState("");
  const [amount, setAmount] = useState("");
  const [originalAmount, setOriginalAmount] = useState("");
  const [exchangeRate, setExchangeRate] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (expense) {
      setExpenseType(String(expense.expense_type));
      setDescription(expense.description);
      setMethod(expense.method);
      setNotes(expense.notes);
      const foreign = expense.original_currency && expense.original_currency !== expense.currency;
      setCurrency(foreign ? expense.original_currency : expense.currency);
      setAmount(foreign ? "" : expense.amount);
      setOriginalAmount(foreign && expense.original_amount ? expense.original_amount : "");
      setExchangeRate(foreign && expense.exchange_rate ? expense.exchange_rate : "");
      setError(null);
    }
  }, [expense]);

  const effectiveCurrency = (currency || base).toUpperCase();
  const isForeign = base !== "" && effectiveCurrency !== base;
  const derivedBase = useMemo(() => {
    if (!isForeign) return null;
    const oa = Number(originalAmount), rate = Number(exchangeRate);
    if (!oa || !rate || oa <= 0 || rate <= 0) return null;
    return (oa * rate).toFixed(2);
  }, [isForeign, originalAmount, exchangeRate]);

  const valid = expenseType !== "" && description.trim() !== "" &&
    (isForeign ? (Number(originalAmount) > 0 && Number(exchangeRate) > 0) : Number(amount) > 0);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!expense) return;
    setError(null);
    if (!valid) return setError(t.errors.validation);
    setBusy(true);
    try {
      const body: ExpenseUpdateBody = {
        expense_type: Number(expenseType),
        description: description.trim(),
        method,
        notes: notes.trim(),
      };
      if (isForeign) {
        body.currency = effectiveCurrency;
        body.original_amount = originalAmount;
        body.exchange_rate = exchangeRate;
      } else {
        body.currency = effectiveCurrency;
        body.amount = amount;
      }
      await updateExpense(expense.id, body);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const typeOptions = types.filter((ty) => ty.is_active || String(ty.id) === expenseType).map((ty) => ({ value: String(ty.id), label: ty.name }));
  const methodOptions = EXPENSE_METHODS.map((m) => ({ value: m, label: t.finance.methods[m] }));
  const currencyOptions = accepted.map((c) => ({ value: c, label: c }));

  return (
    <Modal open={open} onClose={onClose} title={e.editTitle} closeLabel={t.common.close}
      footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button><Button form="exp-edit-form" type="submit" loading={busy} disabled={!valid}>{e.editSave}</Button></>}>
      <form id="exp-edit-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <p className="muted">{e.editHint}</p>
        <div className="form-grid">
          <FormField label={e.type} htmlFor="ee-type">
            <Select id="ee-type" value={expenseType} options={typeOptions} onChange={(ev) => setExpenseType(ev.target.value)} />
          </FormField>
          <FormField label={e.method} htmlFor="ee-method">
            <Select id="ee-method" value={method} options={methodOptions} onChange={(ev) => setMethod(ev.target.value)} />
          </FormField>
          <FormField label={e.currency} htmlFor="ee-cur">
            <Select id="ee-cur" value={effectiveCurrency} options={currencyOptions.length ? currencyOptions : [{ value: base, label: base }]} onChange={(ev) => setCurrency(ev.target.value)} />
          </FormField>
          {isForeign ? (
            <>
              <FormField label={e.originalAmount} htmlFor="ee-oamt">
                <Input id="ee-oamt" type="number" step="0.01" min="0" value={originalAmount} onChange={(ev) => setOriginalAmount(ev.target.value)} />
              </FormField>
              <FormField label={e.exchangeRate} htmlFor="ee-rate" hint={e.exchangeRateHint}>
                <Input id="ee-rate" type="number" step="0.00000001" min="0" value={exchangeRate} onChange={(ev) => setExchangeRate(ev.target.value)} />
              </FormField>
            </>
          ) : (
            <FormField label={e.amount} htmlFor="ee-amt">
              <Input id="ee-amt" type="number" step="0.01" min="0" value={amount} onChange={(ev) => setAmount(ev.target.value)} />
            </FormField>
          )}
        </div>
        {isForeign && derivedBase ? (
          <p className="muted">{e.baseEquivalent}: <bdi dir="ltr">{formatMoney(derivedBase, base, locale)}</bdi></p>
        ) : null}
        <FormField label={e.description} htmlFor="ee-desc"><Input id="ee-desc" value={description} onChange={(ev) => setDescription(ev.target.value)} /></FormField>
        <FormField label={e.notes} htmlFor="ee-notes"><Textarea id="ee-notes" value={notes} onChange={(ev) => setNotes(ev.target.value)} /></FormField>
      </form>
    </Modal>
  );
}
