/**
 * Client-side service catalog + orders API (Phase 9). Calls the same-origin
 * hotel BFF proxy. The backend owns all money math, numbering, the status
 * workflow, and the once-only posting to a folio — these helpers never compute
 * totals or post charges themselves.
 */
import { hotelJson } from "./hotelFetch";
import type {
  PaginatedResponse,
  ServiceCategory,
  ServiceItem,
  ServiceOrder,
  ServiceOrderListItem,
  ServiceTicket,
  ServicesOverview,
} from "./types";

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
  is_active?: string;
  page?: number;
}): Promise<PaginatedResponse<ServiceCategory>> {
  return hotelJson<PaginatedResponse<ServiceCategory>>(
    `${B}/categories${toQuery(params)}`,
  );
}

export type ServiceCategoryBody = Partial<
  Pick<ServiceCategory, "name" | "code" | "description" | "sort_order" | "is_active">
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
  item_type?: string;
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
    | "code"
    | "description"
    | "item_type"
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

// --- Orders ----------------------------------------------------------------------

export interface ServiceOrderListParams {
  search?: string;
  status?: string;
  source?: string;
  stay?: number;
  room?: number;
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
  source?: string;
  stay?: number | null;
  room?: number | null;
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

export function updateServiceOrder(
  id: number,
  body: Partial<ServiceOrderCreateBody>,
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

export function postServiceOrderToFolio(id: number): Promise<ServiceOrder> {
  return hotelJson<ServiceOrder>(`${B}/orders/${id}/post-to-folio`, {
    method: "POST",
    body: "{}",
  });
}

export function getServiceOrderTicket(id: number): Promise<ServiceTicket> {
  return hotelJson<ServiceTicket>(`${B}/orders/${id}/ticket`);
}
