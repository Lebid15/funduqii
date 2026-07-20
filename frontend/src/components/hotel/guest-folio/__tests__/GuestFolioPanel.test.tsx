import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * GUEST-FOLIO-EXTRA-SERVICES-CLOSURE — the operational guest-folio surface.
 *
 * Covers the owner access matrix (service_orders.create-only / services.view-only
 * / finance.view-only / none), the add-service flow (fixed + variable + 409 toast
 * + double-click prevention), the view-services + charge-level Void flow (voided
 * line rendered, void calls the EXISTING finance voidCharge + refetches, NO
 * payment/settle tools), and catalog list/create/update/deactivate + validation +
 * read-only + no-delete.
 */

const nav = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn(), tab: "" }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(nav.tab ? `tab=${nav.tab}` : ""),
  usePathname: () => "/hotel/guest-folio",
  useRouter: () => ({
    replace: nav.replace,
    push: nav.push,
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

const access = vi.hoisted(() => {
  let permissions = new Set<string>();
  let isManager = false;
  let loading = false;
  return {
    set(codes: string[], opts: { isManager?: boolean; loading?: boolean } = {}) {
      permissions = new Set(codes);
      isManager = opts.isManager ?? false;
      loading = opts.loading ?? false;
    },
    hook() {
      return {
        loading,
        isManager,
        permissions,
        can: (...codes: string[]) =>
          isManager || codes.some((code) => permissions.has(code)),
        refresh: () => {},
      };
    },
  };
});

vi.mock("@/lib/session/HotelAccessContext", () => ({
  useHotelAccess: () => access.hook(),
}));

vi.mock("@/lib/api/guestServices", () => ({
  listCatalog: vi.fn(),
  getCatalogItem: vi.fn(),
  createCatalogItem: vi.fn(),
  updateCatalogItem: vi.fn(),
  deactivateCatalogItem: vi.fn(),
  activateCatalogItem: vi.fn(),
  listFolioDirectory: vi.fn(),
  addGuestService: vi.fn(),
  listStayServiceLines: vi.fn(),
}));

vi.mock("@/lib/api/finance", () => ({ voidCharge: vi.fn() }));

import {
  addGuestService,
  createCatalogItem,
  deactivateCatalogItem,
  listCatalog,
  listFolioDirectory,
  listStayServiceLines,
  updateCatalogItem,
} from "@/lib/api/guestServices";
import { voidCharge } from "@/lib/api/finance";
import {
  hotelNavItems,
  visibleHotelNavItems,
} from "@/components/layout/hotelNav";
import { requiredPermissionsFor } from "@/lib/session/hotelRouteAccess";
import type { Dictionary } from "@/lib/i18n/dictionaries";
import type {
  GuestExtraService,
  GuestFolioDirectoryRow,
  GuestServiceLine,
  PaginatedResponse,
} from "@/lib/api/types";
import en from "@/lib/i18n/dictionaries/en.json";
import ar from "@/lib/i18n/dictionaries/ar.json";
import tr from "@/lib/i18n/dictionaries/tr.json";
import { formatServiceCount } from "@/lib/format";
import { GuestFolioPanel } from "../GuestFolioPanel";
import { renderWithProviders } from "@/test-utils";

const g = en.guestFolio;

function page<T>(results: T[], count = results.length): PaginatedResponse<T> {
  return { count, next: null, previous: null, results };
}

function makeDirRow(
  overrides: Partial<GuestFolioDirectoryRow> = {},
): GuestFolioDirectoryRow {
  return {
    stay_id: 1,
    guest_name: "Ali Hassan",
    room_number: "101",
    room_type_name: "Standard",
    floor_name: "Ground",
    floor_number: "0",
    check_in_date: "2026-07-18",
    check_out_date: "2026-07-22",
    folio_status: "open",
    service_count: 2,
    ...overrides,
  };
}

/** The finance-visible variant (server ADDS the four money keys). */
function withMoney(row: GuestFolioDirectoryRow): GuestFolioDirectoryRow {
  return {
    ...row,
    service_total: "150.00",
    balance: "150.00",
    total_payments: "0.00",
    currency: "USD",
  };
}

function makeCatalogItem(
  overrides: Partial<GuestExtraService> = {},
): GuestExtraService {
  return {
    id: 10,
    name: "Ironing",
    category: "laundry",
    description: "",
    unit_price: "20.00",
    currency: "USD",
    tax_rate: "15.00",
    pricing_mode: "fixed",
    is_active: true,
    display_order: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeLine(overrides: Partial<GuestServiceLine> = {}): GuestServiceLine {
  return {
    id: 500,
    source: "guest_extra_service",
    description: "Laundry",
    service_name_snapshot: "Laundry",
    quantity: "1.00",
    unit_amount: "20.00",
    tax_rate: "15.00",
    tax_amount: "3.00",
    total_amount: "23.00",
    currency: "USD",
    created_by: "Front Desk",
    created_at: "2026-07-19T08:00:00Z",
    status: "posted",
    void_reason: null,
    voided_by: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.tab = "";
  access.set([]);
  vi.mocked(listFolioDirectory).mockResolvedValue(page<GuestFolioDirectoryRow>([]));
  vi.mocked(listCatalog).mockResolvedValue([]);
  vi.mocked(listStayServiceLines).mockResolvedValue([]);
  // Deterministic idempotency key for the add flow (jsdom may lack randomUUID).
  if (!globalThis.crypto || typeof globalThis.crypto.randomUUID !== "function") {
    // @ts-expect-error test shim
    globalThis.crypto = { randomUUID: () => "test-uuid-0000" };
  }
});

// --------------------------------------------------------------------------- //
// Access matrix (owner #7)                                                     //
// --------------------------------------------------------------------------- //

describe("access matrix", () => {
  it("(a) service_orders.create only: cards + add, NO money, NO catalog tab", async () => {
    access.set(["service_orders.create"]);
    vi.mocked(listFolioDirectory).mockResolvedValue(page([makeDirRow()]));
    renderWithProviders(<GuestFolioPanel />);

    await screen.findByText("Ali Hassan");
    // Money is OMITTED server-side -> the "hidden" affordance, never a zero.
    expect(screen.getByText(g.card.detailsHidden)).toBeInTheDocument();
    expect(screen.queryByText(/150/)).toBeNull();
    expect(screen.queryByText(/\$/)).toBeNull();
    // Can add a service.
    expect(
      screen.getByRole("button", { name: g.card.addService }),
    ).toBeInTheDocument();
    // The catalog ("Services & prices") tab is NOT reachable (needs services.view).
    expect(screen.queryByRole("tab", { name: g.tabs.catalog })).toBeNull();
    expect(screen.getByRole("tab", { name: g.tabs.folio })).toBeInTheDocument();
  });

  it("(a) service_orders.create only: no variable pricing override control", async () => {
    access.set(["service_orders.create"]);
    vi.mocked(listFolioDirectory).mockResolvedValue(page([makeDirRow()]));
    vi.mocked(listCatalog).mockResolvedValue([
      makeCatalogItem({ id: 11, name: "Damage", pricing_mode: "variable" }),
    ]);
    renderWithProviders(<GuestFolioPanel />);

    fireEvent.click(await screen.findByRole("button", { name: g.card.addService }));
    // Pick the variable service, then confirm NO override switch is offered.
    const select = await screen.findByLabelText(g.addModal.service);
    fireEvent.change(select, { target: { value: "11" } });
    expect(screen.queryByText(g.addModal.overrideLabel)).toBeNull();
  });

  it("(c) finance.view only: money shown, NO add button, NO catalog tab", async () => {
    access.set(["finance.view"]);
    vi.mocked(listFolioDirectory).mockResolvedValue(
      page([withMoney(makeDirRow())]),
    );
    renderWithProviders(<GuestFolioPanel />);

    await screen.findByText("Ali Hassan");
    expect(screen.getAllByText(/\$150\.00/).length).toBeGreaterThan(0);
    expect(screen.queryByText(g.card.detailsHidden)).toBeNull();
    // Cannot add a service; the primary action is "View services" instead.
    expect(screen.queryByRole("button", { name: g.card.addService })).toBeNull();
    expect(
      screen.getByRole("button", { name: g.card.viewServices }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: g.tabs.catalog })).toBeNull();
  });

  it("(b) services.view only: catalog is read-only (no create/edit/deactivate)", async () => {
    access.set(["services.view"]);
    nav.tab = "catalog";
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    renderWithProviders(<GuestFolioPanel />);

    await screen.findByText("Ironing");
    expect(screen.queryByRole("button", { name: g.catalog.create })).toBeNull();
    expect(screen.queryByRole("button", { name: en.common.edit })).toBeNull();
    expect(
      screen.queryByRole("button", { name: g.catalog.deactivate }),
    ).toBeNull();
    // Deactivate-not-delete: no delete affordance anywhere.
    expect(screen.queryByRole("button", { name: en.common.delete })).toBeNull();
  });

  it("(d) none of the three: nav link hidden + route access denies", () => {
    const t = en as unknown as Dictionary;
    const noAccess = {
      loading: false,
      isManager: false,
      permissions: new Set<string>(["rooms.view"]),
      can: (...codes: string[]) => codes.some((c) => new Set(["rooms.view"]).has(c)),
      refresh: () => {},
    };
    const visible = visibleHotelNavItems(hotelNavItems(t), noAccess);
    expect(visible.some((item) => item.href === "/hotel/guest-folio")).toBe(false);
    // The route requires ANY of the three codes.
    expect(requiredPermissionsFor("/hotel/guest-folio")).toEqual([
      "service_orders.create",
      "services.view",
      "finance.view",
    ]);
  });

  it("(d) none of the three: the panel renders access-denied", async () => {
    access.set(["rooms.view"]);
    renderWithProviders(<GuestFolioPanel />);
    await screen.findByText(en.staff.accessDenied.title);
  });
});

// --------------------------------------------------------------------------- //
// Add-service flow                                                             //
// --------------------------------------------------------------------------- //

describe("add service", () => {
  async function openAddModal() {
    access.set(["service_orders.create", "finance.charge_create"]);
    vi.mocked(listFolioDirectory).mockResolvedValue(page([makeDirRow()]));
    renderWithProviders(<GuestFolioPanel />);
    fireEvent.click(await screen.findByRole("button", { name: g.card.addService }));
    await screen.findByLabelText(g.addModal.service);
  }

  it("posts a FIXED service (no override) with an idempotency key", async () => {
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    vi.mocked(addGuestService).mockResolvedValue({} as never);
    await openAddModal();

    fireEvent.change(screen.getByLabelText(g.addModal.service), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: g.addModal.submit }));

    await waitFor(() => expect(addGuestService).toHaveBeenCalledTimes(1));
    const [stayId, body] = vi.mocked(addGuestService).mock.calls[0];
    expect(stayId).toBe(1);
    expect(body.service).toBe(10);
    expect(body.idempotency_key).toBeTruthy();
    expect(body.unit_price_override).toBeUndefined();
    expect(body.reason).toBeUndefined();
  });

  it("posts a VARIABLE override with a reason (finance.charge_create)", async () => {
    vi.mocked(listCatalog).mockResolvedValue([
      makeCatalogItem({ id: 11, name: "Damage", pricing_mode: "variable" }),
    ]);
    vi.mocked(addGuestService).mockResolvedValue({} as never);
    await openAddModal();

    fireEvent.change(screen.getByLabelText(g.addModal.service), {
      target: { value: "11" },
    });
    // The override switch is offered for a variable item + finance.charge_create.
    fireEvent.click(screen.getByLabelText(g.addModal.overrideLabel));
    fireEvent.change(screen.getByLabelText(g.addModal.unitPrice), {
      target: { value: "45" },
    });
    fireEvent.change(screen.getByLabelText(g.addModal.reason), {
      target: { value: "Broken lamp" },
    });
    fireEvent.click(screen.getByRole("button", { name: g.addModal.submit }));

    await waitFor(() => expect(addGuestService).toHaveBeenCalledTimes(1));
    const body = vi.mocked(addGuestService).mock.calls[0][1];
    expect(body.unit_price_override).toBe("45");
    expect(body.reason).toBe("Broken lamp");
  });

  it("surfaces a 409 idempotency conflict as a translated error", async () => {
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    vi.mocked(addGuestService).mockRejectedValue({
      status: 409,
      code: "idempotency_key_conflict",
      message: "x",
    });
    await openAddModal();

    fireEvent.change(screen.getByLabelText(g.addModal.service), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: g.addModal.submit }));

    await screen.findByText(g.errors.idempotencyConflict);
  });

  /**
   * A4 (financial): the key used to be minted INSIDE submit, so every attempt got
   * a new one — which defeats the backend's idempotency protection entirely. The
   * dangerous case is not the double-click (the `busy` guard covers that) but a
   * NETWORK-FAILURE RETRY: the request commits, the response is lost, the user
   * clicks again. With a fresh key that is a DUPLICATE CHARGE on a guest's folio.
   */
  it("REPLAYS the same idempotency_key after a failed submit (A4)", async () => {
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    vi.mocked(addGuestService)
      // Attempt 1: the response never arrives (may or may not have committed).
      .mockRejectedValueOnce({ status: 503, code: "unavailable", message: "x" })
      .mockResolvedValueOnce({} as never);
    await openAddModal();

    fireEvent.change(screen.getByLabelText(g.addModal.service), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: g.addModal.submit }));
    await waitFor(() => expect(addGuestService).toHaveBeenCalledTimes(1));

    // The user retries the SAME service/quantity.
    fireEvent.click(screen.getByRole("button", { name: g.addModal.submit }));
    await waitFor(() => expect(addGuestService).toHaveBeenCalledTimes(2));

    const first = vi.mocked(addGuestService).mock.calls[0][1].idempotency_key;
    const second = vi.mocked(addGuestService).mock.calls[1][1].idempotency_key;
    expect(first).toBeTruthy();
    // The retry must be a REPLAY, so the backend can collapse it.
    expect(second).toBe(first);
  });

  it("mints a FRESH key for the next add attempt after a success", async () => {
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    vi.mocked(addGuestService).mockResolvedValue({} as never);
    await openAddModal();

    fireEvent.change(screen.getByLabelText(g.addModal.service), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: g.addModal.submit }));
    await waitFor(() => expect(addGuestService).toHaveBeenCalledTimes(1));
    const firstKey = vi.mocked(addGuestService).mock.calls[0][1].idempotency_key;

    // Re-open for a genuinely NEW posting.
    fireEvent.click(await screen.findByRole("button", { name: g.card.addService }));
    fireEvent.change(await screen.findByLabelText(g.addModal.service), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: g.addModal.submit }));
    await waitFor(() => expect(addGuestService).toHaveBeenCalledTimes(2));

    expect(vi.mocked(addGuestService).mock.calls[1][1].idempotency_key).not.toBe(
      firstKey,
    );
  });

  it("asks the picker for ACTIVE services only", async () => {
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    await openAddModal();
    // A deactivated service is refused server-side — never offer it.
    expect(listCatalog).toHaveBeenCalledWith({ is_active: true });
  });

  it("refetches the directory after a SUCCESSFUL add", async () => {
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    vi.mocked(addGuestService).mockResolvedValue({} as never);
    await openAddModal();
    const before = vi.mocked(listFolioDirectory).mock.calls.length;

    fireEvent.change(screen.getByLabelText(g.addModal.service), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("button", { name: g.addModal.submit }));

    await waitFor(() => expect(addGuestService).toHaveBeenCalledTimes(1));
    // The card's service count / totals are now stale — the list must reload.
    await waitFor(() =>
      expect(vi.mocked(listFolioDirectory).mock.calls.length).toBeGreaterThan(
        before,
      ),
    );
  });

  /** B4: `.catch(() => setCatalog([]))` used to render a FAILED fetch as "no
   * services in the catalogue" — indistinguishable from a real empty catalogue,
   * with no way to retry. */
  it("distinguishes a catalogue load FAILURE from an empty catalogue (B4)", async () => {
    access.set(["service_orders.create"]);
    vi.mocked(listFolioDirectory).mockResolvedValue(page([makeDirRow()]));
    vi.mocked(listCatalog).mockRejectedValue({
      status: 500,
      code: "server_error",
      message: "boom",
    });
    renderWithProviders(<GuestFolioPanel />);
    fireEvent.click(await screen.findByRole("button", { name: g.card.addService }));

    await screen.findByText(g.addModal.catalogFailed);
    expect(screen.queryByText(g.addModal.noCatalog)).toBeNull();
    // Nothing is postable while the catalogue is unavailable.
    expect(screen.getByRole("button", { name: g.addModal.submit })).toBeDisabled();

    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    fireEvent.click(screen.getByRole("button", { name: en.common.retry }));
    await screen.findByLabelText(g.addModal.service);
    expect(screen.queryByText(g.addModal.catalogFailed)).toBeNull();
  });

  it("keeps submit disabled while the catalogue is genuinely empty", async () => {
    vi.mocked(listCatalog).mockResolvedValue([]);
    await openAddModal();
    expect(screen.getByText(g.addModal.noCatalog)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: g.addModal.submit })).toBeDisabled();
  });

  it("explains WHY the price is read-only for a fixed service (C2)", async () => {
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    await openAddModal();
    fireEvent.change(screen.getByLabelText(g.addModal.service), {
      target: { value: "10" },
    });
    expect(screen.getByText(g.addModal.priceFixedHint)).toBeInTheDocument();
  });

  it("prevents a double-click from posting twice", async () => {
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    // Never resolves -> the button stays busy/disabled after the first click.
    vi.mocked(addGuestService).mockReturnValue(new Promise(() => {}) as never);
    await openAddModal();

    fireEvent.change(screen.getByLabelText(g.addModal.service), {
      target: { value: "10" },
    });
    const submit = screen.getByRole("button", { name: g.addModal.submit });
    fireEvent.click(submit);
    fireEvent.click(submit);
    await waitFor(() => expect(addGuestService).toHaveBeenCalledTimes(1));
  });
});

