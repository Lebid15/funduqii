"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { CheckCircle, FileText, Plus, Printer, ReceiptText } from "lucide-react";

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
  PrintDocumentLayout,
  Select,
  StatusSummaryCard,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import {
  addCharge,
  adjustCharge,
  closeFolio,
  createFolio,
  createInvoice,
  getFolio,
  getFolioStatement,
  getReceipt,
  issueInvoice,
  listFolios,
  recordPayment,
  reversePayment,
  voidCharge,
  voidFolio,
  voidPayment,
} from "@/lib/api/finance";
import { messageForError } from "@/lib/api/errors";
import type { Folio, FolioListItem, FolioStatement, Payment } from "@/lib/api/types";
import { folioStatusTone, formatDate, formatMoney, postingStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { PrintModal, VoidDialog } from "./shared";

const PAGE_SIZE = 25;
const STATUSES = ["open", "closed", "voided"] as const;

export function FoliosTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [rows, setRows] = useState<FolioListItem[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listFolios({ page, status: status || undefined, search: query || undefined });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, status, query, t]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  function applySearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setQuery(search);
  }

  const columns: Column<FolioListItem>[] = [
    { key: "folio_number", header: t.finance.folios.number },
    {
      key: "customer",
      header: t.finance.folios.customer,
      render: (r) => r.customer_name || r.guest_name || "—",
    },
    {
      key: "balance",
      header: t.finance.folios.balance,
      render: (r) => formatMoney(r.balance.balance, r.currency, locale),
    },
    {
      key: "status",
      header: t.common.status,
      render: (r) => <Badge tone={folioStatusTone(r.status)}>{t.finance.folioStatus[r.status]}</Badge>,
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => (
        <Button variant="secondary" size="sm" onClick={() => setOpenId(r.id)}>
          {t.finance.folios.view}
        </Button>
      ),
    },
  ];

  const statusOptions = STATUSES.map((s) => ({ value: s, label: t.finance.folioStatus[s] }));

  return (
    <>
      <Card>
        <form onSubmit={applySearch}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="folio-search">
              <Input id="folio-search" value={search} placeholder={t.finance.folios.searchPlaceholder} onChange={(e) => setSearch(e.target.value)} />
            </FormField>
            <FormField label={t.common.status} htmlFor="folio-status">
              <Select id="folio-status" value={status} placeholder={t.common.all} options={statusOptions} onChange={(e) => { setPage(1); setStatus(e.target.value); }} />
            </FormField>
            <div className="filter-bar__actions cluster">
              <Button icon={Plus} onClick={() => setCreating(true)}>{t.finance.folios.add}</Button>
            </div>
          </FilterBar>
        </form>
      </Card>

      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} /> : null}
      {!loading && !error ? (
        rows.length === 0 ? (
          <EmptyState title={t.finance.folios.empty} hint={t.finance.folios.emptyHint} icon={FileText} action={<Button icon={Plus} onClick={() => setCreating(true)}>{t.finance.folios.add}</Button>} />
        ) : (
          <>
            <DataTable caption={t.finance.tabs.folios} columns={columns} rows={rows} rowKey={(r) => r.id} />
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage}
              labels={{ previous: t.pagination.previous, next: t.pagination.next, status: t.pagination.page.replace("{page}", String(page)).replace("{total}", String(totalPages)) }} />
          </>
        )
      ) : null}

      <FolioCreateModal open={creating} onClose={() => setCreating(false)} onSaved={(f) => { setCreating(false); notify(t.finance.saved); setOpenId(f.id); load(); }} />
      <FolioDetailModal id={openId} onClose={() => setOpenId(null)} onChanged={load} />
    </>
  );
}

function FolioCreateModal({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: (f: Folio) => void }) {
  const { t } = useI18n();
  const [customer, setCustomer] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setCustomer(""); setNotes(""); setError(null); }
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const folio = await createFolio({ customer_name: customer.trim(), notes: notes.trim() });
      onSaved(folio);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={t.finance.folios.createTitle} closeLabel={t.common.close}
      footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button><Button form="folio-form" type="submit" loading={busy}>{t.common.save}</Button></>}>
      <form id="folio-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.finance.folios.customerName} htmlFor="fo-cust"><Input id="fo-cust" value={customer} onChange={(e) => setCustomer(e.target.value)} /></FormField>
        </div>
        <FormField label={t.finance.folios.notes} htmlFor="fo-notes"><Textarea id="fo-notes" value={notes} onChange={(e) => setNotes(e.target.value)} /></FormField>
      </form>
    </Modal>
  );
}

