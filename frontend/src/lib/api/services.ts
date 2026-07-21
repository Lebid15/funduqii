/**
 * Client-side service catalog + orders API (Phase 9). Calls the same-origin
 * hotel BFF proxy. The backend owns all money math, numbering, the status
 * workflow, and the once-only posting to a folio — these helpers never compute
 * totals or post charges themselves.
 */
import { hotelJson } from "./hotelFetch";
import type {
  PaginatedResponse,
  PaymentMethod,
  RestaurantTable,
  RestaurantTableStatus,
  ServiceCategory,
  ServiceItem,
  ServiceOrder,
  ServiceOrderListItem,
  ServiceOrderReturn,
  ServiceOutlet,
  ServiceReturnKind,
  ServiceTicket,
  ServicesOverview,
} from "./types";

/**
 * Mint a fresh idempotency key for ONE money-moving attempt (settle / return).
 *
 * FINANCIAL SAFETY: mint the key ONCE per attempt (when the sub-dialog opens),
 * REUSE it across every retry, and regenerate it only AFTER a success — never
 * inside the submit handler. A stable key is what makes a network-failure retry
 * safe: replaying the same key either returns the original result (identical
 * payload) or fails closed with a 409 `idempotency_key_conflict` (edited
 * payload) — never a second charge/payment. A per-submit key defeats it. Mirrors
 * the guest-folio AddServiceModal pattern.
 */
export function mintIdempotencyKey(): string {
  return crypto.randomUUID();
}

function toQuery(params?: object): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

const B = "/services";

export function getServicesOverview(): Promise<ServicesOverview> {
  return hotelJson<ServicesOverview>(`${B}/overview`);
}

// --- Categories ---------------------------------------------------------------

export function listServiceCategories(params?: {
  search?: string;
  outlet?: string;
  is_active?: string;
  page?: number;
}): Promise<PaginatedResponse<ServiceCategory>> {
  return hotelJson<PaginatedResponse<ServiceCategory>>(
    `${B}/categories${toQuery(params)}`,
  );
}

export type ServiceCategoryBody = Partial<
  Pick<
    ServiceCategory,
    "outlet" | "name" | "description" | "sort_order" | "is_active"
  >
>;

