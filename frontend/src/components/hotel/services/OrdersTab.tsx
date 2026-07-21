"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

import { useQuickAction } from "@/lib/useQuickAction";
import {
  Armchair,
  Banknote,
  BedDouble,
  CheckCircle2,
  ClipboardList,
  Clock,
  Coffee,
  Coins,
  CreditCard,
  DoorOpen,
  Eye,
  FileInput,
  HandCoins,
  Minus,
  PackageCheck,
  Plus,
  Printer,
  ReceiptText,
  Trash2,
  Undo2,
  Utensils,
  UserRound,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  Icon,
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
  type BadgeTone,
  type Column,
} from "@/components/ui";
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
  ServiceOrderType,
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
  stayStatusLabel,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { PrintModal } from "../finance/shared";
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

/** Orders are shown in ONE view only — cards (owner correction: the prep-board
 * view and the list/board toggle were removed). */

/** VISIBLE cycle collapse (RESTAURANT-CAFETERIA-OPERATIONAL-CLOSURE): the surface
 * has exactly two operational states — OPEN (draft/submitted/preparing/ready, all
 * treated as "new") and terminal (delivered/cancelled). An open order's primary
 * action is "Mark delivered" (the backend accepts submitted→delivered directly);
 * preparing/ready are never surfaced as actions. */
function isOpenStatus(status: ServiceOrderStatus): boolean {
  return status !== "delivered" && status !== "cancelled";
}

const PAGE_SIZE = 25;
const ORDER_TYPES = ["room", "table", "direct"] as const;
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

/** Maps a badge tone onto the order card's left-rail accent variable. Mirrors
 * OperationCard's own map so the card keeps identical chrome while its action row
 * is rendered directly here (owner correction 1+2 — no folded "More" menu). */
