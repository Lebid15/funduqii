"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useQuickAction } from "@/lib/useQuickAction";
import {
  BellRing,
  ChefHat,
  ClipboardList,
  FileInput,
  PackageCheck,
  Plus,
  Printer,
  Trash2,
  XCircle,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  IconButton,
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
  cancelServiceOrder,
  createServiceOrder,
  getServiceOrder,
  getServiceOrderTicket,
  listServiceItems,
  listServiceOrders,
  postServiceOrderToFolio,
  setServiceOrderStatus,
  type ServiceOrderCreateBody,
  type ServiceOrderLineInput,
} from "@/lib/api/services";
import { listCurrentResidents } from "@/lib/api/stays";
import { messageForError } from "@/lib/api/errors";
import type {
  ServiceItem,
  ServiceOrder,
  ServiceOrderListItem,
  ServiceTicket,
  Stay,
} from "@/lib/api/types";
import { formatDateTime, formatMoney, serviceOrderStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { PrintModal } from "../finance/shared";

const PAGE_SIZE = 25;
const SOURCES = ["room_service", "restaurant", "cafe", "other"] as const;
const STATUSES = ["submitted", "preparing", "ready", "delivered", "cancelled"] as const;

export function OrdersTab() {
  const { t } = useI18n();
  const { notify } = useToast();

  const [rows, setRows] = useState<ServiceOrderListItem[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [postedFilter, setPostedFilter] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [creating, setCreating] = useState(false);
  // Topbar quick action: ?action=new opens the EXISTING order modal once.
  useQuickAction("new", () => setCreating(true));
  const [detail, setDetail] = useState<ServiceOrder | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listServiceOrders({
        page,
        search: query || undefined,
        status: statusFilter || undefined,
        source: sourceFilter || undefined,
        posted: postedFilter || undefined,
      });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, query, statusFilter, sourceFilter, postedFilter, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function openDetail(id: number) {
    try {
      setDetail(await getServiceOrder(id));
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: t.services.status[s] }));
  const sourceOptions = SOURCES.map((s) => ({ value: s, label: t.services.sources[s] }));

  const columns: Column<ServiceOrderListItem>[] = [
    { key: "order_number", header: t.services.orders.number },
    { key: "source", header: t.services.orders.source, render: (r) => t.services.sources[r.source] },
    { key: "room_number", header: t.services.orders.room, render: (r) => r.room_number || "—" },
    {
      key: "status",
      header: t.common.status,
      render: (r) => <Badge tone={serviceOrderStatusTone(r.status)}>{t.services.status[r.status]}</Badge>,
    },
    { key: "total", header: t.services.orders.total, render: (r) => (r.total ? r.total : "—") },
    {
      key: "is_posted",
      header: t.services.orders.posted,
      render: (r) => (
        <Badge tone={r.is_posted ? "success" : "neutral"}>
          {r.is_posted ? t.services.orders.postedYes : t.services.orders.postedNo}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => (
        <Button size="sm" variant="secondary" onClick={() => openDetail(r.id)}>
          {t.services.orders.details}
        </Button>
      ),
    },
  ];

  return (
    <>
      <Card>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            setQuery(search);
          }}
        >
          <FilterBar>
            <FormField label={t.common.search} htmlFor="ord-search">
              <Input id="ord-search" value={search} placeholder={t.services.orders.searchPlaceholder} onChange={(e) => setSearch(e.target.value)} />
            </FormField>
            <FormField label={t.common.status} htmlFor="ord-status">
              <Select id="ord-status" value={statusFilter} placeholder={t.common.all} options={statusOptions} onChange={(e) => { setPage(1); setStatusFilter(e.target.value); }} />
            </FormField>
            <FormField label={t.services.orders.source} htmlFor="ord-source">
              <Select id="ord-source" value={sourceFilter} placeholder={t.common.all} options={sourceOptions} onChange={(e) => { setPage(1); setSourceFilter(e.target.value); }} />
            </FormField>
            <FormField label={t.services.orders.posted} htmlFor="ord-posted">
              <Select
                id="ord-posted"
                value={postedFilter}
                placeholder={t.common.all}
                options={[
                  { value: "true", label: t.services.orders.postedYes },
                  { value: "false", label: t.services.orders.postedNo },
                ]}
                onChange={(e) => { setPage(1); setPostedFilter(e.target.value); }}
              />
            </FormField>
            <div className="filter-bar__actions cluster">
              <Button icon={Plus} onClick={() => setCreating(true)}>{t.services.orders.addOrder}</Button>
            </div>
          </FilterBar>
        </form>
      </Card>

      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? (
        <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} />
      ) : null}
      {!loading && !error ? (
        rows.length === 0 ? (
          <EmptyState
            title={t.services.orders.empty}
            hint={t.services.orders.emptyHint}
            icon={ClipboardList}
            action={<Button icon={Plus} onClick={() => setCreating(true)}>{t.services.orders.addOrder}</Button>}
          />
        ) : (
          <>
            <DataTable caption={t.services.tabs.orders} columns={columns} rows={rows} rowKey={(r) => r.id} />
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
          </>
        )
      ) : null}

      <OrderCreateModal
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(order) => {
          setCreating(false);
          notify(t.services.saved);
          load();
          setDetail(order);
        }}
      />
      <OrderDetailsModal
        order={detail}
        onClose={() => setDetail(null)}
        onChanged={(order) => {
          setDetail(order);
          load();
        }}
      />
    </>
  );
}