export function createServiceCategory(body: ServiceCategoryBody): Promise<ServiceCategory> {
  return hotelJson<ServiceCategory>(`${B}/categories`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateServiceCategory(
  id: number,
  body: ServiceCategoryBody,
): Promise<ServiceCategory> {
  return hotelJson<ServiceCategory>(`${B}/categories/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteServiceCategory(id: number): Promise<void> {
  return hotelJson<void>(`${B}/categories/${id}`, { method: "DELETE" });
}

// --- Items ----------------------------------------------------------------------

export interface ServiceItemListParams {
  search?: string;
  category?: number;
  outlet?: string;
  is_available?: string;
  is_active?: string;
  ordering?: string;
  page?: number;
}

export function listServiceItems(
  params?: ServiceItemListParams,
): Promise<PaginatedResponse<ServiceItem>> {
  return hotelJson<PaginatedResponse<ServiceItem>>(`${B}/items${toQuery(params)}`);
}

export type ServiceItemBody = Partial<
  Pick<
    ServiceItem,
    | "category"
    | "name"
    | "description"
    | "unit_price"
    | "currency"
    | "tax_rate"
    | "is_available"
    | "is_active"
    | "sort_order"
  >
>;

export function createServiceItem(body: ServiceItemBody): Promise<ServiceItem> {
  return hotelJson<ServiceItem>(`${B}/items`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateServiceItem(id: number, body: ServiceItemBody): Promise<ServiceItem> {
  return hotelJson<ServiceItem>(`${B}/items/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteServiceItem(id: number): Promise<void> {
  return hotelJson<void>(`${B}/items/${id}`, { method: "DELETE" });
}

// --- Tables ----------------------------------------------------------------------

export function listTables(params?: {
  outlet?: string;
  status?: string;
  page?: number;
}): Promise<PaginatedResponse<RestaurantTable>> {
  return hotelJson<PaginatedResponse<RestaurantTable>>(
    `${B}/tables${toQuery(params)}`,
  );
}

export interface RestaurantTableCreateBody {
  outlet: ServiceOutlet;
  number: string;
  name?: string;
  capacity?: number;
}

export function createTable(body: RestaurantTableCreateBody): Promise<RestaurantTable> {
  return hotelJson<RestaurantTable>(`${B}/tables`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateTable(
  id: number,
  body: { number?: string; name?: string; capacity?: number },
): Promise<RestaurantTable> {
  return hotelJson<RestaurantTable>(`${B}/tables/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function setTableStatus(
  id: number,
  status: RestaurantTableStatus,
  note = "",
): Promise<RestaurantTable> {
  return hotelJson<RestaurantTable>(`${B}/tables/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status, note }),
  });
}

export function deleteTable(id: number): Promise<void> {
  return hotelJson<void>(`${B}/tables/${id}`, { method: "DELETE" });
}

// --- Orders ----------------------------------------------------------------------

export interface ServiceOrderListParams {
  search?: string;
  status?: string;
  order_type?: string;
  outlet?: string;
  settlement?: string;
  stay?: number;
  room?: number;
  table?: number;
  date?: string;
  posted?: string;
  ordering?: string;
  page?: number;
}

export function listServiceOrders(
  params?: ServiceOrderListParams,
): Promise<PaginatedResponse<ServiceOrderListItem>> {
  return hotelJson<PaginatedResponse<ServiceOrderListItem>>(
    `${B}/orders${toQuery(params)}`,
  );
}

export function getServiceOrder(id: number): Promise<ServiceOrder> {
  return hotelJson<ServiceOrder>(`${B}/orders/${id}`);
}

export interface ServiceOrderLineInput {
  service_item: number;
  quantity: string;
  notes?: string;
}

export interface ServiceOrderCreateBody {
  order_type: "room" | "table" | "direct";
  outlet: ServiceOutlet;
  stay?: number | null;
  table?: number | null;
  customer_name?: string;
  status?: "draft" | "submitted";
  requested_delivery_time?: string | null;
  notes?: string;
  internal_notes?: string;
  items: ServiceOrderLineInput[];
}

export function createServiceOrder(body: ServiceOrderCreateBody): Promise<ServiceOrder> {
  return hotelJson<ServiceOrder>(`${B}/orders`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** After creation only meta + draft items may change — never the shape
 * (order_type/outlet/table/stay/customer_name are immutable). */
export interface ServiceOrderUpdateBody {
  requested_delivery_time?: string | null;
  notes?: string;
  internal_notes?: string;
  items?: ServiceOrderLineInput[];
}

export function updateServiceOrder(
  id: number,
  body: ServiceOrderUpdateBody,
): Promise<ServiceOrder> {
  return hotelJson<ServiceOrder>(`${B}/orders/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function setServiceOrderStatus(
  id: number,
  status: string,
  note = "",
): Promise<ServiceOrder> {
  return hotelJson<ServiceOrder>(`${B}/orders/${id}/status`, {
    method: "POST",
    body: JSON.stringify({ status, note }),
  });
}

export function cancelServiceOrder(id: number, reason: string): Promise<ServiceOrder> {
  return hotelJson<ServiceOrder>(`${B}/orders/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

/** Post a delivered, stay-linked order to the guest folio (once only). The
 * optional `settlement_key` is the reused idempotency key (see
 * {@link mintIdempotencyKey}); the backend already accepts it and returns the
 * original posting on replay, so a retry never posts a second charge. */
export function postServiceOrderToFolio(
  id: number,
  body?: { settlement_key?: string },
): Promise<ServiceOrder> {
  return hotelJson<ServiceOrder>(`${B}/orders/${id}/post-to-folio`, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });
}

/** Cancel ONE line before settlement (reason mandatory); returns the order. */
export function cancelServiceOrderItem(
  orderId: number,
  itemId: number,
  reason: string,
): Promise<ServiceOrder> {
  return hotelJson<ServiceOrder>(`${B}/orders/${orderId}/items/${itemId}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

/** Direct payment (cash register cycle) — financially closes the order.
 *
 * `amount_received` (a decimal string) is an OPTIONAL cash tender; the backend
 * rejects a short tender and computes `change_given`. `reference` is an optional
 * electronic reference passed to the receipt. `settlement_key` is the reused
 * idempotency key (see {@link mintIdempotencyKey}). The finance Payment always
 * records the exact server-derived total; these only annotate the order. */
export interface ServiceOrderSettleDirectBody {
  method: PaymentMethod;
  amount_received?: string;
  reference?: string;
  settlement_key?: string;
}

export function settleServiceOrderDirect(
  id: number,
  body: ServiceOrderSettleDirectBody,
): Promise<ServiceOrder> {
  return hotelJson<ServiceOrder>(`${B}/orders/${id}/settle-direct`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** ONE returned line of a return/exchange request. `replacement_item` is sent
 * only for an exchange (its quantity defaults server-side to the returned qty). */
export interface ServiceReturnItemInput {
  original_item: number;
  quantity: string;
  replacement_item?: number | null;
  replacement_quantity?: string | null;
}

/** Return / exchange a delivered, settled order (gated `finance.refund`). The
 * server computes and verifies the delta sign against `kind`. `method`/
 * `amount_received`/`reference` carry a DIRECT order's money movement. */
export interface ServiceOrderReturnBody {
  kind: ServiceReturnKind;
  reason: string;
  items: ServiceReturnItemInput[];
  method?: PaymentMethod | null;
  amount_received?: string | null;
  reference?: string;
  idempotency_key?: string;
}

/** POST /orders/{id}/return returns BOTH the new return and the refreshed order. */
export interface ServiceOrderReturnResult {
  return: ServiceOrderReturn;
  order: ServiceOrder;
}

export function returnServiceOrder(
  id: number,
  body: ServiceOrderReturnBody,
): Promise<ServiceOrderReturnResult> {
  return hotelJson<ServiceOrderReturnResult>(`${B}/orders/${id}/return`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getServiceOrderTicket(
  id: number,
  variant: "kot" | "guest_check" = "kot",
): Promise<ServiceTicket> {
  return hotelJson<ServiceTicket>(`${B}/orders/${id}/ticket?variant=${variant}`);
}