const ACCENT_VAR: Record<BadgeTone, string> = {
  success: "var(--color-success)",
  warning: "var(--color-warning)",
  danger: "var(--color-danger)",
  info: "var(--color-info)",
  primary: "var(--color-primary)",
  vip: "var(--color-vip)",
  neutral: "var(--color-border-strong)",
};

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

    const facts: {
      key: string;
      label: string;
      value: ReactNode;
      icon?: LucideIcon;
    }[] = [
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

    // Owner correction 1+2: NO folded "More" menu — every action is a directly
    // visible control. The card's action set is EXACTLY: View details + Print
    // (always), Mark delivered + Cancel (a NEW/open order only), and
    // Return/exchange (a DELIVERED order only). Post-to-folio and direct settle are
    // gone from the card — settlement now runs inside the create form. Each action
    // reuses an EXISTING detail sub-flow (openDetailWith / deliverOrder); no order
    // mutation is duplicated here.
    const isOpen = isOpenStatus(r.status);
    // A settled order's cancel REVERSES money → also needs finance.refund; an
    // unsettled NEW cancel needs no extra permission.
    const canCancel = isOpen && (r.settlement === "unsettled" || can("finance.refund"));
    // Return/exchange: a DELIVERED, SETTLED order (direct or folio), gated on refund.
    const canReturn =
      r.status === "delivered" &&
      (r.settlement === "direct" || r.settlement === "folio") &&
      can("finance.refund");

    // Keeps the OperationCard chrome (badges, id row, fact row) but renders the
    // actions as an accessible DIRECT row instead of one primary + a More menu.
    return (
      <article
        className="op-card"
        aria-label={`${t.services.tabs.orders} ${r.order_number}`}
        style={{ "--op-accent": ACCENT_VAR[serviceOrderStatusTone(r.status)] } as CSSProperties}
      >
        <div className="op-card__header">
          <div className="op-card__badges">
            <Badge tone={serviceOrderStatusTone(r.status)}>{t.services.status[r.status]}</Badge>
            <Badge tone={settlementTone(r.settlement)}>{t.services.settlement[r.settlement]}</Badge>
            <Badge tone="neutral" variant="outline">
              {t.services.outlets[r.outlet]}
            </Badge>
          </div>
          <div className="op-card__idrow">
            <span className="op-card__title">{location}</span>
            <span className="op-card__number">
              <bdi dir="ltr">{r.order_number}</bdi>
            </span>
          </div>
        </div>

        <dl className="op-card__facts">
          {facts.map((fact) => (
            <div className="op-card__fact" key={fact.key}>
              <dt>
                {fact.icon ? <Icon icon={fact.icon} size="sm" /> : null}
                {fact.label}
              </dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>

        <div className="op-card__actions">
          {isOpen ? (
            <Button
              className="op-card__primary"
              size="sm"
              icon={PackageCheck}
              loading={advancingId === r.id}
              onClick={() => deliverOrder(r)}
            >
              {t.services.orders.markDelivered}
            </Button>
          ) : null}
          {canReturn ? (
            <Button
              className="op-card__primary"
              size="sm"
              variant="secondary"
              icon={Undo2}
              onClick={() => openDetailWith(r.id, "return")}
            >
              {t.services.orders.returnExchange}
            </Button>
          ) : null}
          {canCancel ? (
            <Button
              size="sm"
              variant="danger"
              icon={XCircle}
              onClick={() => openDetailWith(r.id, "cancel")}
            >
              {t.services.orders.cancel}
            </Button>
          ) : null}
          <IconButton
            icon={Eye}
            label={t.services.orders.details}
            onClick={() => openDetailWith(r.id, null)}
          />
          <IconButton
            icon={Printer}
            label={t.services.orders.print}
            onClick={() => openDetailWith(r.id, "kot")}
          />
        </div>
      </article>
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
            <div className="filter-bar__actions cluster">
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
        // The create modal owns its own success state now (order number +
        // print/view). onSaved only refreshes the list behind it; opening the
        // full details is the explicit "View order" action via onView.
        onSaved={() => load()}
        onView={(order) => {
          setCreating(false);
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

/** One option in a {@link RadioCardGroup}. */
interface RadioCardOption<T extends string> {
  value: T;
  title: ReactNode;
  description?: ReactNode;
  icon?: LucideIcon;
}

/**
 * Accessible single-select group built from buttons (WAI-ARIA radiogroup): the
 * checked option is the only tab stop (roving tabindex) and Arrow keys move both
 * the selection AND focus. Rendered either as a compact `segmented` switch (the
 * two-way outlet toggle) or as `cards` (order source, payment method). aria-checked
 * carries the state; no separate design language — just design-system tokens.
 */
function RadioCardGroup<T extends string>({
  label,
  value,
  options,
  onChange,
  variant = "cards",
}: {
  label: string;
  value: T;
  options: RadioCardOption<T>[];
  onChange: (value: T) => void;
  variant?: "cards" | "segmented";
}) {
  const groupRef = useRef<HTMLDivElement>(null);
  const activeIndex = options.findIndex((o) => o.value === value);

  function focusAt(index: number) {
    const buttons = groupRef.current?.querySelectorAll<HTMLButtonElement>('[role="radio"]');
    buttons?.[index]?.focus();
  }

  function move(delta: number) {
    if (options.length === 0) return;
    const base = activeIndex < 0 ? 0 : activeIndex;
    const next = (base + delta + options.length) % options.length;
    onChange(options[next].value);
    focusAt(next);
  }

  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      move(1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      move(-1);
    }
  }

  return (
    <div
      ref={groupRef}
      role="radiogroup"
      aria-label={label}
      className={variant === "segmented" ? "svc-segmented" : "svc-choices"}
      onKeyDown={onKeyDown}
    >
      {options.map((option, index) => {
        const checked = option.value === value;
        // Roving tabindex: the checked option (or the first, when nothing is
        // selected yet) is the single tab stop.
        const tabbable = checked || (activeIndex < 0 && index === 0);
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={tabbable ? 0 : -1}
            className={variant === "segmented" ? "svc-segmented__option" : "svc-choice"}
            onClick={() => onChange(option.value)}
          >
            {variant === "segmented" ? (
              <>
                {option.icon ? <Icon icon={option.icon} size="sm" /> : null}
                <span>{option.title}</span>
              </>
            ) : (
              <>
                {option.icon ? (
                  <span className="svc-choice__icon" aria-hidden="true">
                    <Icon icon={option.icon} />
                  </span>
                ) : null}
                <span className="svc-choice__body">
                  <span className="svc-choice__title">{option.title}</span>
                  {option.description ? (
                    <span className="svc-choice__desc">{option.description}</span>
                  ) : null}
                </span>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** One label/value row in the sticky order summary. */
function SvcSummaryRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="svc-sumrow">
      <span className="muted">{label}</span>
      <span className="svc-sumrow__value">{value}</span>
    </div>
  );
}

/** The three payment shapes the create form offers. `room_account` posts to the
 * linked stay's folio; the other two settle directly (cash / electronic). */
type PayMethod = "cash" | "electronic" | "room_account";

export function OrderCreateModal({
  open,
  onClose,
  onSaved,
  onView,
  initialOutlet,
  initialTable,
}: {
  open: boolean;
  onClose: () => void;
  /** Fired after a successful create+deliver+settle — the parent refreshes the
   * list. The modal keeps its own success state open (order number + print/view). */
  onSaved: (order: ServiceOrder) => void;
  /** Optional: open the full order details ("View order" in the success state). */
  onView?: (order: ServiceOrder) => void;
  /** Prefill (TablesTab shortcut): opens as a table order on this outlet. */
  initialOutlet?: ServiceOutlet;
  initialTable?: number;
}) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const enabledOutlets = useEnabledOutlets();

  const [source, setSource] = useState<ServiceOrderType>("room");
  const [outlet, setOutlet] = useState<ServiceOutlet>("restaurant");
  // The linked stay is now stored as the whole object (owner correction #4): the
  // room picker is server-side, so the selected resident must survive the search
  // results clearing between queries. `linkedStayId` is derived from it.
  const [selectedStay, setSelectedStay] = useState<Stay | null>(null);
  const [tableId, setTableId] = useState<number | null>(null);
  const [chargeToRoom, setChargeToRoom] = useState(false);
  const [customerName, setCustomerName] = useState("");

  // Room picker (owner correction #4): SERVER-SIDE search — nothing loads on mount,
  // a debounced query fetches only matching in-house stays, and results are capped.
  const [residentQuery, setResidentQuery] = useState("");
  const [residentMatches, setResidentMatches] = useState<Stay[]>([]);
  const [residentLoading, setResidentLoading] = useState(false);

  const [tables, setTables] = useState<RestaurantTable[]>([]);
  const [catalog, setCatalog] = useState<ServiceItem[]>([]);
  const [itemQuery, setItemQuery] = useState("");
  const [lines, setLines] = useState<ServiceOrderLineInput[]>([]);
  // Snapshot every ADDED item (owner correction #5): the added-line cards and the
  // live estimate read from here, so they never depend on the full (now hidden
  // until typed) outlet catalog list.
  const [itemSnapshots, setItemSnapshots] = useState<Map<number, ServiceItem>>(
    () => new Map(),
  );

  const [paymentMethod, setPaymentMethod] = useState<PayMethod>("cash");
  const [electronicMethod, setElectronicMethod] = useState<PaymentMethod>("card");
  const [reference, setReference] = useState("");
  const [amountReceived, setAmountReceived] = useState("");

  // The hotel BASE currency (D1a) — the order's single currency once created; used
  // here only to label the client-side estimate (server stays authoritative).
  const [baseCurrency, setBaseCurrency] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ServiceOrder | null>(null);
  const [invoice, setInvoice] = useState<ServiceTicket | null>(null);

  // MONEY CHAIN resume-safety (owner decision): the order created by a prior
  // partial attempt, and the ONE settle/post idempotency key. Both are set at most
  // once per submit sequence and REUSED on every retry so a failure mid-chain
  // never double-creates and never double-charges. Reset on (re)open + success.
  const createdOrderRef = useRef<ServiceOrder | null>(null);
  const settleKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setSource(initialTable ? "table" : "room");
    setOutlet(initialOutlet ?? enabledOutlets[0] ?? "restaurant");
    setSelectedStay(null);
    setResidentMatches([]);
    setResidentLoading(false);
    setTableId(initialTable ?? null);
    setChargeToRoom(false);
    setCustomerName("");
    setResidentQuery("");
    setItemQuery("");
    setLines([]);
    setItemSnapshots(new Map());
    setPaymentMethod("cash");
    setElectronicMethod("card");
    setReference("");
    setAmountReceived("");
    setError(null);
    setResult(null);
    setInvoice(null);
    createdOrderRef.current = null;
    settleKeyRef.current = null;
    // Residents are NO LONGER loaded on mount (owner correction #4) — the picker
    // stays empty until the user types (see the debounced search effect below).
    getSettings()
      .then((s) => setBaseCurrency((s.default_currency || "").toUpperCase()))
      .catch(() => setBaseCurrency(""));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when (re)opened
  }, [open, initialOutlet, initialTable]);

  // Debounced SERVER-SIDE resident search (owner correction #4): fetch only after
  // the user types; an empty query clears results (a hint is shown instead); the
  // server returns only matching in-house stays and we cap the list at 10.
  useEffect(() => {
    if (!open) return;
    const q = residentQuery.trim();
    if (q === "") {
      setResidentMatches([]);
      setResidentLoading(false);
      return;
    }
    setResidentLoading(true);
    let active = true;
    const handle = setTimeout(() => {
      listCurrentResidents(q)
        .then((r) => {
          if (active) setResidentMatches(r.results.slice(0, 10));
        })
        .catch(() => {
          if (active) setResidentMatches([]);
        })
        .finally(() => {
          if (active) setResidentLoading(false);
        });
    }, 280);
    return () => {
      active = false;
      clearTimeout(handle);
    };
  }, [open, residentQuery]);

  // The catalog follows the outlet — items must belong to the order's outlet. It
  // is loaded for client-side filtering but is NOT shown until the user types.
  useEffect(() => {
    if (!open) return;
    listServiceItems({ is_active: "true", is_available: "true", outlet, page: 1 })
      .then((r) => setCatalog(r.results))
      .catch(() => setCatalog([]));
  }, [open, outlet]);

  // Free tables of the chosen outlet (table orders only).
  useEffect(() => {
    if (!open || source !== "table") return;
    listTables({ outlet, status: "available" })
      .then((r) => setTables(r.results.filter((row) => !row.is_occupied)))
      .catch(() => setTables([]));
  }, [open, source, outlet]);

  const linkedStayId = selectedStay?.id ?? null;
  const isResidentLinked = selectedStay !== null;

  // "On room account" only exists while a stay is linked; drop back to cash when
  // the link is lost so an impossible payment can never be submitted.
  function dropRoomAccountIfUnlinked() {
    if (paymentMethod === "room_account") setPaymentMethod("cash");
  }

  function changeOutlet(next: ServiceOutlet) {
    if (next === outlet) return;
    setOutlet(next);
    // Lines reference items of the previous outlet; a mixed order is invalid.
    setLines([]);
    setItemSnapshots(new Map());
    setItemQuery("");
    setTableId(null);
  }

  function changeSource(next: ServiceOrderType) {
    setSource(next);
    setTableId(null);
    setChargeToRoom(false);
    setSelectedStay(null);
    setResidentQuery("");
    setResidentMatches([]);
    dropRoomAccountIfUnlinked();
  }

  function unlinkStay() {
    setSelectedStay(null);
    dropRoomAccountIfUnlinked();
  }

  // Selecting a resident clears the query so the results list hides — the chosen
  // stay is reflected in the summary and the pressed chip; type again to change it.
  function pickStay(next: Stay) {
    setSelectedStay(next);
    setResidentQuery("");
    setResidentMatches([]);
  }

  function toggleChargeToRoom(on: boolean) {
    setChargeToRoom(on);
    if (!on) {
      setSelectedStay(null);
      setResidentQuery("");
      setResidentMatches([]);
      dropRoomAccountIfUnlinked();
    }
  }

  // Switching payment method starts a clean money entry (a cash tender vs. an
  // electronic amount that must EQUAL the total) — never carry a stale value over.
  function changePaymentMethod(next: PayMethod) {
    setPaymentMethod(next);
    setAmountReceived("");
    setReference("");
  }

  // Add an item from the search results: MERGE a duplicate into the SAME line
  // (increment its quantity) rather than appending a second line. The item's
  // snapshot is stored so the line + estimate survive without the full catalog.
  function addItem(item: ServiceItem) {
    setItemSnapshots((prev) => {
      if (prev.has(item.id)) return prev;
      const next = new Map(prev);
      next.set(item.id, item);
      return next;
    });
    setLines((prev) => {
      const existing = prev.find((l) => l.service_item === item.id);
      if (existing) {
        return prev.map((l) =>
          l.service_item === item.id
            ? { ...l, quantity: String(Number(l.quantity) + 1) }
            : l,
        );
      }
      return [...prev, { service_item: item.id, quantity: "1", notes: "" }];
    });
    // Clear the item search so its results list hides after adding (the added line
    // now lives in the aside); type again to add another item.
    setItemQuery("");
  }

  function setLineQty(itemId: number, quantity: number) {
    if (quantity < 1) return; // quantity min 1
    setLines((prev) =>
      prev.map((l) =>
        l.service_item === itemId ? { ...l, quantity: String(quantity) } : l,
      ),
    );
  }

  function setLineNote(itemId: number, note: string) {
    setLines((prev) =>
      prev.map((l) => (l.service_item === itemId ? { ...l, notes: note } : l)),
    );
  }

  function removeItem(itemId: number) {
    setLines((prev) => prev.filter((l) => l.service_item !== itemId));
  }

  // Item smart-search (owner correction #5): nothing shows until the user types;
  // then the loaded OUTLET catalog is filtered client-side (name or category) and
  // capped at 10. An added item's own snapshot is what keeps its line + the
  // estimate working even though the full catalog is never displayed.
  const iq = itemQuery.trim().toLowerCase();
  const filteredItems =
    iq === ""
      ? []
      : catalog
          .filter(
            (i) =>
              i.name.toLowerCase().includes(iq) ||
              (i.category_name ?? "").toLowerCase().includes(iq),
          )
          .slice(0, 10);

  // Resolve an added line's item from its stored snapshot first (the catalog list
  // is no longer guaranteed to contain it), falling back to the loaded catalog.
  const lineItem = (id: number): ServiceItem | undefined =>
    itemSnapshots.get(id) ?? catalog.find((i) => i.id === id);

  // LIVE estimate (preview only — the server re-derives the authoritative total
  // from the frozen line snapshots). Computed from unit_price × qty and tax_rate,
  // read from the per-line snapshots (owner correction #5).
  const estimate = lines.reduce(
    (acc, line) => {
      const item = lineItem(line.service_item);
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
      acc.count += qty;
      return acc;
    },
    { subtotal: 0, tax: 0, total: 0, count: 0 },
  );
  // Prefer the base currency; fall back to an added item's own currency snapshot.
  const estimateCurrency =
    baseCurrency ||
    lines.map((l) => lineItem(l.service_item)).find((i) => i?.currency)?.currency ||
    "";
  const money = (amount: number) => formatMoney(amount, estimateCurrency, locale);

  const selectedTable = tables.find((row) => row.id === tableId) ?? null;

  const receivedNum = Number(amountReceived);
  const hasReceived = amountReceived.trim() !== "" && Number.isFinite(receivedNum);
  const cashShort =
    paymentMethod === "cash" && hasReceived && receivedNum < estimate.total;
  const change =
    paymentMethod === "cash" && hasReceived && receivedNum >= estimate.total
      ? receivedNum - estimate.total
      : null;
  // Electronic (owner corrections 6-8): the amount received MUST equal the amount
  // due (the total) — there is no change. Compared within a cent to absorb the
  // client-side float estimate; the backend records the exact total and change 0.
  const electronicMatches =
    paymentMethod === "electronic" &&
    hasReceived &&
    Math.abs(receivedNum - estimate.total) <= 0.005;
  const electronicMismatch =
    paymentMethod === "electronic" && hasReceived && !electronicMatches;

  // Create is enabled only when the source, items and payment are all valid.
  const sourceValid =
    source === "room" ? isResidentLinked : source === "table" ? tableId !== null : true;
  const itemsValid =
    lines.length > 0 &&
    lines.every((l) => {
      const qty = Number(l.quantity);
      return Number.isFinite(qty) && qty >= 1;
    });
  const paymentValid =
    paymentMethod === "room_account"
      ? isResidentLinked
      : paymentMethod === "cash"
        ? hasReceived && receivedNum >= estimate.total
        : electronicMatches; // electronic — received must EQUAL the total
  const canCreate =
    !busy && result === null && sourceValid && itemsValid && paymentValid;

  const paymentLabel =
    paymentMethod === "cash"
      ? t.finance.methods.cash
      : paymentMethod === "electronic"
        ? t.finance.methods[electronicMethod]
        : t.services.orders.payRoomAccount;

  // The summary's "who / where" row adapts to the chosen source.
  let sourceLocationLabel = t.services.orders.customerName;
  let sourceLocationValue: ReactNode = customerName.trim() || "—";
  if (source === "room") {
    sourceLocationLabel = t.services.orders.room;
    sourceLocationValue = selectedStay ? (
      <>
        <bdi dir="ltr">{selectedStay.room_number || selectedStay.room}</bdi>
        {selectedStay.primary_guest_name ? ` · ${selectedStay.primary_guest_name}` : ""}
      </>
    ) : (
      "—"
    );
  } else if (source === "table") {
    sourceLocationLabel = t.services.orders.table;
    sourceLocationValue = selectedTable ? (
      <bdi dir="ltr">{selectedTable.number}</bdi>
    ) : (
      "—"
    );
  }

  const paymentOptions: RadioCardOption<PayMethod>[] = [
    {
      value: "cash",
      title: t.finance.methods.cash,
      description: t.services.orders.payCashDesc,
      icon: Banknote,
    },
    {
      value: "electronic",
      title: t.finance.methods.electronic,
      description: t.services.orders.payElectronicDesc,
      icon: CreditCard,
    },
    // Never offered to a direct customer / no stay — only when a stay is linked.
    ...(isResidentLinked
      ? [
          {
            value: "room_account" as PayMethod,
            title: t.services.orders.payRoomAccount,
            description: t.services.orders.payRoomAccountDesc,
            icon: DoorOpen,
          },
        ]
      : []),
  ];

  /** ONE-action money chain (owner decision): create → deliver → settle/post,
   * resume-safe against partial failure. Same idempotency key on retry, and the
   * created order is never re-created — the tail resumes idempotently instead. */
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !canCreate) return;
    // Mint the settle/post idempotency key ONCE, then reuse it on every retry.
    const settleKey = settleKeyRef.current ?? mintIdempotencyKey();
    settleKeyRef.current = settleKey;
    setBusy(true);
    setError(null);
    try {
      let order = createdOrderRef.current;
      if (!order) {
        order = await createServiceOrder({
          order_type: source,
          outlet,
          // A DIRECT order never carries a stay or table; a table order links a
          // resident stay only when "charge to room" is on.
          stay: source === "direct" ? null : linkedStayId,
          table: source === "table" ? tableId : null,
          customer_name:
            source === "table" || source === "direct" ? customerName.trim() : "",
          requested_delivery_time: null,
          notes: "",
          items: lines,
        });
        // Never re-create on a retry — the settle step resumes against this order.
        createdOrderRef.current = order;
      }
      // Owner-approved OFFICIAL cycle: create → settle, and the order STAYS NEW.
      // Delivery is NOT part of this form — it is a later, card-only action. The
      // backend permits settling a NEW (undelivered) order.
      if (paymentMethod === "cash" || paymentMethod === "electronic") {
        // amount_received travels for BOTH shapes now (owner corrections 6-8): the
        // cash tender (may exceed the total → change) or the electronic amount,
        // which is validated to EQUAL the total (change 0). Reference stays
        // electronic-only; method is "cash" or the chosen electronic method.
        order = await settleServiceOrderDirect(order.id, {
          method: paymentMethod === "cash" ? "cash" : electronicMethod,
          amount_received: amountReceived,
          reference:
            paymentMethod === "electronic" ? reference.trim() || undefined : undefined,
          settlement_key: settleKey,
        });
      } else {
        order = await postServiceOrderToFolio(order.id, {
          settlement_key: settleKey,
        });
      }
      // Chain complete — the next open is a genuinely new attempt.
      settleKeyRef.current = null;
      createdOrderRef.current = null;
      setResult(order);
      onSaved(order);
    } catch (err) {
      // Keep BOTH refs so the next click RESUMES the tail idempotently (never a
      // second order, never a second charge).
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function openInvoice() {
    if (!result) return;
    try {
      setInvoice(await getServiceOrderTicket(result.id, "guest_check"));
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  // Server-side room picker body (owner correction #4): the linked stay stays
  // visible as a pressed chip once chosen; otherwise a subtle "type to search"
  // hint, a loading line, a no-matches note, or the (≤10) matches are shown — but
  // NEVER a resident list before the user has typed.
  function residentResults() {
    const typed = residentQuery.trim() !== "";
    return (
      <div className="stack-tight">
        {selectedStay && !typed ? (
          <div className="svc-results" role="group" aria-label={t.services.orders.searchResults}>
            <button
              type="button"
              className="svc-result"
              aria-pressed
              onClick={unlinkStay}
            >
              <span className="svc-result__main">
                <span className="svc-result__name">
                  {t.services.orders.room}{" "}
                  <bdi dir="ltr">{selectedStay.room_number || selectedStay.room}</bdi>
                  {` · ${selectedStay.primary_guest_name || "—"}`}
                </span>
                <span className="svc-result__meta">
                  {stayStatusLabel(selectedStay.status, t)}
                </span>
              </span>
              <Icon icon={CheckCircle2} />
            </button>
          </div>
        ) : null}
        {residentLoading ? (
          <p className="muted small">{t.common.loading}</p>
        ) : !typed ? (
          selectedStay ? null : (
            <p className="muted small">{t.services.orders.residentTypeHint}</p>
          )
        ) : residentMatches.length === 0 ? (
          <p className="muted small">{t.services.orders.noResidents}</p>
        ) : (
          <div className="svc-results" role="group" aria-label={t.services.orders.searchResults}>
            {residentMatches.map((s) => {
              const selected = s.id === linkedStayId;
              return (
                <button
                  key={s.id}
                  type="button"
                  className="svc-result"
                  aria-pressed={selected}
                  onClick={() => (selected ? unlinkStay() : pickStay(s))}
                >
                  <span className="svc-result__main">
                    <span className="svc-result__name">
                      {t.services.orders.room} <bdi dir="ltr">{s.room_number || s.room}</bdi>
                      {` · ${s.primary_guest_name || "—"}`}
                    </span>
                    <span className="svc-result__meta">{stayStatusLabel(s.status, t)}</span>
                  </span>
                  {selected ? <Icon icon={CheckCircle2} /> : null}
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.services.orders.createTitle}
      closeLabel={t.common.close}
      size="full"
      preventClose={busy}
      footer={
        // The create form has NO footer (owner: "no huge footer") — its Create +
        // Cancel now live pinned in the aside. Only the terminal SUCCESS state keeps
        // a footer Close, so that state is preserved byte-for-byte.
        result ? <Button onClick={onClose}>{t.common.close}</Button> : undefined
      }
    >
      {result ? (
        // SUCCESS state — order number + print invoice + view order, then close.
        <div className="stack" role="status">
          <div className="svc-success">
            <span className="svc-success__icon" aria-hidden="true">
              <Icon icon={CheckCircle2} size="xl" />
            </span>
            <div className="stack-tight">
              <span className="svc-section__title">{t.services.orders.successTitle}</span>
              <p className="muted">
                {t.services.orders.successMessage.replace("{number}", result.order_number)}
              </p>
            </div>
          </div>
          <StatusSummaryCard
            items={[
              {
                label: t.services.orders.number,
                value: <bdi dir="ltr">{result.order_number}</bdi>,
              },
              {
                label: t.services.orders.total,
                value: (
                  <bdi dir="ltr">
                    {formatMoney(result.totals.total, result.totals.currency || result.currency, locale)}
                  </bdi>
                ),
                emphasis: true,
              },
            ]}
          />
          <div className="cluster">
            <Button variant="secondary" icon={Printer} onClick={openInvoice}>
              {t.services.orders.printInvoice}
            </Button>
            {onView ? (
              <Button variant="secondary" icon={Eye} onClick={() => onView(result)}>
                {t.services.orders.viewOrder}
              </Button>
            ) : null}
          </div>
        </div>
      ) : (
        <form id="svc-order-form" onSubmit={submit} noValidate>
          <div className="svc-order">
            <div className="svc-order__main">
              {error ? <Alert tone="error">{error}</Alert> : null}

              {/* (1) Restaurant or Café — a segmented control (never a dropdown). */}
              <section className="svc-section">
                <span className="svc-section__title">{t.services.orders.outletSection}</span>
                <span className="svc-section__desc">{t.services.orders.createDescription}</span>
                <RadioCardGroup
                  variant="segmented"
                  label={t.services.outlet}
                  value={outlet}
                  onChange={changeOutlet}
                  options={enabledOutlets.map((o) => ({
                    value: o,
                    title: t.services.outlets[o],
                    icon: o === "restaurant" ? Utensils : Coffee,
                  }))}
                />
              </section>

              {/* (2) Order source — three choice cards; only the chosen source's
                  fields render (smooth conditional show/hide). */}
              <section className="svc-section">
                <span className="svc-section__title">{t.services.orders.sourceSection}</span>
                <RadioCardGroup
                  label={t.services.orders.sourceSection}
                  value={source}
                  onChange={changeSource}
                  options={[
                    {
                      value: "room",
                      title: t.services.orderTypes.room,
                      description: t.services.orders.sourceRoomDesc,
                      icon: BedDouble,
                    },
                    {
                      value: "table",
                      title: t.services.orderTypes.table,
                      description: t.services.orders.sourceTableDesc,
                      icon: Armchair,
                    },
                    {
                      value: "direct",
                      title: t.services.orderTypes.direct,
                      description: t.services.orders.sourceDirectDesc,
                      icon: UserRound,
                    },
                  ]}
                />

                {source === "room" ? (
                  <div className="stack">
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
                    {residentResults()}
                  </div>
                ) : null}

                {source === "table" ? (
                  <div className="svc-table-source">
                    {/* Compact one-line picker: a select until a table is chosen,
                        then a small chip with a Change/clear button — never a tall
                        list, so TABLE mode is no taller than ROOM / DIRECT. */}
                    {tableId === null ? (
                      <FormField label={t.services.orders.tablesLabel} htmlFor="o-table-select">
                        <Select
                          id="o-table-select"
                          value=""
                          placeholder={
                            tables.length === 0
                              ? t.services.orders.noTablesAvailable
                              : t.services.orders.tableSelectPlaceholder
                          }
                          options={tables.map((row) => ({
                            value: String(row.id),
                            label: `${t.services.orders.table} ${row.number}${row.name ? " · " + row.name : ""} — ${t.services.tables.capacity} ${row.capacity}`,
                          }))}
                          onChange={(e) => setTableId(e.target.value ? Number(e.target.value) : null)}
                        />
                      </FormField>
                    ) : (
                      <div className="svc-chip">
                        <span className="svc-chip__text">
                          {t.services.orders.table} <bdi dir="ltr">{selectedTable?.number}</bdi>
                          {selectedTable?.name ? ` · ${selectedTable.name}` : ""}
                          {" — "}
                          {t.services.tables.capacity} <bdi dir="ltr">{selectedTable?.capacity}</bdi>
                        </span>
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() => setTableId(null)}
                        >
                          {t.services.orders.change}
                        </Button>
                      </div>
                    )}

                    {/* Customer name + "resident" toggle on ONE compact row. When
                        resident is on, the name field is REPLACED by the smart stay
                        search in the same space (no extra vertical stack). */}
                    <div className="svc-table-source__row">
                      <div className="svc-grow">
                        {chargeToRoom ? (
                          <FormField label={t.common.search} htmlFor="o-resident-search-t">
                            <Input
                              id="o-resident-search-t"
                              value={residentQuery}
                              placeholder={t.services.orders.residentSearchPlaceholder}
                              onChange={(e) => setResidentQuery(e.target.value)}
                            />
                          </FormField>
                        ) : (
                          <FormField label={t.services.orders.customerName} htmlFor="o-customer">
                            <Input
                              id="o-customer"
                              value={customerName}
                              onChange={(e) => setCustomerName(e.target.value)}
                            />
                          </FormField>
                        )}
                      </div>
                      <Switch
                        id="o-charge-room"
                        checked={chargeToRoom}
                        onChange={toggleChargeToRoom}
                        label={t.services.orders.residentToggle}
                      />
                    </div>
                    {chargeToRoom ? residentResults() : null}
                  </div>
                ) : null}

                {source === "direct" ? (
                  <FormField label={t.services.orders.customerName} htmlFor="o-customer-d">
                    <Input
                      id="o-customer-d"
                      value={customerName}
                      onChange={(e) => setCustomerName(e.target.value)}
                    />
                  </FormField>
                ) : null}
              </section>

              {/* (3) Items — search-first (owner correction #5): nothing shows
                  until the user types; matches are outlet-scoped and capped at 10. */}
              <section className="svc-section">
                <span className="svc-section__title">{t.services.orders.itemsSection}</span>
                {catalog.length === 0 ? (
                  <p className="muted small">{t.services.orders.noCatalog}</p>
                ) : (
                  <>
                    <FormField label={t.services.orders.itemSearchLabel} htmlFor="o-item-search">
                      <Input
                        id="o-item-search"
                        value={itemQuery}
                        placeholder={t.services.orders.itemSearchPlaceholder}
                        onChange={(e) => setItemQuery(e.target.value)}
                      />
                    </FormField>
                    {itemQuery.trim() === "" ? (
                      <p className="muted small">{t.services.orders.itemTypeHint}</p>
                    ) : filteredItems.length === 0 ? (
                      <p className="muted small">{t.services.orders.noItemsFound}</p>
                    ) : (
                      <div
                        className="svc-results"
                        role="group"
                        aria-label={t.services.orders.searchResults}
                      >
                        {filteredItems.map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            className="svc-result"
                            onClick={() => addItem(item)}
                          >
                            <span className="svc-result__main">
                              <span className="svc-result__name">{item.name}</span>
                              <span className="svc-result__meta">
                                {item.category_name} · {t.services.outlets[item.outlet]}
                              </span>
                            </span>
                            <span className="svc-result__price">
                              <bdi dir="ltr">
                                {formatMoney(item.unit_price, item.currency, locale)}
                              </bdi>
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </section>

              {/* (4) Payment method — three choice cards (room account only when a
                  stay is linked), then the method-specific money fields. */}
              <section className="svc-section">
                <span className="svc-section__title">{t.services.orders.paymentMethod}</span>
                <RadioCardGroup
                  label={t.services.orders.paymentMethod}
                  value={paymentMethod}
                  onChange={changePaymentMethod}
                  options={paymentOptions}
                />

                {paymentMethod === "cash" ? (
                  <div className="form-grid">
                    <div className="field">
                      <span className="field__label">{t.services.orders.amountDue}</span>
                      <strong>
                        <bdi dir="ltr">{money(estimate.total)}</bdi>
                      </strong>
                    </div>
                    <FormField
                      label={t.services.orders.amountReceived}
                      htmlFor="o-received"
                      hint={t.services.orders.amountReceivedHint}
                      error={cashShort ? t.services.orders.shortCash : undefined}
                    >
                      <Input
                        id="o-received"
                        type="number"
                        min="0"
                        step="0.01"
                        inputMode="decimal"
                        value={amountReceived}
                        invalid={cashShort}
                        onChange={(e) => setAmountReceived(e.target.value)}
                      />
                    </FormField>
                    <div className="field form-grid__full">
                      <span className="field__label">{t.services.orders.change}</span>
                      <span className="svc-change" aria-live="polite">
                        {change !== null ? (
                          <bdi dir="ltr">{money(change)}</bdi>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </span>
                    </div>
                  </div>
                ) : null}

                {paymentMethod === "electronic" ? (
                  <div className="form-grid">
                    <div className="field">
                      <span className="field__label">{t.services.orders.amountDue}</span>
                      <strong>
                        <bdi dir="ltr">{money(estimate.total)}</bdi>
                      </strong>
                    </div>
                    {/* Owner corrections 6-8: electronic ALSO captures the amount
                        received (in the base currency), which must EQUAL the amount
                        due — Create is blocked on any mismatch, and there is no
                        change (received === total). */}
                    <FormField
                      label={t.services.orders.amountReceived}
                      htmlFor="o-e-received"
                      hint={t.services.orders.electronicReceivedHint}
                      error={electronicMismatch ? t.services.orders.mustMatchDue : undefined}
                    >
                      <Input
                        id="o-e-received"
                        type="number"
                        min="0"
                        step="0.01"
                        inputMode="decimal"
                        value={amountReceived}
                        invalid={electronicMismatch}
                        onChange={(e) => setAmountReceived(e.target.value)}
                      />
                    </FormField>
                    <FormField label={t.services.orders.electronicMethod} htmlFor="o-emethod">
                      <Select
                        id="o-emethod"
                        value={electronicMethod}
                        options={ELECTRONIC_METHODS.map((m) => ({
                          value: m,
                          label: t.finance.methods[m],
                        }))}
                        onChange={(e) => setElectronicMethod(e.target.value as PaymentMethod)}
                      />
                    </FormField>
                    <FormField
                      label={t.services.orders.reference}
                      htmlFor="o-ref"
                      className="form-grid__full"
                    >
                      <Input
                        id="o-ref"
                        value={reference}
                        placeholder={t.services.orders.referencePlaceholder}
                        onChange={(e) => setReference(e.target.value)}
                      />
                    </FormField>
                  </div>
                ) : null}

                {paymentMethod === "room_account" && selectedStay ? (
                  <Card className="stack-tight">
                    <span className="svc-section__title">
                      {t.services.orders.roomAccountTitle}
                    </span>
                    <SvcSummaryRow
                      label={t.services.orders.room}
                      value={
                        <bdi dir="ltr">
                          {selectedStay.room_number || selectedStay.room}
                        </bdi>
                      }
                    />
                    <SvcSummaryRow
                      label={t.services.orders.guest}
                      value={selectedStay.primary_guest_name || "—"}
                    />
                    <SvcSummaryRow
                      label={t.services.orders.total}
                      value={<bdi dir="ltr">{money(estimate.total)}</bdi>}
                    />
                    <p className="muted small">{t.services.orders.roomAccountNotice}</p>
                  </Card>
                ) : null}
              </section>
            </div>

            {/* (5) Aside — selected items (scrolls on overflow) above a PINNED
                order summary + Create/Cancel. Fills the column on desktop so the
                modal itself never scrolls; drops below the form on mobile. */}
            <aside className="svc-order__aside">
              <div className="svc-order__items">
                <span className="field__label">{t.services.orders.selectedItems}</span>
                {lines.length === 0 ? (
                  <p className="muted small">{t.services.orders.noLines}</p>
                ) : (
                  <div className="svc-lines">
                    {lines.map((line) => {
                      const item = lineItem(line.service_item);
                      if (!item) return null;
                      const qty = Number(line.quantity) || 1;
                      const lineTotal = Number(item.unit_price) * qty;
                      return (
                        <div className="svc-line" key={line.service_item}>
                          <span className="svc-line__main">
                            <span className="svc-line__name">{item.name}</span>
                            <span className="svc-line__meta">{item.category_name}</span>
                          </span>
                          <span
                            className="svc-stepper"
                            role="group"
                            aria-label={t.services.orders.quantity}
                          >
                            <IconButton
                              icon={Minus}
                              label={t.services.orders.decreaseQty}
                              type="button"
                              disabled={qty <= 1}
                              onClick={() => setLineQty(item.id, qty - 1)}
                            />
                            <span className="svc-stepper__value" aria-live="polite">
                              <bdi dir="ltr">{qty}</bdi>
                            </span>
                            <IconButton
                              icon={Plus}
                              label={t.services.orders.increaseQty}
                              type="button"
                              onClick={() => setLineQty(item.id, qty + 1)}
                            />
                          </span>
                          <span className="svc-line__prices">
                            <span className="svc-line__meta">
                              {t.services.orders.unitPrice}:{" "}
                              <bdi dir="ltr">
                                {formatMoney(item.unit_price, item.currency, locale)}
                              </bdi>
                            </span>
                            <strong>
                              <bdi dir="ltr">
                                {formatMoney(lineTotal, item.currency, locale)}
                              </bdi>
                            </strong>
                          </span>
                          <span className="svc-line__note">
                            <Input
                              aria-label={`${t.services.orders.lineNotes} · ${item.name}`}
                              value={line.notes ?? ""}
                              placeholder={t.services.orders.lineNotes}
                              onChange={(e) => setLineNote(item.id, e.target.value)}
                            />
                          </span>
                          <IconButton
                            icon={Trash2}
                            label={t.services.orders.removeLine}
                            type="button"
                            onClick={() => removeItem(item.id)}
                          />
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="svc-order__foot">
                <Card className="stack">
                  <span className="svc-section__title">{t.services.orders.summarySection}</span>
                  <div className="stack-tight">
                    <SvcSummaryRow label={t.services.outlet} value={t.services.outlets[outlet]} />
                    <SvcSummaryRow
                      label={t.services.orderType}
                      value={t.services.orderTypes[source]}
                    />
                    <SvcSummaryRow label={sourceLocationLabel} value={sourceLocationValue} />
                    <SvcSummaryRow
                      label={t.services.orders.itemCount}
                      value={<bdi dir="ltr">{estimate.count}</bdi>}
                    />
                  </div>
                  <div className="stack-tight">
                    <SvcSummaryRow
                      label={t.services.orders.subtotal}
                      value={<bdi dir="ltr">{money(estimate.subtotal)}</bdi>}
                    />
                    <SvcSummaryRow
                      label={t.services.orders.tax}
                      value={<bdi dir="ltr">{money(estimate.tax)}</bdi>}
                    />
                  </div>
                  <div className="stack-tight" aria-live="polite">
                    <span className="field__label">{t.services.orders.estimatedTotal}</span>
                    <span className="svc-total">
                      <bdi dir="ltr">{money(estimate.total)}</bdi>
                    </span>
                    <span className="muted small">{t.services.orders.estimatedTotalHint}</span>
                  </div>
                  <div className="stack-tight">
                    <SvcSummaryRow label={t.services.orders.paymentMethod} value={paymentLabel} />
                    {(paymentMethod === "cash" || paymentMethod === "electronic") &&
                    hasReceived ? (
                      <SvcSummaryRow
                        label={t.services.orders.amountReceivedLabel}
                        value={<bdi dir="ltr">{money(receivedNum)}</bdi>}
                      />
                    ) : null}
                    {paymentMethod === "cash" && change !== null ? (
                      <SvcSummaryRow
                        label={t.services.orders.change}
                        value={<bdi dir="ltr">{money(change)}</bdi>}
                      />
                    ) : null}
                  </div>
                </Card>

                <div className="svc-order__actions">
                  <Button
                    form="svc-order-form"
                    type="submit"
                    loading={busy}
                    disabled={!canCreate}
                  >
                    {t.services.orders.submit}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={onClose}
                    disabled={busy}
                  >
                    {t.common.cancel}
                  </Button>
                </div>
              </div>
            </aside>
          </div>
        </form>
      )}

      {/* Print invoice = the guest-check ticket (reuses the ticket print flow). */}
      <PrintModal
        open={invoice !== null}
        title={t.services.ticket.guestCheckTitle}
        onClose={() => setInvoice(null)}
      >
        {invoice ? (
          <PrintDocumentLayout
            hotelName={invoice.hotel.hotel_name}
            hotelAddress={invoice.hotel.address}
            hotelPhone={invoice.hotel.phone}
            docTitle={t.services.ticket.guestCheckTitle}
            docNumber={invoice.order.order_number}
            meta={[
              { label: t.services.outlet, value: t.services.outlets[invoice.order.outlet] },
              ...(invoice.order.order_type === "room"
                ? [{ label: t.services.ticket.roomLabel, value: invoice.order.room_number || "—" }]
                : [{ label: t.services.ticket.tableLabel, value: invoice.order.table_number || "—" }]),
              ...(invoice.order.customer_name
                ? [{ label: t.services.ticket.customerLabel, value: invoice.order.customer_name }]
                : []),
              { label: t.services.ticket.guestLabel, value: invoice.order.guest_name || "—" },
              { label: t.services.ticket.timeLabel, value: formatDateTime(invoice.order.ordered_at, locale) },
            ]}
            totals={
              invoice.totals
                ? [
                    { label: t.services.orders.subtotal, value: formatMoney(invoice.totals.subtotal, invoice.order.currency, locale) },
                    { label: t.services.orders.tax, value: formatMoney(invoice.totals.tax_total, invoice.order.currency, locale) },
                    { label: t.services.orders.total, value: <strong>{formatMoney(invoice.totals.total, invoice.order.currency, locale)}</strong> },
                  ]
                : undefined
            }
            notes={invoice.order.notes || undefined}
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
                {invoice.items.map((i, idx) => (
                  <tr key={idx}>
                    <td>{i.item_name}</td>
                    <td>{i.quantity}</td>
                    <td>{i.unit_price != null ? formatMoney(i.unit_price, invoice.order.currency, locale) : "—"}</td>
                    <td>{i.total_amount != null ? formatMoney(i.total_amount, invoice.order.currency, locale) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PrintDocumentLayout>
        ) : null}
      </PrintModal>
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
  // Cancel is a PRE-DELIVERY action for any NEW order. A settled order's cancel
  // REVERSES money (refund/credit) and additionally needs finance.refund.
  const cancelReversesMoney = order.settlement !== "unsettled" || order.is_posted;
  const canCancel =
    isOpenStatus(order.status) &&
    (!cancelReversesMoney || can("finance.refund"));
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
              // C2 — settlement_reference is finance-sensitive: shown only with
              // finance.view (the server also blanks it otherwise — defense in depth).
              ...(order.settlement === "direct" &&
              order.settlement_reference &&
              can("finance.view")
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
          {cancelReversesMoney ? (
            <Alert tone="warning">{t.services.orders.cancelReversalWarning}</Alert>
          ) : null}
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

  // C7 — client-side quantity guard (UX): a selected line's quantity must be
  // positive and must not exceed its remaining returnable quantity. The server
  // still enforces this (invalid_return_composition); this only gives instant,
  // per-line feedback instead of a round-trip error.
  function lineQtyError(lineId: number, remaining: number): string | null {
    if (!(lineId in sel)) return null;
    const q = Number(sel[lineId]);
    if (!Number.isFinite(q) || q <= 0) return t.services.returns.qtyPositive;
    if (q > remaining + 0.00001)
      return t.services.returns.qtyExceedsRemaining.replace("{qty}", String(remaining));
    return null;
  }
  const overReturn = returnable.some((r) => lineQtyError(r.line.id, r.remaining) !== null);

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
    !overReturn &&
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
                      error={lineQtyError(r.line.id, r.remaining) ?? undefined}
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
