/**
 * Client-side guest extra-services API (GUEST-FOLIO-EXTRA-SERVICES-CLOSURE).
 * Calls the same-origin hotel BFF proxy under `/guest-services`. The backend is
 * the single source of truth for all money math, tax, currency and idempotency —
 * these helpers never compute a price or a balance (previews are cosmetic).
 */
import { hotelJson } from "./hotelFetch";
import type {
  GuestExtraService,
  GuestFolioDirectoryRow,
  GuestServiceLine,
  GuestServicePostingResult,
  PaginatedResponse,
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

const B = "/guest-services";

// --- Catalog ("Services & Prices") ------------------------------------------

export interface CatalogListParams {
  /** Filter by active flag; omit for both. */
  is_active?: boolean;
}

export function listCatalog(
  params?: CatalogListParams,
): Promise<GuestExtraService[]> {
  // The catalog list endpoint is NOT paginated (returns a plain array).
  return hotelJson<GuestExtraService[]>(`${B}/catalog/${toQuery(params)}`);
}

export function getCatalogItem(id: number): Promise<GuestExtraService> {
  return hotelJson<GuestExtraService>(`${B}/catalog/${id}/`);
}

/** Fields the client sends when creating/editing a catalog entry. `is_active` is
 * READ-ONLY server-side (managed by the deactivate/activate routes). */
export interface CatalogBody {
  name: string;
  category: string;
  description?: string;
  unit_price: string;
  currency: string;
  tax_rate: string;
  pricing_mode: string;
  display_order: number;
}

export function createCatalogItem(
  body: CatalogBody,
): Promise<GuestExtraService> {
  return hotelJson<GuestExtraService>(`${B}/catalog/`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateCatalogItem(
  id: number,
  body: Partial<CatalogBody>,
): Promise<GuestExtraService> {
  return hotelJson<GuestExtraService>(`${B}/catalog/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deactivateCatalogItem(id: number): Promise<GuestExtraService> {
  return hotelJson<GuestExtraService>(`${B}/catalog/${id}/deactivate/`, {
    method: "POST",
    body: "{}",
  });
}

export function activateCatalogItem(id: number): Promise<GuestExtraService> {
  return hotelJson<GuestExtraService>(`${B}/catalog/${id}/activate/`, {
    method: "POST",
    body: "{}",
  });
}

// --- Folio directory (in-house stays) ---------------------------------------

export interface FolioDirectoryParams {
  page?: number;
}

export function listFolioDirectory(
  params?: FolioDirectoryParams,
): Promise<PaginatedResponse<GuestFolioDirectoryRow>> {
  return hotelJson<PaginatedResponse<GuestFolioDirectoryRow>>(
    `${B}/folio-directory/${toQuery(params)}`,
  );
}

// --- Add a service to a stay's folio ----------------------------------------

export interface AddGuestServiceBody {
  service: number;
  quantity: string;
  /** VARIABLE pricing only, and only with finance.charge_create — else ignored. */
  unit_price_override?: string;
  /** Mandatory when an override is actually applied. */
  reason?: string;
  idempotency_key: string;
}

export function addGuestService(
  stayId: number,
  body: AddGuestServiceBody,
): Promise<GuestServicePostingResult> {
  return hotelJson<GuestServicePostingResult>(
    `${B}/stays/${stayId}/add/`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

// --- Per-stay service line items (money-safe) -------------------------------

export function listStayServiceLines(
  stayId: number,
): Promise<GuestServiceLine[]> {
  return hotelJson<GuestServiceLine[]>(`${B}/stays/${stayId}/service-lines/`);
}