// --------------------------------------------------------------------------- //
// B1 — SERVER-side directory search                                            //
// --------------------------------------------------------------------------- //

describe("directory search (B1)", () => {
  async function renderDirectory(rows = [makeDirRow()]) {
    access.set(["service_orders.create"]);
    vi.mocked(listFolioDirectory).mockResolvedValue(page(rows));
    renderWithProviders(<GuestFolioPanel />);
    await screen.findByText(rows[0].guest_name);
    vi.mocked(listFolioDirectory).mockClear();
    return screen.getByLabelText(en.common.search);
  }

  it("sends the term to the SERVER and resets to page 1", async () => {
    const input = await renderDirectory();
    fireEvent.change(input, { target: { value: "ahmed" } });

    // Client-side filtering could only ever search the CURRENT page, so a guest
    // on page 3 was unfindable from page 1.
    await waitFor(
      () =>
        expect(listFolioDirectory).toHaveBeenCalledWith({
          page: 1,
          search: "ahmed",
        }),
      { timeout: 3000 },
    );
  });

  it("debounces a burst of keystrokes into ONE request", async () => {
    const input = await renderDirectory();
    for (const value of ["a", "ah", "ahm", "ahme", "ahmed"]) {
      fireEvent.change(input, { target: { value } });
    }

    await waitFor(
      () =>
        expect(listFolioDirectory).toHaveBeenCalledWith({
          page: 1,
          search: "ahmed",
        }),
      { timeout: 3000 },
    );
    expect(listFolioDirectory).toHaveBeenCalledTimes(1);
  });

  it("omits the param entirely when the box is cleared", async () => {
    const input = await renderDirectory();
    fireEvent.change(input, { target: { value: "ahmed" } });
    await waitFor(() => expect(listFolioDirectory).toHaveBeenCalled(), {
      timeout: 3000,
    });
    vi.mocked(listFolioDirectory).mockClear();

    fireEvent.change(input, { target: { value: "" } });
    await waitFor(
      () =>
        expect(listFolioDirectory).toHaveBeenCalledWith({
          page: 1,
          search: undefined,
        }),
      { timeout: 3000 },
    );
  });

  it("uses a DISTINCT no-matches message, not 'no in-house guests'", async () => {
    const input = await renderDirectory();
    vi.mocked(listFolioDirectory).mockResolvedValue(
      page<GuestFolioDirectoryRow>([], 0),
    );
    fireEvent.change(input, { target: { value: "zzzz" } });

    await screen.findByText(g.noMatches, undefined, { timeout: 3000 });
    // "No in-house guests" would be a lie while a filter is active.
    expect(screen.queryByText(g.empty)).toBeNull();
    // The way out stays available.
    expect(input).toBeInTheDocument();
  });

  /**
   * The old trap: filtering CLIENT-side left `page` untouched, so a user who
   * filtered while on page 3 saw zero visible rows AND lost the Pagination
   * controls (it was rendered inside the non-empty branch). Server-side search
   * resets to page 1, so the filtered set is always entered from its first page.
   */
  it("resets to page 1 when a search starts, so no one is stranded on page N", async () => {
    access.set(["service_orders.create"]);
    vi.mocked(listFolioDirectory).mockResolvedValue(page([makeDirRow()], 60));
    renderWithProviders(<GuestFolioPanel />);
    await screen.findByText("Ali Hassan");

    fireEvent.click(screen.getByRole("button", { name: en.pagination.next }));
    await waitFor(() =>
      expect(listFolioDirectory).toHaveBeenCalledWith({
        page: 2,
        search: undefined,
      }),
    );
    vi.mocked(listFolioDirectory).mockClear();

    fireEvent.change(screen.getByLabelText(en.common.search), {
      target: { value: "ahmed" },
    });
    await waitFor(
      () =>
        expect(listFolioDirectory).toHaveBeenCalledWith({
          page: 1,
          search: "ahmed",
        }),
      { timeout: 3000 },
    );
  });

  it("keeps Pagination mounted for a MULTI-page filtered result", async () => {
    const input = await renderDirectory();
    vi.mocked(listFolioDirectory).mockResolvedValue(page([makeDirRow()], 60));
    fireEvent.change(input, { target: { value: "ali" } });

    await waitFor(() => expect(listFolioDirectory).toHaveBeenCalled(), {
      timeout: 3000,
    });
    // Pagination is driven by the RESULT SET, not by "this render has rows".
    expect(
      await screen.findByRole("button", { name: en.pagination.next }),
    ).toBeInTheDocument();
  });

  it("still says 'no in-house guests' for a genuinely empty, UNFILTERED list", async () => {
    access.set(["service_orders.create"]);
    vi.mocked(listFolioDirectory).mockResolvedValue(
      page<GuestFolioDirectoryRow>([], 0),
    );
    renderWithProviders(<GuestFolioPanel />);

    await screen.findByText(g.empty);
    expect(screen.queryByText(g.noMatches)).toBeNull();
    expect(screen.queryByRole("button", { name: en.pagination.next })).toBeNull();
  });

  /** B8: the announcement used to recompute on EVERY keystroke, firing five
   * consecutive polite announcements while typing "ahmed". */
  it("debounces the aria-live announcement while typing (B8)", async () => {
    const input = await renderDirectory();
    const live = screen.getByTestId("gf-results-announce");
    const settled = live.textContent;

    for (const value of ["a", "ah", "ahm", "ahme"]) {
      fireEvent.change(input, { target: { value } });
    }
    // Nothing announced mid-burst — the previous text is left in place.
    expect(live.textContent).toBe(settled);

    fireEvent.change(input, { target: { value: "ahmed" } });
    await waitFor(() => expect(listFolioDirectory).toHaveBeenCalled(), {
      timeout: 3000,
    });
    await waitFor(
      () => expect(live.textContent).toBe(en.operations.resultsCount.replace("{count}", "1")),
      { timeout: 3000 },
    );
  });
});

