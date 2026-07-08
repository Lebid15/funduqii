"use client";

import { useCallback, useEffect, useState } from "react";
import { Printer, Receipt } from "lucide-react";

import {
  Badge, Button, Card, DataTable, EmptyState, ErrorState, FilterBar, FormField,
  LoadingState, Pagination, PrintDocumentLayout, Select, useToast, type Column,
} from "@/components/ui";
import { getReceipt, listPayments, voidPayment } from "@/lib/api/finance";
import { messageForError } from "@/lib/api/errors";
import type { HotelHeader, Payment } from "@/lib/api/types";
import { formatDate, formatMoney, postingStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { PrintModal, VoidDialog } from "./shared";

const PAGE_SIZE = 25;

export function PaymentsTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [rows, setRows] = useState<Payment[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [method, setMethod] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [voidTarget, setVoidTarget] = useState<Payment | null>(null);
  const [receipt, setReceipt] = useState<{ hotel: HotelHeader; payment: Payment } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listPayments({ page, method: method || undefined });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, method, t]);

  useEffect(() => { load(); }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const methodOptions = (["cash", "card", "bank_transfer", "electronic", "other"] as const).map((v) => ({ value: v, label: t.finance.methods[v] }));

  async function openReceipt(id: number) {
    try {
      const r = await getReceipt(id);
      setReceipt({ hotel: r.hotel, payment: r.payment });
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  const columns: Column<Payment>[] = [
    { key: "receipt_number", header: t.finance.payments.number },
    { key: "folio_number", header: t.finance.tabs.folios },
    { key: "amount", header: t.finance.payments.amount, render: (r) => formatMoney(r.amount, r.currency, locale) },
    { key: "method", header: t.finance.payments.method, render: (r) => t.finance.methods[r.method] },
    { key: "paid_at", header: t.finance.payments.date, render: (r) => formatDate(r.paid_at, locale) },
    { key: "status", header: t.common.status, render: (r) => <Badge tone={postingStatusTone(r.status)}>{t.finance.postingStatus[r.status]}</Badge> },
    {
      key: "actions", header: t.common.actions, align: "end",
      render: (r) => (
        <div className="table__actions">
          <Button size="sm" variant="secondary" icon={Printer} onClick={() => openReceipt(r.id)}>{t.finance.payments.receipt}</Button>
          {r.status === "posted" ? <Button size="sm" variant="danger" onClick={() => setVoidTarget(r)}>{t.finance.payments.void}</Button> : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <Card>
        <FilterBar>
          <FormField label={t.finance.payments.method} htmlFor="pay-method">
            <Select id="pay-method" value={method} placeholder={t.common.all} options={methodOptions} onChange={(e) => { setPage(1); setMethod(e.target.value); }} />
          </FormField>
        </FilterBar>
      </Card>
      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} /> : null}
      {!loading && !error ? (
        rows.length === 0 ? <EmptyState title={t.finance.payments.empty} hint={t.finance.payments.emptyHint} icon={Receipt} /> : (
          <>
            <DataTable caption={t.finance.tabs.payments} columns={columns} rows={rows} rowKey={(r) => r.id} />
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage}
              labels={{ previous: t.pagination.previous, next: t.pagination.next, status: t.pagination.page.replace("{page}", String(page)).replace("{total}", String(totalPages)) }} />
          </>
        )
      ) : null}

      <VoidDialog open={voidTarget !== null} onClose={() => setVoidTarget(null)}
        onConfirm={async (reason) => { if (voidTarget) { await voidPayment(voidTarget.id, reason); setVoidTarget(null); notify(t.finance.saved); load(); } }} />
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
    </>
  );
}
