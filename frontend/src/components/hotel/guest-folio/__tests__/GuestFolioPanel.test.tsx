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