function FolioDetailModal({ id, onClose, onChanged }: { id: number | null; onClose: () => void; onChanged: () => void }) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [folio, setFolio] = useState<Folio | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [panel, setPanel] = useState<"charge" | "payment" | null>(null);
  const [voidTarget, setVoidTarget] = useState<{ kind: "charge" | "payment" | "folio"; id: number } | null>(null);
  const [actionTarget, setActionTarget] = useState<{ kind: "adjust" | "reverse"; id: number } | null>(null);
  const [receipt, setReceipt] = useState<{ hotel: import("@/lib/api/types").HotelHeader; payment: Payment } | null>(null);
  const [statement, setStatement] = useState<FolioStatement | null>(null);

  const reload = useCallback(async () => {
    if (id === null) return;
    try {
      setFolio(await getFolio(id));
      setError(null);
    } catch (err) {
      setError(messageForError(err, t));
    }
  }, [id, t]);

  useEffect(() => {
    if (id !== null) { setFolio(null); setPanel(null); reload(); }
  }, [id, reload]);

  if (id === null) return null;
  const currency = folio?.currency ?? "USD";
  const m = (v: string) => formatMoney(v, currency, locale);
  const editable = folio?.status === "open";

  async function afterMutation(msg = t.finance.saved) {
    await reload();
    onChanged();
    notify(msg);
  }

  async function doCreateInvoice() {
    if (!folio) return;
    try {
      const draft = await createInvoice(folio.id);
      await issueInvoice(draft.id);
      await afterMutation();
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  async function doClose() {
    if (!folio) return;
    try {
      await closeFolio(folio.id);
      await afterMutation();
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  async function openReceipt(paymentId: number) {
    try {
      const r = await getReceipt(paymentId);
      setReceipt({ hotel: r.hotel, payment: r.payment });
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  async function openStatement() {
    if (!folio) return;
    try {
      setStatement(await getFolioStatement(folio.id));
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  return (
    <Modal open={id !== null} onClose={onClose} title={folio ? `${t.finance.folio.title} ${folio.folio_number}` : t.finance.folio.title} closeLabel={t.common.close}
      footer={<Button variant="secondary" onClick={onClose}>{t.common.close}</Button>}>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {!folio ? <LoadingState label={t.common.loading} /> : (
        <div className="stack">
          <div className="cluster">
            <Badge tone={folioStatusTone(folio.status)}>{t.finance.folioStatus[folio.status]}</Badge>
            <span className="muted">{folio.customer_name || folio.guest_name || "—"}</span>
            <Button size="sm" variant="ghost" icon={Printer} onClick={openStatement}>{t.finance.folio.statement}</Button>
          </div>

          <StatusSummaryCard
            items={[
              { label: t.finance.folio.totalCharges, value: m(folio.balance.total_charges) },
              { label: t.finance.folio.totalPayments, value: m(folio.balance.total_payments) },
              { label: t.finance.folio.balance, value: m(folio.balance.balance), emphasis: true },
            ]}
          />

          {editable ? (
            <div className="cluster">
              <Button size="sm" icon={Plus} onClick={() => setPanel(panel === "charge" ? null : "charge")}>{t.finance.folio.addCharge}</Button>
              <Button size="sm" variant="secondary" icon={Plus} onClick={() => setPanel(panel === "payment" ? null : "payment")}>{t.finance.folio.recordPayment}</Button>
              <Button size="sm" variant="secondary" icon={ReceiptText} onClick={doCreateInvoice}>{t.finance.folio.createInvoice}</Button>
              <Button size="sm" variant="ghost" icon={CheckCircle} onClick={doClose}>{t.finance.folio.close}</Button>
              <Button size="sm" variant="danger" onClick={() => setVoidTarget({ kind: "folio", id: folio.id })}>{t.finance.folio.void}</Button>
            </div>
          ) : null}

          {panel === "charge" ? <ChargeForm folioId={folio.id} onDone={() => { setPanel(null); afterMutation(); }} /> : null}
          {panel === "payment" ? (
            <PaymentForm
              folioId={folio.id}
              onDone={() => { setPanel(null); afterMutation(); }}
              onSavedContinue={() => afterMutation()}
            />
          ) : null}

          <div>
            <h4>{t.finance.folio.charges}</h4>
            {folio.charges.length === 0 ? <p className="muted">{t.finance.folio.noCharges}</p> : (
              <ul className="mini-list">
                {folio.charges.map((c) => (
                  <li key={c.id} className="mini-list__row">
                    <span className="mini-list__main">
                      <strong>{c.description}</strong>
                      <span className="muted">
                        {t.finance.chargeTypes[c.type]} · {c.charge_date}
                        {c.adjusts !== null ? <span title={t.finance.folio.adjustsRef}> · ↩ {c.adjusts_number}</span> : null}
                      </span>
                    </span>
                    <span className="mini-list__side">
                      <span>{m(c.total_amount)}</span>
                      {c.status === "voided" ? <Badge tone="danger">{t.finance.folio.voided}</Badge> :
                        editable ? (
                          <>
                            <Button size="sm" variant="ghost" onClick={() => setVoidTarget({ kind: "charge", id: c.id })}>{t.finance.folio.voidCharge}</Button>
                            {c.status === "posted" && c.adjusts === null ? (
                              <Button size="sm" variant="ghost" onClick={() => setActionTarget({ kind: "adjust", id: c.id })}>{t.finance.folio.adjust}</Button>
                            ) : null}
                          </>
                        ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h4>{t.finance.folio.payments}</h4>
            {folio.payments.length === 0 ? <p className="muted">{t.finance.folio.noPayments}</p> : (
              <ul className="mini-list">
                {folio.payments.map((p) => (
                  <li key={p.id} className="mini-list__row">
                    <span className="mini-list__main">
                      <strong>{p.receipt_number}</strong>
                      <span className="muted">
                        {t.finance.methods[p.method]} · {formatDate(p.paid_at, locale)}
                        {p.reverses !== null ? <span title={t.finance.folio.reversesRef}> · ↩ {p.reverses_receipt}</span> : null}
                      </span>
                    </span>
                    <span className="mini-list__side">
                      <span>{m(p.amount)}</span>
                      <Badge tone={postingStatusTone(p.status)}>{t.finance.postingStatus[p.status]}</Badge>
                      <Button size="sm" variant="ghost" icon={Printer} onClick={() => openReceipt(p.id)}>{t.finance.folio.printReceipt}</Button>
                      {p.status === "posted" && editable ? <Button size="sm" variant="ghost" onClick={() => setVoidTarget({ kind: "payment", id: p.id })}>{t.finance.folio.voidPayment}</Button> : null}
                      {p.status === "posted" && p.reverses === null && Number(p.amount) > 0 && editable ? (
                        <Button size="sm" variant="ghost" onClick={() => setActionTarget({ kind: "reverse", id: p.id })}>{t.finance.folio.reverse}</Button>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      <VoidDialog
        open={voidTarget !== null}
        onClose={() => setVoidTarget(null)}
        onConfirm={async (reason) => {
          if (!voidTarget) return;
          if (voidTarget.kind === "charge") await voidCharge(voidTarget.id, reason);
          else if (voidTarget.kind === "payment") await voidPayment(voidTarget.id, reason);
          else await voidFolio(voidTarget.id, reason);
          setVoidTarget(null);
          await afterMutation();
        }}
      />
      <VoidDialog
        open={actionTarget !== null}
        title={actionTarget?.kind === "reverse" ? t.finance.reverse.title : t.finance.adjust.title}
        confirmLabel={actionTarget?.kind === "reverse" ? t.finance.reverse.confirm : t.finance.adjust.confirm}
        onClose={() => setActionTarget(null)}
        onConfirm={async (reason) => {
          if (!actionTarget) return;
          if (actionTarget.kind === "adjust") await adjustCharge(actionTarget.id, reason);
          else await reversePayment(actionTarget.id, reason);
          setActionTarget(null);
          await afterMutation();
        }}
      />
      <PrintModal open={receipt !== null} title={t.finance.print.receiptTitle} onClose={() => setReceipt(null)}>
        {receipt ? (
          <PrintDocumentLayout
            hotelName={receipt.hotel.hotel_name}
            hotelAddress={receipt.hotel.address}
            hotelPhone={receipt.hotel.phone}
            docTitle={t.finance.print.receiptTitle}
            docNumber={receipt.payment.receipt_number}
            meta={[
              { label: t.finance.print.customer, value: receipt.payment.payer_name || "—" },
              { label: t.finance.print.date, value: formatDate(receipt.payment.paid_at, locale) },
              { label: t.finance.print.method, value: t.finance.methods[receipt.payment.method] },
              { label: t.finance.print.amount, value: <strong>{formatMoney(receipt.payment.amount, receipt.payment.currency, locale)}</strong> },
              { label: t.finance.print.folio, value: receipt.payment.folio_number },
              ...(receipt.payment.reservation_number
                ? [{ label: t.finance.print.reservation, value: receipt.payment.reservation_number }]
                : []),
              ...(receipt.payment.reference
                ? [{ label: t.finance.print.reference, value: receipt.payment.reference }]
                : []),
              ...(receipt.payment.created_by
                ? [{ label: t.finance.print.receivedBy, value: receipt.payment.created_by }]
                : []),
            ]}
            notes={receipt.payment.notes || undefined}
            notesLabel={t.finance.print.notes}
            signatureLabel={t.finance.print.signature}
            footer={t.finance.print.thanks}
          />
        ) : null}
      </PrintModal>
      <PrintModal open={statement !== null} title={t.finance.print.statementTitle} onClose={() => setStatement(null)}>
        {statement ? (
          <PrintDocumentLayout
            hotelName={statement.hotel.hotel_name}
            hotelAddress={statement.hotel.address}
            hotelPhone={statement.hotel.phone}
            docTitle={t.finance.print.statementTitle}
            docNumber={statement.folio.folio_number}
            meta={[
              { label: t.finance.print.status, value: t.finance.folioStatus[statement.folio.status] },
              { label: t.finance.print.customer, value: statement.folio.customer_name || statement.folio.guest_name || "—" },
              ...(statement.stay
                ? [
                    { label: t.finance.print.room, value: statement.stay.room_number },
                    { label: t.finance.print.plannedCheckIn, value: formatDate(statement.stay.planned_check_in_date, locale) },
                    { label: t.finance.print.plannedCheckOut, value: formatDate(statement.stay.planned_check_out_date, locale) },
                  ]
                : []),
              { label: t.finance.print.opened, value: formatDate(statement.folio.opened_at, locale) },
              ...(statement.folio.closed_at
                ? [{ label: t.finance.print.closed, value: formatDate(statement.folio.closed_at, locale) }]
                : []),
            ]}
            totals={[
              { label: t.finance.folio.totalCharges, value: formatMoney(statement.folio.balance.total_charges, statement.folio.currency, locale) },
              { label: t.finance.folio.totalPayments, value: formatMoney(statement.folio.balance.total_payments, statement.folio.currency, locale) },
              { label: t.finance.folio.balance, value: <strong>{formatMoney(statement.folio.balance.balance, statement.folio.currency, locale)}</strong> },
            ]}
          >
            <h4>{t.finance.folio.charges}</h4>
            {statement.folio.charges.length === 0 ? <p className="muted">{t.finance.folio.noCharges}</p> : (
              <table className="print-table">
                <thead>
                  <tr>
                    <th>{t.finance.chargeForm.description}</th>
                    <th>{t.finance.chargeForm.type}</th>
                    <th>{t.finance.print.date}</th>
                    <th>{t.finance.print.total}</th>
                  </tr>
                </thead>
                <tbody>
                  {statement.folio.charges.map((c) => (
                    <tr key={c.id}>
                      <td>
                        {c.description}
                        {c.adjusts !== null ? <span className="muted"> → {c.adjusts_number}</span> : null}
                        {c.status === "voided" ? <> <Badge tone="danger">{t.finance.folio.voided}</Badge></> : null}
                      </td>
                      <td>{t.finance.chargeTypes[c.type]}</td>
                      <td>{formatDate(c.charge_date, locale)}</td>
                      <td>{formatMoney(c.total_amount, statement.folio.currency, locale)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <h4>{t.finance.folio.payments}</h4>
            {statement.folio.payments.length === 0 ? <p className="muted">{t.finance.folio.noPayments}</p> : (
              <table className="print-table">
                <thead>
                  <tr>
                    <th>{t.finance.payments.number}</th>
                    <th>{t.finance.print.method}</th>
                    <th>{t.finance.print.date}</th>
                    <th>{t.finance.print.amount}</th>
                  </tr>
                </thead>
                <tbody>
                  {statement.folio.payments.map((p) => (
                    <tr key={p.id}>
                      <td>
                        {p.receipt_number}
                        {p.reverses !== null ? <span className="muted"> → {p.reverses_receipt}</span> : null}
                        {p.status === "voided" ? <> <Badge tone="danger">{t.finance.folio.voided}</Badge></> : null}
                      </td>
                      <td>{t.finance.methods[p.method]}</td>
                      <td>{formatDate(p.paid_at, locale)}</td>
                      <td>{formatMoney(p.amount, statement.folio.currency, locale)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </PrintDocumentLayout>
        ) : null}
      </PrintModal>
    </Modal>
  );
}

function ChargeForm({ folioId, onDone }: { folioId: number; onDone: () => void }) {
  const { t } = useI18n();
  const [type, setType] = useState("service");
  const [description, setDescription] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [unit, setUnit] = useState("");
  const [tax, setTax] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const typeOptions = (["room", "service", "tax", "adjustment", "discount", "other"] as const).map((v) => ({ value: v, label: t.finance.chargeTypes[v] }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!description.trim() || !unit) return setError(t.errors.validation);
    setBusy(true);
    try {
      await addCharge(folioId, { type, description: description.trim(), quantity, unit_amount: unit, tax_rate: tax });
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <form className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.finance.chargeForm.type} htmlFor="cf-type"><Select id="cf-type" value={type} options={typeOptions} onChange={(e) => setType(e.target.value)} /></FormField>
          <FormField label={t.finance.chargeForm.description} htmlFor="cf-desc"><Input id="cf-desc" value={description} onChange={(e) => setDescription(e.target.value)} /></FormField>
          <FormField label={t.finance.chargeForm.quantity} htmlFor="cf-qty"><Input id="cf-qty" type="number" step="0.01" value={quantity} onChange={(e) => setQuantity(e.target.value)} /></FormField>
          <FormField label={t.finance.chargeForm.unitAmount} htmlFor="cf-unit"><Input id="cf-unit" type="number" step="0.01" value={unit} onChange={(e) => setUnit(e.target.value)} /></FormField>
          <FormField label={t.finance.chargeForm.taxRate} htmlFor="cf-tax"><Input id="cf-tax" type="number" step="0.01" value={tax} onChange={(e) => setTax(e.target.value)} /></FormField>
        </div>
        <div className="cluster"><Button type="submit" size="sm" loading={busy}>{t.finance.chargeForm.submit}</Button></div>
      </form>
    </Card>
  );
}

function PaymentForm({ folioId, onDone, onSavedContinue }: { folioId: number; onDone: () => void; onSavedContinue: () => void }) {
  const { t } = useI18n();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [payer, setPayer] = useState("");
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const methodOptions = (["cash", "card", "bank_transfer", "electronic", "other"] as const).map((v) => ({ value: v, label: t.finance.methods[v] }));

  async function save(addAnother: boolean) {
    setError(null);
    if (!amount) return setError(t.errors.validation);
    setBusy(true);
    try {
      await recordPayment(folioId, { amount, method, payer_name: payer.trim(), reference: reference.trim() });
      if (addAnother) {
        setAmount("");
        setReference("");
        onSavedContinue();
      } else {
        onDone();
      }
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await save(false);
  }

  return (
    <Card>
      <form className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.finance.paymentForm.amount} htmlFor="pf-amt"><Input id="pf-amt" type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} /></FormField>
          <FormField label={t.finance.paymentForm.method} htmlFor="pf-method"><Select id="pf-method" value={method} options={methodOptions} onChange={(e) => setMethod(e.target.value)} /></FormField>
          <FormField label={t.finance.paymentForm.payerName} htmlFor="pf-payer"><Input id="pf-payer" value={payer} onChange={(e) => setPayer(e.target.value)} /></FormField>
          <FormField label={t.finance.paymentForm.reference} htmlFor="pf-ref"><Input id="pf-ref" value={reference} onChange={(e) => setReference(e.target.value)} /></FormField>
        </div>
        <p className="muted small">{t.finance.paymentForm.mixedHint}</p>
        <p className="muted small">{t.finance.financeNote}</p>
        <div className="cluster">
          <Button type="submit" size="sm" loading={busy}>{t.finance.paymentForm.submit}</Button>
          <Button type="button" size="sm" variant="ghost" icon={Plus} disabled={busy} onClick={() => save(true)}>
            {t.finance.paymentForm.addAnother}
          </Button>
        </div>
      </form>
    </Card>
  );
}