/* ------------------------------------------------------------------------- */
/* Create                                                                      */
/* ------------------------------------------------------------------------- */

function OrderCreateModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: (order: ServiceOrder) => void;
}) {
  const { t, locale } = useI18n();
  const [stays, setStays] = useState<Stay[]>([]);
  const [catalog, setCatalog] = useState<ServiceItem[]>([]);
  const [form, setForm] = useState<ServiceOrderCreateBody>({ source: "room_service", items: [] });
  const [lines, setLines] = useState<ServiceOrderLineInput[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({ source: "room_service", items: [], stay: null, notes: "" });
    setLines([]);
    setError(null);
    listCurrentResidents()
      .then((r) => setStays(r.results))
      .catch(() => setStays([]));
    listServiceItems({ is_active: "true", is_available: "true", page: 1 })
      .then((r) => setCatalog(r.results))
      .catch(() => setCatalog([]));
  }, [open]);

  function addLine() {
    if (catalog.length === 0) return;
    setLines((prev) => [...prev, { service_item: catalog[0].id, quantity: "1", notes: "" }]);
  }

  function setLine(index: number, patch: Partial<ServiceOrderLineInput>) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  }

  function removeLine(index: number) {
    setLines((prev) => prev.filter((_, i) => i !== index));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (lines.length === 0) return setError(t.services.errors.itemsRequired);
    setBusy(true);
    setError(null);
    try {
      const order = await createServiceOrder({
        ...form,
        stay: form.stay || null,
        items: lines,
      });
      onSaved(order);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const sourceOptions = SOURCES.map((s) => ({ value: s, label: t.services.sources[s] }));
  const stayOptions = stays.map((s) => ({
    value: String(s.id),
    label: `${s.room_number ?? s.room} — ${s.primary_guest_name ?? ""}`.trim(),
  }));
  const itemOptions = catalog.map((i) => ({
    value: String(i.id),
    label: `${i.name} (${formatMoney(i.unit_price, i.currency, locale)})`,
  }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.services.orders.createTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="svc-order-form" type="submit" loading={busy}>{t.services.orders.submit}</Button>
        </>
      }
    >
      <form id="svc-order-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.services.orders.source} htmlFor="o-source">
            <Select id="o-source" value={form.source ?? "room_service"} options={sourceOptions} onChange={(e) => setForm((p) => ({ ...p, source: e.target.value }))} />
          </FormField>
          <FormField label={t.services.orders.stay} htmlFor="o-stay">
            <Select
              id="o-stay"
              value={form.stay ? String(form.stay) : ""}
              placeholder={t.services.orders.walkIn}
              options={stayOptions}
              onChange={(e) => setForm((p) => ({ ...p, stay: e.target.value ? Number(e.target.value) : null }))}
            />
          </FormField>
          <FormField label={t.services.orders.requestedTime} htmlFor="o-time">
            <Input
              id="o-time"
              type="time"
              value={form.requested_delivery_time ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, requested_delivery_time: e.target.value || null }))}
            />
          </FormField>
        </div>

        <div className="stack">
          <div className="cluster">
            <strong>{t.services.orders.itemsSection}</strong>
            <Button size="sm" variant="secondary" icon={Plus} onClick={addLine} type="button" disabled={catalog.length === 0}>
              {t.services.orders.addLine}
            </Button>
          </div>
          {lines.length === 0 ? <p className="muted">{t.services.orders.noLines}</p> : null}
          {lines.map((line, index) => (
            <div className="form-grid" key={index}>
              <FormField label={t.services.orders.item} htmlFor={`l-item-${index}`}>
                <Select
                  id={`l-item-${index}`}
                  value={String(line.service_item)}
                  options={itemOptions}
                  onChange={(e) => setLine(index, { service_item: Number(e.target.value) })}
                />
              </FormField>
              <FormField label={t.services.orders.quantity} htmlFor={`l-qty-${index}`}>
                <Input
                  id={`l-qty-${index}`}
                  type="number"
                  min="1"
                  step="1"
                  value={line.quantity}
                  onChange={(e) => setLine(index, { quantity: e.target.value })}
                />
              </FormField>
              <FormField label={t.services.orders.lineNotes} htmlFor={`l-notes-${index}`}>
                <div className="cluster">
                  <Input
                    id={`l-notes-${index}`}
                    value={line.notes ?? ""}
                    onChange={(e) => setLine(index, { notes: e.target.value })}
                  />
                  <IconButton icon={Trash2} label={t.services.orders.removeLine} type="button" onClick={() => removeLine(index)} />
                </div>
              </FormField>
            </div>
          ))}
          <p className="muted small">{t.services.orders.totalAfterSave}</p>
        </div>

        <FormField label={t.services.orders.notes} htmlFor="o-notes">
          <Textarea id="o-notes" value={form.notes ?? ""} onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))} />
        </FormField>
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------------- */
/* Details                                                                     */
/* ------------------------------------------------------------------------- */

