"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { useQuickAction } from "@/lib/useQuickAction";
import {
  Armchair,
  BellRing,
  ChefHat,
  ClipboardList,
  Clock,
  Coins,
  Eye,
  FileInput,
  HandCoins,
  LayoutGrid,
  List,
  PackageCheck,
  Plus,
  Printer,
  ReceiptText,
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
  OperationCard,
  type OperationFact,
  type OperationMenuItem,
  type OperationPrimaryAction,
} from "@/components/hotel/operations/OperationCard";
import {
  cancelServiceOrder,
  cancelServiceOrderItem,
  createServiceOrder,
  getServiceOrder,
  getServiceOrderTicket,
  listServiceItems,
  listServiceOrders,
  listTables,
  postServiceOrderToFolio,
  setServiceOrderStatus,
  settleServiceOrderDirect,
  type ServiceOrderLineInput,
} from "@/lib/api/services";
import { getReceipt } from "@/lib/api/finance";
import { listCurrentResidents } from "@/lib/api/stays";
import { messageForError } from "@/lib/api/errors";
import type {
  HotelHeader,
  Payment,
  PaymentMethod,
  RestaurantTable,
  ServiceItem,
  ServiceOrder,
  ServiceOrderItem,
  ServiceOrderListItem,
  ServiceOrderSettlement,
  ServiceOrderStatus,
  ServiceOutlet,
  ServiceTicket,
  Stay,
} from "@/lib/api/types";
import {
  formatDate,
  formatDateTime,
  formatMoney,
  serviceOrderStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { PrintModal } from "../finance/shared";
import { BoardTab } from "./BoardTab";
import { TablesTab } from "./TablesTab";
import { useEnabledOutlets } from "./useOutlets";

/** Which sub-flow of OrderDetailsModal a "More" menu item should pre-open. */
type OrderIntent = "post" | "settle" | "cancel" | "kot" | "guest_check" | "receipt";

/** The list is shown as cards; the prep board is folded in as a view MODE. */
type OrdersView = "list" | "board";

/** State-driven single primary action for an order card (kitchen advance). */
const STATUS_ADVANCE: Partial<
  Record<ServiceOrderStatus, { next: ServiceOrderStatus; labelKey: "markPreparing" | "markReady" | "markDelivered"; icon: typeof ChefHat }>
> = {
  submitted: { next: "preparing", labelKey: "markPreparing", icon: ChefHat },
  preparing: { next: "ready", labelKey: "markReady", icon: BellRing },
  ready: { next: "delivered", labelKey: "markDelivered", icon: PackageCheck },
};

const PAGE_SIZE = 25;
const ORDER_TYPES = ["room", "table"] as const;
const STATUSES = ["submitted", "preparing", "ready", "delivered", "cancelled"] as const;
const PAYMENT_METHODS: PaymentMethod[] = [
  "cash",
  "card",
  "bank_transfer",
  "electronic",
  "other",
];

/** Cosmetic permission gate — every API re-checks server-side regardless. */
function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

function settlementTone(settlement: ServiceOrderSettlement): "neutral" | "success" | "info" {
  if (settlement === "direct") return "success";
  if (settlement === "folio") return "info";
  return "neutral";
}

export function OrdersTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const can = useCan();

  const [rows, setRows] = useState<ServiceOrderListItem[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [outletFilter, setOutletFilter] = useState("");
  const [settlementFilter, setSettlementFilter] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  // Prep board is now a VIEW MODE inside Orders; table management is a modal.
  const [view, setView] = useState<OrdersView>("list");
  const [tablesOpen, setTablesOpen] = useState(false);

  const [creating, setCreating] = useState(false);
  // Topbar quick action: ?action=new opens the EXISTING order modal once.
  useQuickAction("new", () => setCreating(true));
  const [detail, setDetail] = useState<ServiceOrder | null>(null);
  const [detailAction, setDetailAction] = useState<OrderIntent | null>(null);
  const [advancingId, setAdvancingId] = useState<number | null>(null);

  const loadedOnceRef = useRef(false);
  const mountedRef = useRef(true);
  const seqRef = useRef(0);
  const resultsRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef(false);

  const canManageTables = can("services.tables_manage");

  const load = useCallback(async () => {
    const seq = (seqRef.current += 1);
    setLoading(true);
    setError(null);
    try {
      const data = await listServiceOrders({
        page,
        search: query || undefined,
        status: statusFilter || undefined,
        order_type: typeFilter || undefined,
        outlet: outletFilter || undefined,
        settlement: settlementFilter || undefined,
      });
      if (seqRef.current !== seq) return;
      setRows(data.results);
      setCount(data.count);
      loadedOnceRef.current = true;
      setHasLoadedOnce(true);
    } catch (err) {
      if (seqRef.current !== seq) return;
      const message = messageForError(err, t);
      // Background refetch failure keeps the cards + a non-blocking toast; the
      // full ErrorState + retry is reserved for the very first load.
      if (loadedOnceRef.current) notify(message, "error");
      else setError(message);
    } finally {
      if (mountedRef.current && seqRef.current === seq) setLoading(false);
    }
  }, [page, query, statusFilter, typeFilter, outletFilter, settlementFilter, t, notify]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // After an action-triggered reload settles, restore focus to the stable
  // results anchor if the acting control (e.g. a card that changed status and
  // moved between filters) unmounted.
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

  // Card "More" items open the SINGLE reused OrderDetailsModal, pre-triggered to
  // the requested sub-flow — no order-mutation logic is duplicated here.
  async function openDetailWith(id: number, action: OrderIntent | null) {
    try {
      const full = await getServiceOrder(id);
      setDetailAction(action);
      setDetail(full);
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  async function advanceStatus(r: ServiceOrderListItem, next: ServiceOrderStatus) {
    setAdvancingId(r.id);
    try {
      await setServiceOrderStatus(r.id, next);
      notify(t.services.saved);
      await reloadAfterAction();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setAdvancingId(null);
    }
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: t.services.status[s] }));
  const typeOptions = ORDER_TYPES.map((v) => ({ value: v, label: t.services.orderTypes[v] }));
  const outletOptions = (["restaurant", "cafe"] as const).map((o) => ({
    value: o,
    label: t.services.outlets[o],
  }));
  const settlementOptions = (["unsettled", "direct", "folio"] as const).map((s) => ({
    value: s,
    label: t.services.settlement[s],
  }));

  function renderCard(r: ServiceOrderListItem) {
    const location =
      r.order_type === "room" ? (
        <span>
          {t.services.orders.room} <bdi dir="ltr">{r.room_number || "—"}</bdi>
        </span>
      ) : (
        <span>
          {t.services.orders.table} <bdi dir="ltr">{r.table_number || "—"}</bdi>
        </span>
      );

    const facts: OperationFact[] = [
      {
        key: "orderedAt",
        label: t.services.orders.orderedAt,
        value: formatDateTime(r.ordered_at, locale),
        icon: Clock,
      },
      {
        key: "total",
        label: t.services.orders.total,
        value: <bdi dir="ltr">{r.total ?? "—"}</bdi>,
        icon: Coins,
      },
    ];
    if (r.order_type === "table" && r.customer_name) {
      facts.push({
        key: "customer",
        label: t.services.orders.customerName,
        value: r.customer_name,
      });
    }

    // ONE state-driven primary: the kitchen status advance. Terminal states
    // (delivered/cancelled) have no advance, so the primary opens Details.
    const advance = STATUS_ADVANCE[r.status];
    let primary: OperationPrimaryAction | null;
    if (advance) {
      primary = {
        label: t.services.orders[advance.labelKey],
        icon: advance.icon,
        loading: advancingId === r.id,
        onClick: () => advanceStatus(r, advance.next),
      };
    } else {
      primary = {
        label: t.services.orders.details,
        icon: Eye,
        variant: "secondary",
        onClick: () => openDetailWith(r.id, null),
      };
    }

    const menu: OperationMenuItem[] = [
      {
        key: "details",
        label: t.services.orders.details,
        icon: Eye,
        onSelect: () => openDetailWith(r.id, null),
      },
    ];
    const isPostable =
      r.status === "delivered" &&
      r.settlement === "unsettled" &&
      !r.is_posted &&
      r.stay !== null;
    if (isPostable) {
      menu.push({
        key: "post",
        label: t.services.orders.postToFolio,
        icon: FileInput,
        onSelect: () => openDetailWith(r.id, "post"),
      });
    }
    if (
      r.status === "delivered" &&
      r.settlement === "unsettled" &&
      can("service_orders.settle_direct")
    ) {
      menu.push({
        key: "settle",
        label: t.services.orders.directPayment,
        icon: HandCoins,
        onSelect: () => openDetailWith(r.id, "settle"),
      });
    }
    menu.push({
      key: "kot",
      label: t.services.ticket.title,
      icon: Printer,
      onSelect: () => openDetailWith(r.id, "kot"),
    });
    menu.push({
      key: "guest_check",
      label: t.services.ticket.guestCheckTitle,
      icon: Printer,
      onSelect: () => openDetailWith(r.id, "guest_check"),
    });
    if (r.settlement === "direct") {
      menu.push({
        key: "receipt",
        label: t.services.orders.printReceipt,
        icon: ReceiptText,
        onSelect: () => openDetailWith(r.id, "receipt"),
      });
    }
    if (r.settlement === "unsettled" && r.status !== "cancelled") {
      menu.push({
        key: "cancel",
        label: t.services.orders.cancel,
        icon: XCircle,
        danger: true,
        onSelect: () => openDetailWith(r.id, "cancel"),
      });
    }

    return (
      <OperationCard
        accent={serviceOrderStatusTone(r.status)}
        number={r.order_number}
        title={location}
        ariaLabel={`${t.services.tabs.orders} ${r.order_number}`}
        moreLabel={t.services.orders.more}
        badges={
          <>
            <Badge tone={serviceOrderStatusTone(r.status)}>{t.services.status[r.status]}</Badge>
            <Badge tone={settlementTone(r.settlement)}>{t.services.settlement[r.settlement]}</Badge>
            <Badge tone="neutral" variant="outline">
              {t.services.outlets[r.outlet]}
            </Badge>
          </>
        }
        facts={facts}
        primary={primary}
        menu={menu}
      />
    );
  }

  const showInitialLoading = loading && !hasLoadedOnce;
  const showInitialError = !showInitialLoading && !hasLoadedOnce && error !== null;
  const backgroundRefreshing = loading && hasLoadedOnce;

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
            {view === "list" ? (
              <>
                <FormField label={t.common.search} htmlFor="ord-search">
                  <Input id="ord-search" value={search} placeholder={t.services.orders.searchPlaceholder} onChange={(e) => setSearch(e.target.value)} />
                </FormField>
                <FormField label={t.common.status} htmlFor="ord-status">
                  <Select id="ord-status" value={statusFilter} placeholder={t.common.all} options={statusOptions} onChange={(e) => { setPage(1); setStatusFilter(e.target.value); }} />
                </FormField>
                <FormField label={t.services.orderType} htmlFor="ord-type">
                  <Select id="ord-type" value={typeFilter} placeholder={t.common.all} options={typeOptions} onChange={(e) => { setPage(1); setTypeFilter(e.target.value); }} />
                </FormField>
                <FormField label={t.services.outlet} htmlFor="ord-outlet">
                  <Select id="ord-outlet" value={outletFilter} placeholder={t.common.all} options={outletOptions} onChange={(e) => { setPage(1); setOutletFilter(e.target.value); }} />
                </FormField>
                <FormField label={t.services.settlementLabel} htmlFor="ord-settlement">
                  <Select
                    id="ord-settlement"
                    value={settlementFilter}
                    placeholder={t.common.all}
                    options={settlementOptions}
                    onChange={(e) => { setPage(1); setSettlementFilter(e.target.value); }}
                  />
                </FormField>
              </>
            ) : null}
            <div className="filter-bar__actions cluster">
              <div className="cluster" role="group" aria-label={t.services.view.label}>
                <Button
                  type="button"
                  size="sm"
                  variant={view === "list" ? "primary" : "secondary"}
                  icon={List}
                  aria-pressed={view === "list"}
                  onClick={() => setView("list")}
                >
                  {t.services.view.list}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={view === "board" ? "primary" : "secondary"}
                  icon={LayoutGrid}
                  aria-pressed={view === "board"}
                  onClick={() => setView("board")}
                >
                  {t.services.view.board}
                </Button>
              </div>
              {canManageTables ? (
                <Button type="button" variant="secondary" icon={Armchair} onClick={() => setTablesOpen(true)}>
                  {t.services.manageTables}
                </Button>
              ) : null}
              <Button icon={Plus} onClick={() => setCreating(true)}>{t.services.orders.addOrder}</Button>
            </div>
          </FilterBar>
        </form>
      </Card>

      {view === "board" ? (
        <BoardTab />
      ) : (
        <>
          {showInitialLoading ? <LoadingState label={t.common.loading} /> : null}
          {showInitialError ? (
            <ErrorState title={t.states.errorTitle} message={error ?? ""} retryLabel={t.common.retry} onRetry={load} />
          ) : null}
          {!showInitialLoading && !showInitialError ? (
            <div className="op-results" ref={resultsRef} tabIndex={-1} aria-label={t.services.tabs.orders}>
              <div className="op-results__status" role="status" aria-live="polite">
                {backgroundRefreshing ? (
                  <span className="op-results__searching">
                    <span className="spinner" aria-hidden="true" />
                    <span>{t.operations.updating}</span>
                  </span>
                ) : null}
              </div>
              {rows.length === 0 ? (
                <EmptyState
                  title={t.services.orders.empty}
                  hint={t.services.orders.emptyHint}
                  icon={ClipboardList}
                  action={<Button icon={Plus} onClick={() => setCreating(true)}>{t.services.orders.addOrder}</Button>}
                />
              ) : (
                <div className="op-grid" role="list" aria-label={t.services.tabs.orders} aria-busy={backgroundRefreshing}>
                  {rows.map((r) => (
                    <div role="listitem" key={r.id}>
                      {renderCard(r)}
                    </div>
                  ))}
                </div>
              )}
              {rows.length > 0 ? (
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
        </>
      )}

      <Modal
        open={tablesOpen}
        onClose={() => setTablesOpen(false)}
        title={t.services.manageTables}
        closeLabel={t.common.close}
        size="xl"
      >
        {/* Reuses the whole table-management surface (CRUD + out-of-service +
            launch-order) with zero duplicated logic. Same services.tables_manage
            gating applies inside. */}
        <TablesTab />
      </Modal>

      <OrderCreateModal
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(order) => {
          setCreating(false);
          notify(t.services.saved);
          load();
          setDetailAction(null);
          setDetail(order);
        }}
      />
      <OrderDetailsModal
        order={detail}
        initialAction={detailAction}
        onClose={() => {
          setDetail(null);
          setDetailAction(null);
        }}
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

export function OrderCreateModal({
  open,
  onClose,
  onSaved,
  initialOutlet,
  initialTable,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: (order: ServiceOrder) => void;
  /** Prefill (TablesTab shortcut): opens as a table order on this outlet. */
  initialOutlet?: ServiceOutlet;
  initialTable?: number;
}) {
  const { t, locale } = useI18n();
  const enabledOutlets = useEnabledOutlets();
  const [orderType, setOrderType] = useState<"room" | "table">("room");
  const [outlet, setOutlet] = useState<ServiceOutlet>("restaurant");
  const [stayId, setStayId] = useState<number | null>(null);
  const [tableId, setTableId] = useState<number | null>(null);
  const [customerName, setCustomerName] = useState("");
  const [requestedTime, setRequestedTime] = useState("");
  const [notes, setNotes] = useState("");
  const [stays, setStays] = useState<Stay[]>([]);
  const [tables, setTables] = useState<RestaurantTable[]>([]);
  const [catalog, setCatalog] = useState<ServiceItem[]>([]);
  const [lines, setLines] = useState<ServiceOrderLineInput[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setOrderType(initialTable ? "table" : "room");
    setOutlet(initialOutlet ?? enabledOutlets[0] ?? "restaurant");
    setStayId(null);
    setTableId(initialTable ?? null);
    setCustomerName("");
    setRequestedTime("");
    setNotes("");
    setLines([]);
    setError(null);
    listCurrentResidents()
      .then((r) => setStays(r.results))
      .catch(() => setStays([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when (re)opened
  }, [open, initialOutlet, initialTable]);

  // The catalog follows the outlet — items must belong to the order's outlet.
  useEffect(() => {
    if (!open) return;
    listServiceItems({ is_active: "true", is_available: "true", outlet, page: 1 })
      .then((r) => setCatalog(r.results))
      .catch(() => setCatalog([]));
  }, [open, outlet]);

  // Free tables of the chosen outlet (table orders only).
  useEffect(() => {
    if (!open || orderType !== "table") return;
    listTables({ outlet, status: "available" })
      .then((r) => setTables(r.results.filter((row) => !row.is_occupied)))
      .catch(() => setTables([]));
  }, [open, orderType, outlet]);

  function changeOutlet(next: ServiceOutlet) {
    setOutlet(next);
    // Lines reference items of the previous outlet; a mixed order is invalid.
    setLines([]);
    setTableId(null);
  }

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
    if (orderType === "room" && !stayId) return setError(t.errors.validation);
    if (orderType === "table" && !tableId) return setError(t.errors.validation);
    setBusy(true);
    setError(null);
    try {
      const order = await createServiceOrder({
        order_type: orderType,
        outlet,
        stay: stayId || null,
        table: orderType === "table" ? tableId : null,
        customer_name: orderType === "table" ? customerName.trim() : "",
        requested_delivery_time: requestedTime || null,
        notes,
        items: lines,
      });
      onSaved(order);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const typeOptions = ORDER_TYPES.map((v) => ({ value: v, label: t.services.orderTypes[v] }));
  const outletOptions = enabledOutlets.map((o) => ({ value: o, label: t.services.outlets[o] }));
  const stayOptions = stays.map((s) => ({
    value: String(s.id),
    label: `${s.room_number ?? s.room} — ${s.primary_guest_name ?? ""}`.trim(),
  }));
  const tableOptions = tables.map((row) => ({
    value: String(row.id),
    label: row.name ? `${row.number} — ${row.name}` : row.number,
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
          <FormField label={t.services.orderType} htmlFor="o-type">
            <Select
              id="o-type"
              value={orderType}
              options={typeOptions}
              onChange={(e) => {
                setOrderType(e.target.value as "room" | "table");
                setTableId(null);
              }}
            />
          </FormField>
          <FormField label={t.services.outlet} htmlFor="o-outlet">
            <Select
              id="o-outlet"
              value={outlet}
              options={outletOptions}
              onChange={(e) => changeOutlet(e.target.value as ServiceOutlet)}
            />
          </FormField>
          {orderType === "table" ? (
            <FormField label={t.services.orders.table} htmlFor="o-table">
              <Select
                id="o-table"
                value={tableId ? String(tableId) : ""}
                placeholder={
                  tables.length === 0 ? t.services.orders.noTablesAvailable : t.common.required
                }
                options={tableOptions}
                onChange={(e) => setTableId(e.target.value ? Number(e.target.value) : null)}
              />
            </FormField>
          ) : null}
          <FormField label={t.services.orders.stay} htmlFor="o-stay">
            <Select
              id="o-stay"
              value={stayId ? String(stayId) : ""}
              placeholder={orderType === "room" ? t.common.required : t.services.orders.walkIn}
              options={stayOptions}
              onChange={(e) => setStayId(e.target.value ? Number(e.target.value) : null)}
            />
          </FormField>
          {orderType === "table" ? (
            <FormField label={t.services.orders.customerName} htmlFor="o-customer">
              <Input
                id="o-customer"
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
              />
            </FormField>
          ) : null}
          <FormField label={t.services.orders.requestedTime} htmlFor="o-time">
            <Input
              id="o-time"
              type="time"
              value={requestedTime}
              onChange={(e) => setRequestedTime(e.target.value)}
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
          <Textarea id="o-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
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
  initialAction = null,
  onClose,
  onChanged,
}: {
  order: ServiceOrder | null;
  /** When the modal is opened from a card "More" item, pre-open this sub-flow. */
  initialAction?: OrderIntent | null;
  onClose: () => void;
  onChanged: (order: ServiceOrder) => void;
}) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const [busy, setBusy] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [postConfirm, setPostConfirm] = useState(false);
  const [itemCancel, setItemCancel] = useState<ServiceOrderItem | null>(null);
  const [itemCancelReason, setItemCancelReason] = useState("");
  const [settleOpen, setSettleOpen] = useState(false);
  const [settleMethod, setSettleMethod] = useState<PaymentMethod>("cash");
  const [ticket, setTicket] = useState<ServiceTicket | null>(null);
  const [receipt, setReceipt] = useState<{ hotel: HotelHeader; payment: Payment } | null>(null);

  // Reset every sub-dialog whenever a DIFFERENT order is opened, then honour the
  // requested open-intent once. Keyed on order id (a same-id refetch via
  // onChanged never re-fires the intent). All sub-flows below already exist —
  // the intent only drives which one auto-opens, so nothing is duplicated.
  useEffect(() => {
    setCancelOpen(false);
    setCancelReason("");
    setPostConfirm(false);
    setItemCancel(null);
    setItemCancelReason("");
    setSettleOpen(false);
    setSettleMethod("cash");
    setTicket(null);
    setReceipt(null);
    if (!order || !initialAction) return;
    switch (initialAction) {
      case "post":
        setPostConfirm(true);
        break;
      case "settle":
        setSettleOpen(true);
        break;
      case "cancel":
        setCancelOpen(true);
        break;
      case "kot":
        void openTicket("kot");
        break;
      case "guest_check":
        void openTicket("guest_check");
        break;
      case "receipt":
        void openReceipt();
        break;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire the open-intent once per opened order
  }, [order?.id, initialAction]);

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

  async function openTicket(variant: "kot" | "guest_check") {
    try {
      setTicket(await getServiceOrderTicket(order!.id, variant));
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  async function openReceipt() {
    if (!order?.settlement_payment) return;
    try {
      const r = await getReceipt(order.settlement_payment);
      setReceipt({ hotel: r.hotel, payment: r.payment });
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  const canCancelItems =
    order.settlement === "unsettled" &&
    order.status !== "cancelled" &&
    can("service_orders.update");

  const itemColumns: Column<ServiceOrder["items"][number]>[] = [
    {
      key: "item_name",
      header: t.services.orders.item,
      render: (r) =>
        r.is_cancelled ? (
          <span className="cluster">
            <s className="muted">{r.item_name}</s>
            <Badge tone="danger">{t.services.orders.itemCancelled}</Badge>
            {r.cancel_reason ? <span className="muted small">{r.cancel_reason}</span> : null}
          </span>
        ) : (
          r.item_name
        ),
    },
    { key: "quantity", header: t.services.orders.quantity },
    { key: "unit_price", header: t.services.catalog.price },
    { key: "tax_amount", header: t.services.orders.tax },
    { key: "total_amount", header: t.services.orders.total },
    ...(canCancelItems
      ? [
          {
            key: "actions",
            header: t.common.actions,
            align: "end",
            render: (r) =>
              r.is_cancelled ? null : (
                <IconButton
                  icon={XCircle}
                  label={t.services.orders.cancelItem}
                  onClick={() => {
                    setItemCancelReason("");
                    setItemCancel(r);
                  }}
                />
              ),
          } satisfies Column<ServiceOrder["items"][number]>,
        ]
      : []),
  ];

  const canAdvance = ["submitted", "preparing", "ready"].includes(order.status);
  const canCancel = order.settlement === "unsettled" && order.status !== "cancelled";
  const canPost =
    order.status === "delivered" &&
    order.settlement === "unsettled" &&
    !order.is_posted &&
    order.stay !== null;
  const canSettleDirect =
    order.status === "delivered" &&
    order.settlement === "unsettled" &&
    can("service_orders.settle_direct");

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title={`${t.services.orders.details} · ${order.order_number}`}
        closeLabel={t.common.close}
        footer={
          <>
            <Button variant="secondary" icon={Printer} onClick={() => openTicket("kot")} disabled={busy}>
              {t.services.ticket.title}
            </Button>
            <Button variant="secondary" icon={Printer} onClick={() => openTicket("guest_check")} disabled={busy}>
              {t.services.ticket.guestCheckTitle}
            </Button>
            {order.settlement === "direct" && order.settlement_payment ? (
              <Button variant="secondary" icon={ReceiptText} onClick={openReceipt} disabled={busy}>
                {t.services.orders.printReceipt}
              </Button>
            ) : null}
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
            {canSettleDirect ? (
              <Button icon={HandCoins} onClick={() => setSettleOpen(true)} loading={busy}>
                {t.services.orders.directPayment}
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
            <Badge tone="neutral">{t.services.outlets[order.outlet]}</Badge>
            <Badge tone="neutral">{t.services.orderTypes[order.order_type]}</Badge>
            <Badge tone={settlementTone(order.settlement)}>{t.services.settlement[order.settlement]}</Badge>
            {order.is_posted ? <Badge tone="success">{t.services.orders.postedYes}</Badge> : null}
          </div>
          <StatusSummaryCard
            items={[
              ...(order.order_type === "room"
                ? [{ label: t.services.orders.room, value: order.room_number || "—" }]
                : [{ label: t.services.orders.table, value: order.table_number || "—" }]),
              ...(order.customer_name
                ? [{ label: t.services.orders.customerName, value: order.customer_name }]
                : []),
              { label: t.services.orders.guest, value: order.guest_name || "—" },
              { label: t.services.orders.businessDate, value: formatDate(order.business_date, locale) },
              { label: t.services.orders.orderedAt, value: formatDateTime(order.ordered_at, locale) },
              ...(order.settlement === "direct" && order.settlement_receipt
                ? [{ label: t.services.orders.settlementReceipt, value: order.settlement_receipt }]
                : []),
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

      <Modal
        open={itemCancel !== null}
        onClose={() => setItemCancel(null)}
        title={t.services.orders.cancelItemTitle}
        closeLabel={t.common.close}
        footer={
          <>
            <Button variant="secondary" onClick={() => setItemCancel(null)} disabled={busy}>{t.common.cancel}</Button>
            <Button
              variant="danger"
              loading={busy}
              onClick={async () => {
                if (!itemCancel || !itemCancelReason.trim()) return;
                await run(() =>
                  cancelServiceOrderItem(order.id, itemCancel.id, itemCancelReason.trim()),
                );
                setItemCancel(null);
              }}
            >
              {t.services.orders.cancelConfirm}
            </Button>
          </>
        }
      >
        <div className="stack">
          {itemCancel ? <p>{itemCancel.item_name}</p> : null}
          <FormField label={t.services.orders.cancelReason} htmlFor="o-item-cancel-reason">
            <Textarea id="o-item-cancel-reason" value={itemCancelReason} onChange={(e) => setItemCancelReason(e.target.value)} />
          </FormField>
        </div>
      </Modal>

      <Modal
        open={settleOpen}
        onClose={() => setSettleOpen(false)}
        title={t.services.orders.directPayment}
        closeLabel={t.common.close}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSettleOpen(false)} disabled={busy}>{t.common.cancel}</Button>
            <Button
              loading={busy}
              onClick={async () => {
                await run(() => settleServiceOrderDirect(order.id, settleMethod));
                setSettleOpen(false);
              }}
            >
              {t.services.orders.directPaymentConfirmAction}
            </Button>
          </>
        }
      >
        <div className="stack">
          <Alert tone="warning">{t.services.orders.directPaymentConfirm}</Alert>
          <FormField label={t.services.orders.paymentMethod} htmlFor="o-settle-method">
            <Select
              id="o-settle-method"
              value={settleMethod}
              options={PAYMENT_METHODS.map((m) => ({ value: m, label: t.finance.methods[m] }))}
              onChange={(e) => setSettleMethod(e.target.value as PaymentMethod)}
            />
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

      <PrintModal
        open={ticket !== null}
        title={ticket?.document === "guest_check" ? t.services.ticket.guestCheckTitle : t.services.ticket.title}
        onClose={() => setTicket(null)}
      >
        {ticket ? (
          <PrintDocumentLayout
            hotelName={ticket.hotel.hotel_name}
            hotelAddress={ticket.hotel.address}
            hotelPhone={ticket.hotel.phone}
            docTitle={
              ticket.document === "guest_check"
                ? t.services.ticket.guestCheckTitle
                : t.services.ticket.title
            }
            docNumber={ticket.order.order_number}
            meta={[
              { label: t.services.outlet, value: t.services.outlets[ticket.order.outlet] },
              ...(ticket.order.order_type === "room"
                ? [{ label: t.services.ticket.roomLabel, value: ticket.order.room_number || "—" }]
                : [{ label: t.services.ticket.tableLabel, value: ticket.order.table_number || "—" }]),
              ...(ticket.order.customer_name
                ? [{ label: t.services.ticket.customerLabel, value: ticket.order.customer_name }]
                : []),
              { label: t.services.ticket.guestLabel, value: ticket.order.guest_name || "—" },
              { label: t.services.ticket.timeLabel, value: formatDateTime(ticket.order.ordered_at, locale) },
              ...(ticket.order.requested_delivery_time
                ? [{ label: t.services.orders.requestedTime, value: ticket.order.requested_delivery_time }]
                : []),
            ]}
            totals={
              ticket.document === "guest_check" && ticket.totals
                ? [
                    { label: t.services.orders.subtotal, value: ticket.totals.subtotal },
                    { label: t.services.orders.tax, value: ticket.totals.tax_total },
                    { label: t.services.orders.total, value: <strong>{ticket.totals.total}</strong> },
                  ]
                : undefined
            }
            notes={ticket.order.notes || undefined}
            notesLabel={t.services.orders.notes}
          >
            <table className="print-table">
              <thead>
                <tr>
                  <th>{t.services.orders.item}</th>
                  <th>{t.services.ticket.qty}</th>
                  {ticket.document === "guest_check" ? (
                    <>
                      <th>{t.services.ticket.price}</th>
                      <th>{t.services.ticket.lineTotal}</th>
                    </>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {ticket.items.map((i, idx) => (
                  <tr key={idx}>
                    <td>{i.item_name}</td>
                    <td>{i.quantity}</td>
                    {ticket.document === "guest_check" ? (
                      <>
                        <td>{i.unit_price ?? "—"}</td>
                        <td>{i.total_amount ?? "—"}</td>
                      </>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </PrintDocumentLayout>
        ) : null}
      </PrintModal>

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
              {
                label: t.finance.print.amount,
                value: (
                  <strong>
                    {formatMoney(receipt.payment.amount, receipt.payment.currency, locale)}
                  </strong>
                ),
              },
              { label: t.finance.print.folio, value: receipt.payment.folio_number },
              ...(receipt.payment.reference
                ? [{ label: t.finance.print.reference, value: receipt.payment.reference }]
                : []),
              ...(receipt.payment.created_by
                ? [{ label: t.finance.print.receivedBy, value: receipt.payment.created_by }]
                : []),
            ]}
            notes={receipt.payment.notes || undefined}
          />
        ) : null}
      </PrintModal>
    </>
  );
}
