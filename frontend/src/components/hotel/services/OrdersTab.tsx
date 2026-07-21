"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { useQuickAction } from "@/lib/useQuickAction";
import {
  Armchair,
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
  Undo2,
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
  Switch,
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
  mintIdempotencyKey,
  postServiceOrderToFolio,
  returnServiceOrder,
  setServiceOrderStatus,
  settleServiceOrderDirect,
  type ServiceOrderLineInput,
  type ServiceReturnItemInput,
} from "@/lib/api/services";
import { getReceipt } from "@/lib/api/finance";
import { getSettings } from "@/lib/api/hotel";
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
  ServiceReturnKind,
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
type OrderIntent =
  | "post"
  | "settle"
  | "cancel"
  | "kot"
  | "guest_check"
  | "receipt"
  | "return";

/** The list is shown as cards; the prep board is folded in as a view MODE. */
type OrdersView = "list" | "board";

/** VISIBLE cycle collapse (RESTAURANT-CAFETERIA-OPERATIONAL-CLOSURE): the surface
 * has exactly two operational states — OPEN (draft/submitted/preparing/ready, all
 * treated as "new") and terminal (delivered/cancelled). An open order's primary
 * action is "Mark delivered" (the backend accepts submitted→delivered directly);
 * preparing/ready are never surfaced as actions. */