function OrderDetailsModal({
  order,
  onClose,
  onChanged,
}: {
  order: ServiceOrder | null;
  onClose: () => void;
  onChanged: (order: ServiceOrder) => void;
}) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [postConfirm, setPostConfirm] = useState(false);
  const [ticket, setTicket] = useState<ServiceTicket | null>(null);

  useEffect(() => {
    setCancelOpen(false);
    setCancelReason("");
    setPostConfirm(false);
  }, [order?.id]);

  if (!order) return null;

  async function run(action: () => Promise<ServiceOrder>) {
    setBusy(true);
    try {
      const updated = await action();
      onChanged(updated);
      notify(t.services.saved);
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusy(false);
    }
  }

  async function openTicket() {
    try {
      setTicket(await getServiceOrderTicket(order!.id));
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  const itemColumns: Column<ServiceOrder["items"][number]>[] = [
    { key: "item_name", header: t.services.orders.item },
    { key: "quantity", header: t.services.orders.quantity },
    { key: "unit_price", header: t.services.catalog.price },
    { key: "tax_amount", header: t.services.orders.tax },
    { key: "total_amount", header: t.services.orders.total },
  ];

  const canAdvance = ["submitted", "preparing", "ready"].includes(order.status);
  const canCancel = !order.is_posted && order.status !== "cancelled";
  const canPost = order.status === "delivered" && !order.is_posted;

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title={`${t.services.orders.details} · ${order.order_number}`}
        closeLabel={t.common.close}
        footer={
          <>
            <Button variant="secondary" icon={Printer} onClick={openTicket} disabled={busy}>
              {t.services.ticket.title}
            </Button>
            {order.status === "submitted" ? (
              <Button icon={ChefHat} onClick={() => run(() => setServiceOrderStatus(order.id, "preparing"))} loading={busy}>
                {t.services.orders.markPreparing}
              </Button>
            ) : null}
            {["submitted", "preparing"].includes(order.status) ? (
              <Button icon={BellRing} onClick={() => run(() => setServiceOrderStatus(order.id, "ready"))} loading={busy}>
                {t.services.orders.markReady}
              </Button>
            ) : null}
            {canAdvance ? (
              <Button icon={PackageCheck} onClick={() => run(() => setServiceOrderStatus(order.id, "delivered"))} loading={busy}>
                {t.services.orders.markDelivered}
              </Button>
            ) : null}
            {canPost ? (
              <Button icon={FileInput} onClick={() => setPostConfirm(true)} loading={busy}>
                {t.services.orders.postToFolio}
              </Button>
            ) : null}
            {canCancel ? (
              <Button variant="danger" icon={XCircle} onClick={() => setCancelOpen(true)} disabled={busy}>
                {t.services.orders.cancel}
              </Button>
            ) : null}
          </>
        }
      >
        <div className="stack">
          <div className="cluster">
            <Badge tone={serviceOrderStatusTone(order.status)}>{t.services.status[order.status]}</Badge>
            <Badge tone="neutral">{t.services.sources[order.source]}</Badge>
            {order.is_posted ? <Badge tone="success">{t.services.orders.postedYes}</Badge> : null}
          </div>
          <StatusSummaryCard
            items={[
              { label: t.services.orders.room, value: order.room_number || "—" },
              { label: t.services.orders.guest, value: order.guest_name || "—" },
              { label: t.services.orders.orderedAt, value: formatDateTime(order.ordered_at, locale) },
              ...(order.folio_number
                ? [{ label: t.services.orders.folio, value: order.folio_number }]
                : []),
              ...(order.posted_charge_number
                ? [{ label: t.services.orders.chargeRef, value: order.posted_charge_number }]
                : []),
            ]}
          />
          <DataTable caption={t.services.orders.itemsSection} columns={itemColumns} rows={order.items} rowKey={(r) => r.id} />
          <StatusSummaryCard
            title={t.services.orders.totalsTitle}
            items={[
              { label: t.services.orders.subtotal, value: order.totals.subtotal },
              { label: t.services.orders.tax, value: order.totals.tax_total },
              { label: t.services.orders.total, value: order.totals.total, emphasis: true },
            ]}
          />
          {order.status === "cancelled" && order.cancellation_reason ? (
            <Alert tone="warning">{`${t.services.orders.cancelReason}: ${order.cancellation_reason}`}</Alert>
          ) : null}
          {canPost ? <Alert tone="warning">{t.services.orders.postHint}</Alert> : null}
          {order.notes ? <p className="muted">{`${t.services.orders.notes}: ${order.notes}`}</p> : null}
        </div>
      </Modal>

      <Modal
        open={cancelOpen}
        onClose={() => setCancelOpen(false)}
        title={t.services.orders.cancelTitle}
        closeLabel={t.common.close}
        footer={
          <>
            <Button variant="secondary" onClick={() => setCancelOpen(false)} disabled={busy}>{t.common.cancel}</Button>
            <Button
              variant="danger"
              loading={busy}
              onClick={async () => {
                if (!cancelReason.trim()) return;
                await run(() => cancelServiceOrder(order.id, cancelReason.trim()));
                setCancelOpen(false);
              }}
            >
              {t.services.orders.cancelConfirm}
            </Button>
          </>
        }
      >
        <div className="stack">
          <FormField label={t.services.orders.cancelReason} htmlFor="o-cancel-reason">
            <Textarea id="o-cancel-reason" value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} />
          </FormField>
        </div>
      </Modal>

      <ConfirmDialog
        open={postConfirm}
        title={t.services.orders.postConfirmTitle}
        body={t.services.orders.postConfirmBody}
        confirmLabel={t.services.orders.postToFolio}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        busy={busy}
        onClose={() => setPostConfirm(false)}
        onConfirm={async () => {
          await run(() => postServiceOrderToFolio(order.id));
          setPostConfirm(false);
        }}
      />

      <PrintModal open={ticket !== null} title={t.services.ticket.title} onClose={() => setTicket(null)}>
        {ticket ? (
          <PrintDocumentLayout
            hotelName={ticket.hotel.hotel_name}
            hotelAddress={ticket.hotel.address}
            hotelPhone={ticket.hotel.phone}
            docTitle={t.services.ticket.title}
            docNumber={ticket.order.order_number}
            meta={[
              { label: t.services.orders.source, value: t.services.sources[ticket.order.source] },
              { label: t.services.ticket.roomLabel, value: ticket.order.room_number || "—" },
              { label: t.services.ticket.guestLabel, value: ticket.order.guest_name || "—" },
              { label: t.services.ticket.timeLabel, value: formatDateTime(ticket.order.ordered_at, locale) },
              ...(ticket.order.requested_delivery_time
                ? [{ label: t.services.orders.requestedTime, value: ticket.order.requested_delivery_time }]
                : []),
            ]}
            totals={[
              { label: t.services.orders.subtotal, value: ticket.totals.subtotal },
              { label: t.services.orders.tax, value: ticket.totals.tax_total },
              { label: t.services.orders.total, value: <strong>{ticket.totals.total}</strong> },
            ]}
            notes={ticket.order.notes || undefined}
            notesLabel={t.services.orders.notes}
          >
            <table className="print-table">
              <thead>
                <tr>
                  <th>{t.services.orders.item}</th>
                  <th>{t.services.ticket.qty}</th>
                  <th>{t.services.ticket.price}</th>
                  <th>{t.services.ticket.lineTotal}</th>
                </tr>
              </thead>
              <tbody>
                {ticket.items.map((i, idx) => (
                  <tr key={idx}>
                    <td>{i.item_name}</td>
                    <td>{i.quantity}</td>
                    <td>{i.unit_price}</td>
                    <td>{i.total_amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PrintDocumentLayout>
        ) : null}
      </PrintModal>
    </>
  );
}
