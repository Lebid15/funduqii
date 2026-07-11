"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { PiggyBank, Plus, Printer } from "lucide-react";

import { useQuickAction } from "@/lib/useQuickAction";

import {
  Alert, Badge, Button, Card, DataTable, EmptyState, ErrorState, FilterBar, FormField,
  Input, LoadingState, Modal, Pagination, PrintDocumentLayout, Select, Textarea, useToast, type Column,
} from "@/components/ui";
import {
  createExpense, getExpenseVoucher, listExpenses, reverseExpense, updateExpense, voidExpense,
  type ExpenseBody, type ExpenseUpdateBody,
} from "@/lib/api/finance";
import { messageForError } from "@/lib/api/errors";
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
  const [rows, setRows] = useState<Expense[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  // Topbar quick action: ?action=new opens the EXISTING expense modal once.
  useQuickAction("new", () => setCreating(true));
  const [voidTarget, setVoidTarget] = useState<Expense | null>(null);
  const [editTarget, setEditTarget] = useState<Expense | null>(null);
  const [reverseTarget, setReverseTarget] = useState<Expense | null>(null);
  const [voucher, setVoucher] = useState<{ hotel: HotelHeader; expense: Expense } | null>(null);
  const can = useCan();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listExpenses({ page, category: category || undefined, search: query || undefined });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, category, query, t]);

  useEffect(() => { load(); }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: t.finance.categories[c] }));

  async function openVoucher(id: number) {
    try { const r = await getExpenseVoucher(id); setVoucher({ hotel: r.hotel, expense: r.expense }); }
    catch (err) { notify(messageForError(err, t), "error"); }
  }

  const columns: Column<Expense>[] = [
    {
      key: "expense_number", header: t.finance.expenses.number,
      render: (r) => (
        <>
          {r.expense_number}
          {r.reverses_number ? <span className="muted" title={t.finance.expenses.reversalOf}> ↩ {r.reverses_number}</span> : null}
          {r.reversed_by_number ? <span className="muted" title={t.finance.expenses.reversedBy}> ↩ {r.reversed_by_number}</span> : null}
        </>
      ),
    },
    { key: "category", header: t.finance.expenses.category, render: (r) => t.finance.categories[r.category] },
    { key: "description", header: t.finance.expenses.description },
    { key: "amount", header: t.finance.expenses.amount, render: (r) => formatMoney(r.amount, r.currency, locale) },
    { key: "business_date", header: t.finance.expenses.date, render: (r) => formatDate(r.business_date ?? r.paid_at, locale) },
    { key: "status", header: t.common.status, render: (r) => <Badge tone={postingStatusTone(r.status)}>{t.finance.postingStatus[r.status]}</Badge> },
    {
      key: "actions", header: t.common.actions, align: "end",
      render: (r) => (
        <div className="table__actions">
          <Button size="sm" variant="secondary" icon={Printer} onClick={() => openVoucher(r.id)}>{t.finance.expenses.voucher}</Button>
          {r.status === "posted" && can("expenses.update") ? <Button size="sm" variant="ghost" onClick={() => setEditTarget(r)}>{t.finance.expenses.edit}</Button> : null}
          {r.status === "posted" && r.reverses === null && !r.reversed_by_number && can("expenses.reverse") ? <Button size="sm" variant="ghost" onClick={() => setReverseTarget(r)}>{t.finance.expenses.reverse}</Button> : null}
          {r.status === "posted" && can("expenses.void") ? <Button size="sm" variant="danger" onClick={() => setVoidTarget(r)}>{t.finance.expenses.void}</Button> : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <Card>
        <form onSubmit={(e) => { e.preventDefault(); setPage(1); setQuery(search); }}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="exp-search"><Input id="exp-search" value={search} placeholder={t.finance.expenses.searchPlaceholder} onChange={(e) => setSearch(e.target.value)} /></FormField>
            <FormField label={t.finance.expenses.category} htmlFor="exp-cat"><Select id="exp-cat" value={category} placeholder={t.common.all} options={categoryOptions} onChange={(e) => { setPage(1); setCategory(e.target.value); }} /></FormField>
            <div className="filter-bar__actions cluster"><Button icon={Plus} onClick={() => setCreating(true)}>{t.finance.expenses.add}</Button></div>
          </FilterBar>
        </form>
      </Card>
      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} /> : null}
      {!loading && !error ? (
        rows.length === 0 ? <EmptyState title={t.finance.expenses.empty} hint={t.finance.expenses.emptyHint} icon={PiggyBank} action={<Button icon={Plus} onClick={() => setCreating(true)}>{t.finance.expenses.add}</Button>} /> : (
          <>
            <DataTable caption={t.finance.tabs.expenses} columns={columns} rows={rows} rowKey={(r) => r.id} />
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage}
              labels={{ previous: t.pagination.previous, next: t.pagination.next, status: t.pagination.page.replace("{page}", String(page)).replace("{total}", String(totalPages)) }} />
          </>
        )
      ) : null}

      <ExpenseModal open={creating} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); notify(t.finance.saved); setPage(1); load(); }} />
      <ExpenseEditModal expense={editTarget} onClose={() => setEditTarget(null)} onSaved={() => { setEditTarget(null); notify(t.finance.saved); load(); }} />
      <VoidDialog open={voidTarget !== null} onClose={() => setVoidTarget(null)}
        onConfirm={async (reason) => { if (voidTarget) { await voidExpense(voidTarget.id, reason); setVoidTarget(null); notify(t.finance.saved); load(); } }} />
      <VoidDialog open={reverseTarget !== null} title={t.finance.expenses.reverseTitle} confirmLabel={t.finance.expenses.reverseConfirm}
        description={t.finance.expenses.reverseHint} onClose={() => setReverseTarget(null)}
        onConfirm={async (reason) => { if (reverseTarget) { await reverseExpense(reverseTarget.id, reason); setReverseTarget(null); notify(t.finance.saved); load(); } }} />
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
              { label: t.finance.expenses.category, value: t.finance.categories[voucher.expense.category] },
              { label: t.finance.print.status, value: t.finance.postingStatus[voucher.expense.status] },
              { label: t.finance.print.businessDate, value: formatDate(voucher.expense.business_date ?? voucher.expense.paid_at, locale) },
              { label: t.finance.print.executedAt, value: formatDateTime(voucher.expense.paid_at, locale) },
              ...(voucher.expense.shift_number
                ? [{ label: t.finance.print.shift, value: voucher.expense.shift_number }]
                : []),
              { label: t.finance.print.method, value: t.finance.methods[voucher.expense.method] },
              { label: t.finance.print.amount, value: <strong>{formatMoney(voucher.expense.amount, voucher.expense.currency, locale)}</strong> },
              { label: t.finance.expenses.description, value: voucher.expense.description },
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
    <Modal open={open} onClose={onClose} title={t.finance.expenses.createTitle} closeLabel={t.common.close}
      footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button><Button form="exp-form" type="submit" loading={busy}>{t.finance.expenses.submit}</Button></>}>
      <form id="exp-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.finance.expenses.category} htmlFor="e-cat"><Select id="e-cat" value={form.category ?? "other"} options={categoryOptions} onChange={(e) => set("category", e.target.value)} /></FormField>
          <FormField label={t.finance.expenses.amount} htmlFor="e-amt"><Input id="e-amt" type="number" step="0.01" value={form.amount ?? ""} onChange={(e) => set("amount", e.target.value)} /></FormField>
          <FormField label={t.finance.expenses.method} htmlFor="e-method"><Select id="e-method" value={form.method ?? "cash"} options={methodOptions} onChange={(e) => set("method", e.target.value)} /></FormField>
          <FormField label={t.finance.expenses.vendor} htmlFor="e-vendor"><Input id="e-vendor" value={form.vendor_name ?? ""} onChange={(e) => set("vendor_name", e.target.value)} /></FormField>
          <FormField label={t.finance.expenses.reference} htmlFor="e-ref"><Input id="e-ref" value={form.reference ?? ""} onChange={(e) => set("reference", e.target.value)} /></FormField>
        </div>
        <FormField label={t.finance.expenses.description} htmlFor="e-desc"><Input id="e-desc" value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} /></FormField>
        <FormField label={t.finance.folios.notes} htmlFor="e-notes"><Textarea id="e-notes" value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} /></FormField>
      </form>
    </Modal>
  );
}

/** Edits the four descriptive fields only — the server rejects anything else
 *  and enforces the open-business-day window (409 void_window_closed). */
function ExpenseEditModal({ expense, onClose, onSaved }: { expense: Expense | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
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
    <Modal open={expense !== null} onClose={onClose} title={t.finance.expenses.editTitle} closeLabel={t.common.close}
      footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button><Button form="exp-edit-form" type="submit" loading={busy}>{t.finance.expenses.editSave}</Button></>}>
      <form id="exp-edit-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={t.finance.expenses.description} htmlFor="ee-desc"><Input id="ee-desc" value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} /></FormField>
        <div className="form-grid">
          <FormField label={t.finance.expenses.vendor} htmlFor="ee-vendor"><Input id="ee-vendor" value={form.vendor_name ?? ""} onChange={(e) => set("vendor_name", e.target.value)} /></FormField>
          <FormField label={t.finance.expenses.reference} htmlFor="ee-ref"><Input id="ee-ref" value={form.reference ?? ""} onChange={(e) => set("reference", e.target.value)} /></FormField>
        </div>
        <FormField label={t.finance.folios.notes} htmlFor="ee-notes"><Textarea id="ee-notes" value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} /></FormField>
      </form>
    </Modal>
  );
}