function isOpenStatus(status: ServiceOrderStatus): boolean {
  return status !== "delivered" && status !== "cancelled";
}

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
/** Methods that take an electronic reference (shown on the settle/return forms). */
const ELECTRONIC_METHODS: PaymentMethod[] = ["card", "bank_transfer", "electronic"];

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

  // The collapsed cycle's single advance: any open order jumps straight to
  // delivered (the backend accepts submitted→delivered without the intermediate
  // preparing/ready hops, which the surface no longer shows).
  async function deliverOrder(r: ServiceOrderListItem) {
    setAdvancingId(r.id);
    try {
      await setServiceOrderStatus(r.id, "delivered");
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
        // Currency now travels on the list row — show it with the amount (a null
        // total means no active lines yet, rendered as an em dash).
        value: (
          <bdi dir="ltr">
            {r.total !== null ? formatMoney(r.total, r.currency, locale) : "—"}
          </bdi>
        ),
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

    // ONE state-driven primary (collapsed cycle): an OPEN order delivers; a
    // terminal order (delivered/cancelled) opens Details.
    let primary: OperationPrimaryAction;
    if (isOpenStatus(r.status)) {
      primary = {
        label: t.services.orders.markDelivered,
        icon: PackageCheck,
        loading: advancingId === r.id,
        onClick: () => deliverOrder(r),
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
    // Return / exchange: only AFTER delivery on a SETTLED order (direct or folio),
    // gated on the existing finance.refund permission (a return moves money back
    // to — or collects a delta from — the customer).
    if (
      r.status === "delivered" &&
      (r.settlement === "direct" || r.settlement === "folio") &&
      can("finance.refund")
    ) {
      menu.push({
        key: "return",
        label: t.services.orders.returnExchange,
        icon: Undo2,
        onSelect: () => openDetailWith(r.id, "return"),
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
  const [residentQuery, setResidentQuery] = useState("");
  const [tables, setTables] = useState<RestaurantTable[]>([]);
  const [catalog, setCatalog] = useState<ServiceItem[]>([]);
  const [lines, setLines] = useState<ServiceOrderLineInput[]>([]);
  // The hotel BASE currency (D1a) — the order's single currency once created; used
  // here only to label the client-side estimated total (server stays authoritative).
  const [baseCurrency, setBaseCurrency] = useState("");
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
    setResidentQuery("");
    setError(null);
    // Only IN-HOUSE residents are returned here, so ended/checked-out stays are
    // already excluded (a room order needs a checked-in guest).
    listCurrentResidents()
      .then((r) => setStays(r.results))
      .catch(() => setStays([]));
    getSettings()
      .then((s) => setBaseCurrency((s.default_currency || "").toUpperCase()))
      .catch(() => setBaseCurrency(""));
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
  // Resident search — by room number OR guest name (case-insensitive). NOTE: the
  // current-residents payload carries no phone, so phone search is unavailable
  // here (surfaced as a field note); ended/checked-out stays are already excluded.
  const q = residentQuery.trim().toLowerCase();
  const filteredStays = q
    ? stays.filter(
        (s) =>
          String(s.room_number ?? s.room).toLowerCase().includes(q) ||
          (s.primary_guest_name ?? "").toLowerCase().includes(q),
      )
    : stays;
  const stayOptions = filteredStays.map((s) => ({
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

  // LIVE estimated total (preview only — the server re-derives the authoritative
  // total from the frozen line snapshots). Computed from the selected catalog
  // items' unit_price × qty and tax_rate, in the hotel base currency.
  const estimate = lines.reduce(
    (acc, line) => {
      const item = catalog.find((i) => i.id === line.service_item);
      if (!item) return acc;
      const qty = Number(line.quantity);
      const unit = Number(item.unit_price);
      const rate = Number(item.tax_rate);
      if (!Number.isFinite(qty) || qty <= 0 || !Number.isFinite(unit)) return acc;
      const amount = unit * qty;
      const tax = Number.isFinite(rate) ? (amount * rate) / 100 : 0;
      acc.subtotal += amount;
      acc.tax += tax;
      acc.total += amount + tax;
      return acc;
    },
    { subtotal: 0, tax: 0, total: 0 },
  );
  // Prefer the base currency; fall back to a selected item's own currency snapshot.
  const estimateCurrency =
    baseCurrency ||
    catalog.find((i) => lines.some((l) => l.service_item === i.id) && i.currency)?.currency ||
    "";

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
          <FormField
            label={t.common.search}
            htmlFor="o-resident-search"
            hint={t.services.orders.residentSearchNote}
          >
            <Input
              id="o-resident-search"
              value={residentQuery}
              placeholder={t.services.orders.residentSearchPlaceholder}
              onChange={(e) => setResidentQuery(e.target.value)}
            />
          </FormField>
          <FormField label={t.services.orders.stay} htmlFor="o-stay">
            {/* A table order may link a resident stay (room-linked path) so it can
                later post to that guest's folio; leaving it blank is a walk-in. */}
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
          {lines.length > 0 ? (
            <div className="stack" style={{ gap: "0.25rem" }} aria-live="polite">
              <span className="field__label">{t.services.orders.estimatedTotal}</span>
              <StatusSummaryCard
                items={[
                  {
                    label: t.services.orders.subtotal,
                    value: formatMoney(estimate.subtotal, estimateCurrency, locale),
                  },
                  {
                    label: t.services.orders.tax,
                    value: formatMoney(estimate.tax, estimateCurrency, locale),
                  },
                  {
                    label: t.services.orders.estimatedTotal,
                    value: formatMoney(estimate.total, estimateCurrency, locale),
                    emphasis: true,
                  },
                ]}
              />
              <span className="muted small">{t.services.orders.estimatedTotalHint}</span>
            </div>
          ) : (
            <p className="muted small">{t.services.orders.totalAfterSave}</p>
          )}
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
  const [returnOpen, setReturnOpen] = useState(false);
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
    setReturnOpen(false);
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
      case "return":
        setReturnOpen(true);
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
    {
      key: "unit_price",
      header: t.services.catalog.price,
      render: (r) => <bdi dir="ltr">{formatMoney(r.unit_price, r.currency, locale)}</bdi>,
    },
    {
      key: "tax_amount",
      header: t.services.orders.tax,
      render: (r) => <bdi dir="ltr">{formatMoney(r.tax_amount, r.currency, locale)}</bdi>,
    },
    {
      key: "total_amount",
      header: t.services.orders.total,
      render: (r) => <bdi dir="ltr">{formatMoney(r.total_amount, r.currency, locale)}</bdi>,
    },
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

  const canAdvance = isOpenStatus(order.status);
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
  // Return / exchange: a delivered, SETTLED order (direct or folio), gated on the
  // existing finance.refund permission (money moves back to the customer).
  const canReturn =
    order.status === "delivered" &&
    (order.settlement === "direct" || order.settlement === "folio") &&
    can("finance.refund");

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
            {canReturn ? (
              <Button variant="secondary" icon={Undo2} onClick={() => setReturnOpen(true)} disabled={busy}>
                {t.services.orders.returnExchange}
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
              ...(order.settlement === "direct" && order.amount_received
                ? [{ label: t.services.orders.amountReceived, value: formatMoney(order.amount_received, order.currency, locale) }]
                : []),
              ...(order.settlement === "direct" && order.change_given
                ? [{ label: t.services.orders.change, value: formatMoney(order.change_given, order.currency, locale) }]
                : []),
              ...(order.settlement === "direct" && order.settlement_reference
                ? [{ label: t.services.orders.reference, value: order.settlement_reference }]
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
              { label: t.services.orders.subtotal, value: formatMoney(order.totals.subtotal, order.totals.currency, locale) },
              { label: t.services.orders.tax, value: formatMoney(order.totals.tax_total, order.totals.currency, locale) },
              { label: t.services.orders.total, value: formatMoney(order.totals.total, order.totals.currency, locale), emphasis: true },
            ]}
          />
          {order.returns.length > 0 ? (
            <StatusSummaryCard
              title={t.services.returns.history}
              items={order.returns.map((ret) => ({
                label: `${t.services.returns.returnNumber} ${ret.return_number} · ${t.services.returns.kinds[ret.kind]}`,
                value: ret.reason || "—",
              }))}
            />
          ) : null}
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

      <DirectPaymentModal
        order={order}
        open={settleOpen}
        onClose={() => setSettleOpen(false)}
        onSettled={(updated) => {
          setSettleOpen(false);
          onChanged(updated);
        }}
      />

      <ReturnExchangeModal
        order={order}
        open={returnOpen}
        onClose={() => setReturnOpen(false)}
        onDone={(updated) => {
          setReturnOpen(false);
          onChanged(updated);
        }}
      />

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
                    { label: t.services.orders.subtotal, value: formatMoney(ticket.totals.subtotal, ticket.order.currency, locale) },
                    { label: t.services.orders.tax, value: formatMoney(ticket.totals.tax_total, ticket.order.currency, locale) },
                    { label: t.services.orders.total, value: <strong>{formatMoney(ticket.totals.total, ticket.order.currency, locale)}</strong> },
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
                        <td>{i.unit_price != null ? formatMoney(i.unit_price, ticket.order.currency, locale) : "—"}</td>
                        <td>{i.total_amount != null ? formatMoney(i.total_amount, ticket.order.currency, locale) : "—"}</td>
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
              // Cash-capture capture (D2a) lives on the ORDER, not the payment
              // (which always records the exact total) — surface it on the receipt.
              ...(order.amount_received
                ? [{ label: t.services.orders.amountReceived, value: formatMoney(order.amount_received, order.currency, locale) }]
                : []),
              ...(order.change_given
                ? [{ label: t.services.orders.change, value: formatMoney(order.change_given, order.currency, locale) }]
                : []),
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

/* ------------------------------------------------------------------------- */
/* Direct payment (D2a — cash capture, live change, idempotent)                */
/* ------------------------------------------------------------------------- */

function DirectPaymentModal({
  order,
  open,
  onClose,
  onSettled,
}: {
  order: ServiceOrder;
  open: boolean;
  onClose: () => void;
  onSettled: (order: ServiceOrder) => void;
}) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [method, setMethod] = useState<PaymentMethod>("cash");
  const [amountReceived, setAmountReceived] = useState("");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ONE idempotency key per settle attempt: minted when the modal opens, REUSED
  // across retries, regenerated only AFTER success — never inside submit(). A
  // stable key makes a network-failure retry safe (replay returns the original
  // settlement or fails closed on a 409), never a second payment.
  const keyRef = useRef("");

  useEffect(() => {
    if (!open) return;
    setMethod("cash");
    setAmountReceived("");
    setReference("");
    setError(null);
    keyRef.current = mintIdempotencyKey();
  }, [open]);

  const currency = order.totals.currency || order.currency;
  const total = Number(order.totals.total);
  const isCash = method === "cash";
  const isElectronic = ELECTRONIC_METHODS.includes(method);
  const receivedNum = Number(amountReceived);
  const hasReceived = amountReceived.trim() !== "" && Number.isFinite(receivedNum);
  const shortCash = isCash && hasReceived && receivedNum < total;
  const change = isCash && hasReceived && receivedNum >= total ? receivedNum - total : null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || shortCash) return;
    if (!keyRef.current) keyRef.current = mintIdempotencyKey();
    setBusy(true);
    setError(null);
    try {
      const updated = await settleServiceOrderDirect(order.id, {
        method,
        settlement_key: keyRef.current,
        // Cash tender only when entered (the backend rejects a short tender and
        // computes change); electronic reference only for electronic methods.
        ...(isCash && hasReceived ? { amount_received: amountReceived } : {}),
        ...(isElectronic && reference.trim() ? { reference: reference.trim() } : {}),
      });
      // Settled — the next attempt is a genuinely new request.
      keyRef.current = mintIdempotencyKey();
      if (updated.change_given && Number(updated.change_given) > 0) {
        notify(
          t.services.orders.paidWithChange.replace(
            "{amount}",
            formatMoney(updated.change_given, updated.currency, locale),
          ),
        );
      } else {
        notify(t.services.saved);
      }
      onSettled(updated);
    } catch (err) {
      // Leave the key untouched so the next click REPLAYS (never a 2nd payment).
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.services.orders.directPayment}
      closeLabel={t.common.close}
      preventClose={busy}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="svc-settle-form" type="submit" loading={busy} disabled={busy || shortCash}>
            {t.services.orders.directPaymentConfirmAction}
          </Button>
        </>
      }
    >
      <form id="svc-settle-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="warning">{t.services.orders.directPaymentConfirm}</Alert>
        <StatusSummaryCard
          items={[
            {
              label: t.services.orders.total,
              value: formatMoney(order.totals.total, currency, locale),
              emphasis: true,
            },
          ]}
        />
        <FormField label={t.services.orders.paymentMethod} htmlFor="o-settle-method">
          <Select
            id="o-settle-method"
            value={method}
            options={PAYMENT_METHODS.map((m) => ({ value: m, label: t.finance.methods[m] }))}
            onChange={(e) => setMethod(e.target.value as PaymentMethod)}
          />
        </FormField>
        {isCash ? (
          <div className="form-grid">
            <FormField
              label={t.services.orders.amountReceived}
              htmlFor="o-settle-received"
              hint={t.services.orders.amountReceivedHint}
              error={shortCash ? t.services.orders.shortCash : undefined}
            >
              <Input
                id="o-settle-received"
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={amountReceived}
                invalid={shortCash}
                onChange={(e) => setAmountReceived(e.target.value)}
              />
            </FormField>
            <FormField label={t.services.orders.change} htmlFor="o-settle-change">
              <div className="cluster" id="o-settle-change" aria-live="polite">
                {change !== null ? (
                  <strong>
                    <bdi dir="ltr">{formatMoney(change, currency, locale)}</bdi>
                  </strong>
                ) : (
                  <span className="muted">—</span>
                )}
              </div>
            </FormField>
          </div>
        ) : null}
        {isElectronic ? (
          <FormField label={t.services.orders.reference} htmlFor="o-settle-ref">
            <Input
              id="o-settle-ref"
              value={reference}
              placeholder={t.services.orders.referencePlaceholder}
              onChange={(e) => setReference(e.target.value)}
            />
          </FormField>
        ) : null}
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------------- */
/* Return / exchange (after delivery only; gated finance.refund)               */
/* ------------------------------------------------------------------------- */

type ReturnAction = "return" | "exchange";

function ReturnExchangeModal({
  order,
  open,
  onClose,
  onDone,
}: {
  order: ServiceOrder;
  open: boolean;
  onClose: () => void;
  onDone: (order: ServiceOrder) => void;
}) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [action, setAction] = useState<ReturnAction>("return");
  // Selected returned lines: lineId -> quantity string (presence = selected).
  const [sel, setSel] = useState<Record<number, string>>({});
  const [replacementId, setReplacementId] = useState<number | null>(null);
  const [replacementQty, setReplacementQty] = useState("1");
  const [reason, setReason] = useState("");
  const [method, setMethod] = useState<PaymentMethod>("cash");
  const [amountReceived, setAmountReceived] = useState("");
  const [reference, setReference] = useState("");
  const [catalog, setCatalog] = useState<ServiceItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Same idempotency lifecycle as the settle modal (mint on open, reuse on retry,
  // regenerate after success — never inside submit()).
  const keyRef = useRef("");

  useEffect(() => {
    if (!open) return;
    setAction("return");
    setSel({});
    setReplacementId(null);
    setReplacementQty("1");
    setReason("");
    setMethod("cash");
    setAmountReceived("");
    setReference("");
    setError(null);
    keyRef.current = mintIdempotencyKey();
    // Replacement items must belong to the order's outlet (the backend enforces it).
    listServiceItems({ outlet: order.outlet, is_active: "true", is_available: "true", page: 1 })
      .then((r) => setCatalog(r.results))
      .catch(() => setCatalog([]));
  }, [open, order.id, order.outlet]);

  const currency = order.totals.currency || order.currency;
  const isDirect = order.settlement === "direct";
  const isExchange = action === "exchange";

  // Remaining returnable quantity per line = ordered qty − already-returned qty.
  function returnedQty(lineId: number): number {
    let sum = 0;
    for (const ret of order.returns) {
      for (const it of ret.items) {
        if (it.original_item === lineId) sum += Number(it.quantity);
      }
    }
    return sum;
  }
  const returnable = order.items
    .filter((i) => !i.is_cancelled)
    .map((i) => ({ line: i, remaining: Number(i.quantity) - returnedQty(i.id) }))
    .filter((r) => r.remaining > 0.00001);

  function toggleLine(lineId: number, remaining: number) {
    setSel((prev) => {
      const next = { ...prev };
      if (lineId in next) delete next[lineId];
      else next[lineId] = String(remaining);
      return next;
    });
  }

  const selectedIds = Object.keys(sel).map(Number);

  // Return total from the selected line snapshots (preview — server authoritative).
  let returnTotal = 0;
  for (const r of returnable) {
    if (!(r.line.id in sel)) continue;
    const q = Number(sel[r.line.id]);
    if (!Number.isFinite(q) || q <= 0) continue;
    const amt = q * Number(r.line.unit_price);
    returnTotal += amt + (amt * Number(r.line.tax_rate)) / 100;
  }

  const replacement = catalog.find((i) => i.id === replacementId) ?? null;
  const repQtyNum = Number(replacementQty);
  let replacementTotal = 0;
  if (isExchange && replacement && Number.isFinite(repQtyNum) && repQtyNum > 0) {
    const amt = repQtyNum * Number(replacement.unit_price);
    replacementTotal = amt + (amt * Number(replacement.tax_rate)) / 100;
  }
  const delta = replacementTotal - returnTotal;

  // The SERVER computes and verifies the kind; the client derives the same value
  // from the numbers so the preview and the request agree.
  let kind: ServiceReturnKind = "return";
  if (isExchange) {
    kind = delta === 0 ? "exchange_same" : delta > 0 ? "exchange_higher" : "exchange_lower";
  }
  // "out" = money back to the customer (cash refund on a direct sale, or a credit
  // on the guest folio); "in" = collect an upgrade delta; "none" = equal exchange.
  const direction: "out" | "in" | "none" =
    kind === "exchange_same" ? "none" : kind === "exchange_higher" ? "in" : "out";
  const moveAmount = kind === "return" ? returnTotal : Math.abs(delta);

  let moneyMove: string;
  if (direction === "none") moneyMove = t.services.returns.noChange;
  else if (direction === "in")
    moneyMove = t.services.returns.collect.replace("{amount}", formatMoney(moveAmount, currency, locale));
  else if (isDirect)
    moneyMove = t.services.returns.refund.replace("{amount}", formatMoney(moveAmount, currency, locale));
  else moneyMove = t.services.returns.credit.replace("{amount}", formatMoney(moveAmount, currency, locale));

  // Payment fields only for a DIRECT order that actually moves money; a FOLIO
  // order's money runs on the guest folio (no method/tender collected here).
  const showPayment = isDirect && direction !== "none";
  const isCash = method === "cash";
  const isElectronic = ELECTRONIC_METHODS.includes(method);
  const receivedNum = Number(amountReceived);
  const hasReceived = amountReceived.trim() !== "" && Number.isFinite(receivedNum);
  // Only the COLLECT (upgrade) path tenders cash; refunds do not.
  const collectCash = showPayment && direction === "in" && isCash;
  const shortCash = collectCash && hasReceived && receivedNum < moveAmount;
  const change =
    collectCash && hasReceived && receivedNum >= moveAmount ? receivedNum - moveAmount : null;

  const exchangeOneLine = isExchange && selectedIds.length !== 1;
  const needsReplacement = isExchange && !replacement;
  const canSubmit =
    selectedIds.length > 0 &&
    returnTotal > 0 &&
    reason.trim() !== "" &&
    !exchangeOneLine &&
    !needsReplacement &&
    !shortCash;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !canSubmit) return;
    if (!keyRef.current) keyRef.current = mintIdempotencyKey();
    const items: ServiceReturnItemInput[] = returnable
      .filter((r) => r.line.id in sel)
      .map((r) => ({
        original_item: r.line.id,
        quantity: sel[r.line.id],
        ...(isExchange && replacement
          ? { replacement_item: replacement.id, replacement_quantity: replacementQty }
          : {}),
      }));
    setBusy(true);
    setError(null);
    try {
      const result = await returnServiceOrder(order.id, {
        kind,
        reason: reason.trim(),
        items,
        idempotency_key: keyRef.current,
        ...(showPayment ? { method } : {}),
        ...(collectCash && hasReceived ? { amount_received: amountReceived } : {}),
        ...(showPayment && isElectronic && reference.trim() ? { reference: reference.trim() } : {}),
      });
      keyRef.current = mintIdempotencyKey();
      notify(t.services.saved);
      onDone(result.order);
    } catch (err) {
      // Leave the key untouched so the next click REPLAYS the same request.
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.services.returns.title}
      closeLabel={t.common.close}
      preventClose={busy}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="svc-return-form" type="submit" loading={busy} disabled={busy || !canSubmit}>
            {t.services.returns.submit}
          </Button>
        </>
      }
    >
      <form id="svc-return-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <p className="muted small">{t.services.returns.intro}</p>

        <FormField label={t.services.returns.kindLabel} htmlFor="r-action">
          <Select
            id="r-action"
            value={action}
            options={[
              { value: "return", label: t.services.returns.actionReturn },
              { value: "exchange", label: t.services.returns.actionExchange },
            ]}
            onChange={(e) => setAction(e.target.value as ReturnAction)}
          />
        </FormField>

        <div className="stack">
          <span className="field__label">{t.services.returns.selectItems}</span>
          {returnable.length === 0 ? (
            <p className="muted">{t.services.returns.noItems}</p>
          ) : (
            returnable.map((r) => {
              const selected = r.line.id in sel;
              return (
                <div className="form-grid" key={r.line.id}>
                  <Switch
                    id={`r-sel-${r.line.id}`}
                    checked={selected}
                    onChange={() => toggleLine(r.line.id, r.remaining)}
                    label={`${r.line.item_name} · ${formatMoney(r.line.unit_price, r.line.currency || currency, locale)}`}
                  />
                  {selected ? (
                    <FormField
                      label={t.services.returns.quantity}
                      htmlFor={`r-qty-${r.line.id}`}
                      hint={t.services.returns.remaining.replace("{qty}", String(r.remaining))}
                    >
                      <Input
                        id={`r-qty-${r.line.id}`}
                        type="number"
                        min="0.01"
                        step="0.01"
                        max={String(r.remaining)}
                        inputMode="decimal"
                        value={sel[r.line.id]}
                        onChange={(e) => setSel((prev) => ({ ...prev, [r.line.id]: e.target.value }))}
                      />
                    </FormField>
                  ) : null}
                </div>
              );
            })
          )}
        </div>

        {isExchange ? (
          <div className="form-grid">
            <FormField
              label={t.services.returns.replacement}
              htmlFor="r-replacement"
              error={exchangeOneLine ? t.services.returns.exchangeOneLine : undefined}
            >
              <Select
                id="r-replacement"
                value={replacementId ? String(replacementId) : ""}
                placeholder={t.common.required}
                options={catalog.map((i) => ({
                  value: String(i.id),
                  label: `${i.name} (${formatMoney(i.unit_price, i.currency || currency, locale)})`,
                }))}
                onChange={(e) => setReplacementId(e.target.value ? Number(e.target.value) : null)}
              />
            </FormField>
            <FormField label={t.services.returns.replacementQty} htmlFor="r-rep-qty">
              <Input
                id="r-rep-qty"
                type="number"
                min="0.01"
                step="0.01"
                inputMode="decimal"
                value={replacementQty}
                onChange={(e) => setReplacementQty(e.target.value)}
              />
            </FormField>
          </div>
        ) : null}

        <FormField label={t.services.returns.reason} htmlFor="r-reason">
          <Textarea
            id="r-reason"
            value={reason}
            placeholder={t.services.returns.reasonPlaceholder}
            onChange={(e) => setReason(e.target.value)}
          />
        </FormField>

        {returnTotal > 0 ? (
          <StatusSummaryCard
            title={t.services.returns.moneyMove}
            items={[{ label: t.services.returns.moneyMove, value: moneyMove, emphasis: true }]}
          />
        ) : null}

        {showPayment ? (
          <div className="stack">
            <span className="field__label">{t.services.returns.paymentSection}</span>
            <FormField label={t.services.orders.paymentMethod} htmlFor="r-method">
              <Select
                id="r-method"
                value={method}
                options={PAYMENT_METHODS.map((m) => ({ value: m, label: t.finance.methods[m] }))}
                onChange={(e) => setMethod(e.target.value as PaymentMethod)}
              />
            </FormField>
            {collectCash ? (
              <div className="form-grid">
                <FormField
                  label={t.services.orders.amountReceived}
                  htmlFor="r-received"
                  hint={t.services.orders.amountReceivedHint}
                  error={shortCash ? t.services.orders.shortCash : undefined}
                >
                  <Input
                    id="r-received"
                    type="number"
                    min="0"
                    step="0.01"
                    inputMode="decimal"
                    value={amountReceived}
                    invalid={shortCash}
                    onChange={(e) => setAmountReceived(e.target.value)}
                  />
                </FormField>
                <FormField label={t.services.orders.change} htmlFor="r-change">
                  <div className="cluster" id="r-change" aria-live="polite">
                    {change !== null ? (
                      <strong>
                        <bdi dir="ltr">{formatMoney(change, currency, locale)}</bdi>
                      </strong>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </div>
                </FormField>
              </div>
            ) : null}
            {isElectronic ? (
              <FormField label={t.services.orders.reference} htmlFor="r-ref">
                <Input
                  id="r-ref"
                  value={reference}
                  placeholder={t.services.orders.referencePlaceholder}
                  onChange={(e) => setReference(e.target.value)}
                />
              </FormField>
            ) : null}
          </div>
        ) : null}
      </form>
    </Modal>
  );
}