// --------------------------------------------------------------------------- //
// B7 — service-count pluralisation                                             //
// --------------------------------------------------------------------------- //

describe("service count pluralisation (B7)", () => {
  it("renders a SINGULAR badge at 1 and a plural badge beyond", async () => {
    access.set(["service_orders.create"]);
    vi.mocked(listFolioDirectory).mockResolvedValue(
      page([
        makeDirRow({ stay_id: 1, guest_name: "One", room_number: "101", service_count: 1 }),
        makeDirRow({ stay_id: 2, guest_name: "Two", room_number: "102", service_count: 2 }),
        makeDirRow({ stay_id: 3, guest_name: "None", room_number: "103", service_count: 0 }),
        makeDirRow({ stay_id: 4, guest_name: "Lots", room_number: "104", service_count: 12 }),
      ]),
    );
    renderWithProviders(<GuestFolioPanel />);
    await screen.findByText("One");

    // Was "1 services" before the fix.
    expect(screen.getByText(g.card.serviceCount.one)).toBeInTheDocument();
    expect(screen.getByText(g.card.serviceCount.two)).toBeInTheDocument();
    expect(screen.getByText(g.card.serviceCount.zero)).toBeInTheDocument();
    expect(screen.getByText("12 services")).toBeInTheDocument();
  });

  it("selects the right ARABIC form for 1 / 2 / 3-10 / 11+", () => {
    const d = ar as unknown as Dictionary;
    const c = d.guestFolio.card.serviceCount;
    // Arabic needs خدمة / خدمتان / خدمات / خدمة — "{count} خدمات" was wrong at
    // 1, 2 and 11+.
    expect(formatServiceCount(0, d, "ar")).toBe(c.zero);
    expect(formatServiceCount(1, d, "ar")).toBe(c.one);
    expect(formatServiceCount(2, d, "ar")).toBe(c.two);
    expect(formatServiceCount(5, d, "ar")).toBe(
      c.few.replace("{count}", new Intl.NumberFormat("ar").format(5)),
    );
    // 11+ goes BACK to the singular noun.
    expect(formatServiceCount(11, d, "ar")).toBe(
      c.many.replace("{count}", new Intl.NumberFormat("ar").format(11)),
    );
    // The 3-10 band is judged on the last two digits (103 behaves like 3).
    expect(formatServiceCount(103, d, "ar")).toBe(
      c.few.replace("{count}", new Intl.NumberFormat("ar").format(103)),
    );
  });

  it("keeps Turkish invariant after a numeral", () => {
    const d = tr as unknown as Dictionary;
    const c = d.guestFolio.card.serviceCount;
    expect(formatServiceCount(1, d, "tr")).toBe(c.one);
    expect(formatServiceCount(9, d, "tr")).toBe(c.few.replace("{count}", "9"));
    expect(formatServiceCount(11, d, "tr")).toBe(c.many.replace("{count}", "11"));
  });
});

