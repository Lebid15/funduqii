"use client";

import { useCallback, useEffect, useState } from "react";
import { FileCheck, Printer, ReceiptText } from "lucide-react";

import {
  Badge, Button, Card, DataTable, EmptyState, ErrorState, FilterBar, FormField,
  Input, LoadingState, Pagination, Select, useToast, type Column,
} from "@/components/ui";
import { getInvoicePrint, issueInvoice, listInvoices, voidInvoice } from "@/lib/api/finance";
import { messageForError } from "@/lib/api/errors";
import type { HotelHeader, Invoice } from "@/lib/api/types";
import { formatDate, formatMoney, invoiceStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { PrintModal, VoidDialog } from "./shared";

const PAGE_SIZE = 25;
const STATUSES = ["draft", "issued", "voided"] as const;

export function InvoicesTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [rows, setRows] = useState<Invoice[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [voidTarget, setVoidTarget] = useState<Invoice | null>(null);
  const [printDoc, setPrintDoc] = useState<{ hotel: HotelHeader; invoice: Invoice } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listInvoices({ page, status: status || undefined, search: query || undefined });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, status, query, t]);

  useEffect(() => { load(); }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: t.finance.invoiceStatus[s] }));

  async function doIssue(inv: Invoice) {
    try { await issueInvoice(inv.id); notify(t.finance.saved); load(); }
    catch (err) { notify(messageForError(err, t), "error"); }
  }

  async function openPrint(id: number) {
    try { const r = await getInvoicePrint(id); setPrintDoc({ hotel: r.hotel, invoice: r.invoice }); }
    catch (err) { notify(messageForError(err, t), "error"); }
  }

  const columns: Column<Invoice>[] = [
    { key: "invoice_number", header: t.finance.invoices.number, render: (r) => r.invoice_number || "—" },
    { key: "customer_name", header: t.finance.invoices.customer, render: (r) => r.customer_name || "—" },
    { key: "total", header: t.finance.invoices.total, render: (r) => formatMoney(r.total, r.currency, locale) },
    { key: "issued_at", header: t.finance.invoices.issuedAt, render: (r) => (r.issued_at ? formatDate(r.issued_at, locale) : "—") },
    { key: "status", header: t.common.status, render: (r) => <Badge tone={invoiceStatusTone(r.status)}>{t.finance.invoiceStatus[r.status]}</Badge> },
    {
      key: "actions", header: t.common.actions, align: "end",
      render: (r) => (
        <div className="table__actions">
          {r.status === "draft" ? <Button size="sm" icon={FileCheck} onClick={() => doIssue(r)}>{t.finance.invoices.issue}</Button> : null}
          {r.status === "issued" ? <Button size="sm" variant="secondary" icon={Printer} onClick={() => openPrint(r.id)}>{t.finance.invoices.print}</Button> : null}
          {r.status !== "voided" ? <Button size="sm" variant="danger" onClick={() => setVoidTarget(r)}>{t.finance.invoices.void}</Button> : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <Card>
        <form onSubmit={(e) => { e.preventDefault(); setPage(1); setQuery(search); }}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="inv-search"><Input id="inv-search" value={search} onChange={(e) => setSearch(e.target.value)} /></FormField>
            <FormField label={t.common.status} htmlFor="inv-status"><Select id="inv-status" value={status} placeholder={t.common.all} options={statusOptions} onChange={(e) => { setPage(1); setStatus(e.target.value); }} /></FormField>
          </FilterBar>
        </form>
      </Card>
      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} /> : null}
      {!loading && !error ? (
        rows.length === 0 ? <EmptyState title={t.finance.invoices.empty} hint={t.finance.invoices.emptyHint} icon={ReceiptText} /> : (
          <>
            <DataTable caption={t.finance.tabs.invoices} columns={columns} rows={rows} rowKey={(r) => r.id} />
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage}
              labels={{ previous: t.pagination.previous, next: t.pagination.next, status: t.pagination.page.replace("{page}", String(page)).replace("{total}", String(totalPages)) }} />
          </>
        )
      ) : null}

      <VoidDialog open={voidTarget !== null} onClose={() => setVoidTarget(null)}
        onConfirm={async (reason) => { if (voidTarget) { await voidInvoice(voidTarget.id, reason); setVoidTarget(null); notify(t.finance.saved); load(); } }} />
      <PrintModal open={printDoc !== null} title={t.finance.print.invoiceTitle} onClose={() => setPrintDoc(null)}>
        {printDoc ? (
          <div className="receipt">
            <h3>{printDoc.hotel.hotel_name}</h3>
            <p className="muted">{t.finance.print.invoiceTitle} · {printDoc.invoice.invoice_number}</p>
            <dl className="print-grid">
              <div><dt>{t.finance.print.customer}</dt><dd>{printDoc.invoice.customer_name || "—"}</dd></div>
              <div><dt>{t.finance.print.date}</dt><dd>{printDoc.invoice.issued_at ? formatDate(printDoc.invoice.issued_at, locale) : "—"}</dd></div>
            </dl>
            <table className="print-table">
              <thead><tr><th>{t.finance.chargeForm.description}</th><th>{t.finance.chargeForm.quantity}</th><th>{t.finance.print.total}</th></tr></thead>
              <tbody>
                {printDoc.invoice.lines.map((l) => (
                  <tr key={l.id}><td>{l.description}</td><td>{l.quantity}</td><td>{formatMoney(l.total_amount, printDoc.invoice.currency, locale)}</td></tr>
                ))}
              </tbody>
            </table>
            <dl className="print-grid print-grid--totals">
              <div><dt>{t.finance.print.subtotal}</dt><dd>{formatMoney(printDoc.invoice.subtotal, printDoc.invoice.currency, locale)}</dd></div>
              <div><dt>{t.finance.print.tax}</dt><dd>{formatMoney(printDoc.invoice.tax_total, printDoc.invoice.currency, locale)}</dd></div>
              <div><dt>{t.finance.print.total}</dt><dd><strong>{formatMoney(printDoc.invoice.total, printDoc.invoice.currency, locale)}</strong></dd></div>
            </dl>
          </div>
        ) : null}
      </PrintModal>
    </>
  );
}