// --------------------------------------------------------------------------- //
// B6 — the complete WAI-ARIA tab pattern (implemented locally)                 //
// --------------------------------------------------------------------------- //

describe("tab a11y (B6)", () => {
  beforeEach(() => {
    access.set([], { isManager: true });
    vi.mocked(listFolioDirectory).mockResolvedValue(page([makeDirRow()]));
  });

  it("wires tablist/tab/tabpanel with a roving tabindex", async () => {
    renderWithProviders(<GuestFolioPanel />);

    const tablist = await screen.findByRole("tablist");
    expect(tablist).toHaveAttribute("aria-label", g.tablistLabel);

    const folioTab = screen.getByRole("tab", { name: g.tabs.folio });
    const catalogTab = screen.getByRole("tab", { name: g.tabs.catalog });
    expect(folioTab).toHaveAttribute("aria-selected", "true");
    // Roving tabindex: the whole tablist is ONE tab stop.
    expect(folioTab).toHaveAttribute("tabindex", "0");
    expect(catalogTab).toHaveAttribute("tabindex", "-1");
    // Only the ACTIVE tab's panel is mounted, so only it may claim aria-controls.
    expect(folioTab).toHaveAttribute("aria-controls", "gf-panel-folio");
    expect(catalogTab).not.toHaveAttribute("aria-controls");

    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("id", "gf-panel-folio");
    expect(panel).toHaveAttribute("aria-labelledby", "gf-tab-folio");
  });

  it("moves with ArrowRight in LTR", async () => {
    renderWithProviders(<GuestFolioPanel />);
    const folioTab = await screen.findByRole("tab", { name: g.tabs.folio });

    fireEvent.keyDown(folioTab, { key: "ArrowRight" });
    expect(nav.replace).toHaveBeenCalledWith("/hotel/guest-folio?tab=catalog", {
      scroll: false,
    });
  });

  it("REVERSES the arrows in RTL (Arabic)", async () => {
    renderWithProviders(<GuestFolioPanel />, { locale: "ar" });
    const folioTab = await screen.findByRole("tab", {
      name: ar.guestFolio.tabs.folio,
    });

    // In Arabic the visually-next tab sits to the LEFT.
    fireEvent.keyDown(folioTab, { key: "ArrowLeft" });
    expect(nav.replace).toHaveBeenCalledWith("/hotel/guest-folio?tab=catalog", {
      scroll: false,
    });
  });

  it("supports Home / End", async () => {
    nav.tab = "catalog";
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    renderWithProviders(<GuestFolioPanel />);
    const catalogTab = await screen.findByRole("tab", { name: g.tabs.catalog });

    fireEvent.keyDown(catalogTab, { key: "Home" });
    expect(nav.replace).toHaveBeenCalledWith("/hotel/guest-folio?tab=folio", {
      scroll: false,
    });
  });
});

// --------------------------------------------------------------------------- //
// View services + charge-level Void                                            //
// --------------------------------------------------------------------------- //

describe("view services + void", () => {
  async function openViewModal() {
    // Manager: can add (so View sits in the More menu) AND can void.
    access.set([], { isManager: true });
    vi.mocked(listFolioDirectory).mockResolvedValue(page([makeDirRow()]));
    renderWithProviders(<GuestFolioPanel />);
    await screen.findByText("Ali Hassan");
    fireEvent.click(screen.getByRole("button", { name: g.card.more }));
    fireEvent.click(
      await screen.findByRole("menuitem", { name: g.card.viewServices }),
    );
  }

  it("renders posted + voided lines and offers NO payment/settle tools", async () => {
    vi.mocked(listStayServiceLines).mockResolvedValue([
      makeLine(),
      makeLine({
        id: 501,
        status: "voided",
        void_reason: "Guest disputed",
        voided_by: "Manager",
      }),
    ]);
    await openViewModal();

    await screen.findByText(g.viewModal.title);
    expect(screen.getByText(g.viewModal.statusPosted)).toBeInTheDocument();
    expect(screen.getByText(g.viewModal.statusVoided)).toBeInTheDocument();
    expect(screen.getByText(/Guest disputed/)).toBeInTheDocument();
    expect(screen.getByText(/Manager/)).toBeInTheDocument();
    // Money-safe operational surface: no record-payment / settle / refund /
    // invoice affordance anywhere.
    expect(
      screen.queryByRole("button", { name: /settle|refund|payment|invoice/i }),
    ).toBeNull();
  });

  it("voids a posted line via the EXISTING finance voidCharge, then refetches", async () => {
    vi.mocked(listStayServiceLines).mockResolvedValue([makeLine()]);
    vi.mocked(voidCharge).mockResolvedValue({} as never);
    await openViewModal();

    await screen.findByText(g.viewModal.title);
    const initialCalls = vi.mocked(listStayServiceLines).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: g.viewModal.void }));

    const dialog = await screen.findByRole("dialog", {
      name: g.viewModal.voidTitle,
    });
    fireEvent.change(within(dialog).getByLabelText(en.finance.void.reason), {
      target: { value: "Wrong charge" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: g.viewModal.void }),
    );

    await waitFor(() => expect(voidCharge).toHaveBeenCalledTimes(1));
    expect(vi.mocked(voidCharge).mock.calls[0][0]).toBe(500);
    expect(vi.mocked(voidCharge).mock.calls[0][1]).toBe("Wrong charge");
    // Refetch after the void.
    await waitFor(() =>
      expect(vi.mocked(listStayServiceLines).mock.calls.length).toBeGreaterThan(
        initialCalls,
      ),
    );
  });

  /** B9: the VoidDialog restores focus to the Void button, then the reload
   * re-renders the line as voided and that button unmounts — focus fell to
   * document.body while the modal was still open. */
  it("keeps focus INSIDE the modal after a void (B9)", async () => {
    vi.mocked(listStayServiceLines)
      .mockResolvedValueOnce([makeLine()])
      .mockResolvedValue([
        makeLine({ status: "voided", void_reason: "Wrong charge", voided_by: "Manager" }),
      ]);
    vi.mocked(voidCharge).mockResolvedValue({} as never);
    await openViewModal();

    await screen.findByText(g.viewModal.title);
    fireEvent.click(screen.getByRole("button", { name: g.viewModal.void }));
    const dialog = await screen.findByRole("dialog", {
      name: g.viewModal.voidTitle,
    });
    fireEvent.change(within(dialog).getByLabelText(en.finance.void.reason), {
      target: { value: "Wrong charge" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: g.viewModal.void }),
    );

    // The acting button is gone once the line is voided...
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: g.viewModal.void })).toBeNull(),
    );
    // ...so focus must land on the modal's stable anchor, never on <body>.
    await waitFor(() => expect(document.activeElement).not.toBe(document.body));
    expect(document.activeElement).not.toBeNull();
  });

  it("surfaces the variable-price override reason on a line", async () => {
    vi.mocked(listStayServiceLines).mockResolvedValue([
      makeLine({ price_override_reason: "Damaged minibar door" }),
    ]);
    await openViewModal();

    await screen.findByText(g.viewModal.title);
    expect(screen.getByText("Damaged minibar door")).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(g.viewModal.overrideReason)),
    ).toBeInTheDocument();
  });

  it("hides the Void action without finance.charge_void", async () => {
    access.set(["finance.view"]);
    vi.mocked(listFolioDirectory).mockResolvedValue(
      page([withMoney(makeDirRow())]),
    );
    vi.mocked(listStayServiceLines).mockResolvedValue([makeLine()]);
    renderWithProviders(<GuestFolioPanel />);
    await screen.findByText("Ali Hassan");
    // finance.view-only -> View services is the primary action (no add/menu).
    fireEvent.click(screen.getByRole("button", { name: g.card.viewServices }));
    await screen.findByText(g.viewModal.title);
    expect(screen.queryByRole("button", { name: g.viewModal.void })).toBeNull();
  });
});

// --------------------------------------------------------------------------- //
// Catalog ("Services & prices")                                               //
// --------------------------------------------------------------------------- //

describe("catalog", () => {
  beforeEach(() => {
    nav.tab = "catalog";
    access.set([], { isManager: true });
  });

  it("lists catalog items", async () => {
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    renderWithProviders(<GuestFolioPanel />);
    await screen.findByText("Ironing");
    expect(screen.getByText(g.catalog.categories.laundry)).toBeInTheDocument();
  });

  it("creates a catalog item", async () => {
    vi.mocked(listCatalog).mockResolvedValue([]);
    vi.mocked(createCatalogItem).mockResolvedValue(makeCatalogItem() as never);
    renderWithProviders(<GuestFolioPanel />);
    await screen.findByRole("button", { name: g.catalog.create });

    fireEvent.click(screen.getByRole("button", { name: g.catalog.create }));
    await screen.findByRole("dialog", { name: g.catalog.createTitle });
    fireEvent.change(screen.getByLabelText(g.catalog.fields.name), {
      target: { value: "Spa" },
    });
    fireEvent.change(screen.getByLabelText(g.catalog.fields.currency), {
      target: { value: "usd" },
    });
    fireEvent.click(screen.getByRole("button", { name: en.common.save }));

    await waitFor(() => expect(createCatalogItem).toHaveBeenCalledTimes(1));
    const body = vi.mocked(createCatalogItem).mock.calls[0][0];
    expect(body.name).toBe("Spa");
    expect(body.currency).toBe("USD"); // upper-cased client-side
  });

  it("blocks create when the name is empty (client validation)", async () => {
    vi.mocked(listCatalog).mockResolvedValue([]);
    renderWithProviders(<GuestFolioPanel />);
    await screen.findByRole("button", { name: g.catalog.create });

    fireEvent.click(screen.getByRole("button", { name: g.catalog.create }));
    await screen.findByRole("dialog", { name: g.catalog.createTitle });
    fireEvent.click(screen.getByRole("button", { name: en.common.save }));

    await screen.findByText(g.catalog.errors.nameRequired);
    expect(createCatalogItem).not.toHaveBeenCalled();
  });

  it("updates a catalog item", async () => {
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    vi.mocked(updateCatalogItem).mockResolvedValue(makeCatalogItem() as never);
    renderWithProviders(<GuestFolioPanel />);
    await screen.findByText("Ironing");

    fireEvent.click(screen.getByRole("button", { name: en.common.edit }));
    await screen.findByText(g.catalog.editTitle);
    fireEvent.change(screen.getByLabelText(g.catalog.fields.name), {
      target: { value: "Laundry Plus" },
    });
    fireEvent.click(screen.getByRole("button", { name: en.common.save }));

    await waitFor(() => expect(updateCatalogItem).toHaveBeenCalledTimes(1));
    expect(vi.mocked(updateCatalogItem).mock.calls[0][0]).toBe(10);
    expect(vi.mocked(updateCatalogItem).mock.calls[0][1].name).toBe("Laundry Plus");
  });

  it("deactivates (never deletes) a catalog item", async () => {
    vi.mocked(listCatalog).mockResolvedValue([makeCatalogItem()]);
    vi.mocked(deactivateCatalogItem).mockResolvedValue(
      makeCatalogItem({ is_active: false }) as never,
    );
    renderWithProviders(<GuestFolioPanel />);
    await screen.findByText("Ironing");

    // No delete affordance exists at all.
    expect(screen.queryByRole("button", { name: en.common.delete })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: g.catalog.deactivate }));
    await waitFor(() => expect(deactivateCatalogItem).toHaveBeenCalledWith(10));
  });
});
