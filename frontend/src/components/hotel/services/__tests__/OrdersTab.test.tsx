import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * OrdersTab — PR #55 owner-approved coverage: the VISIBLE order cycle (new →
 * delivered) and the FINANCIAL permission gating on the surface (direct payment
 * → service_orders.settle_direct; return/exchange → finance.refund), PLUS the
 * rebuilt single-page OrderCreateModal (source cards, item smart-search + qty
 * stepper, payment cards, and the create → deliver → settle money chain). Money
 * safety is enforced server-side; these prove the surface offers the right
 * actions/shapes and fires the chain in order.
 */

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  usePathname: () => "/hotel/services",
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

const access = vi.hoisted(() => {
  let permissions = new Set<string>();
  return {
    set(codes: string[]) {
      permissions = new Set(codes);
    },
    hook() {
      return {
        loading: false,
        isManager: false,
        permissions,
        can: (...codes: string[]) => codes.some((code) => permissions.has(code)),
        refresh: () => {},
      };
    },
  };
});

vi.mock("@/lib/session/HotelAccessContext", () => ({
  useHotelAccess: () => access.hook(),
}));

vi.mock("@/lib/api/services", () => ({
  listServiceOrders: vi.fn(),
  setServiceOrderStatus: vi.fn(),
  listServiceItems: vi.fn(),
  listTables: vi.fn(),
  getServiceOrder: vi.fn(),
  getServiceOrderTicket: vi.fn(),
  createServiceOrder: vi.fn(),
  cancelServiceOrder: vi.fn(),
  cancelServiceOrderItem: vi.fn(),
  postServiceOrderToFolio: vi.fn(),
  returnServiceOrder: vi.fn(),
  settleServiceOrderDirect: vi.fn(),
  mintIdempotencyKey: () => "test-key",
}));
vi.mock("@/lib/api/hotel", () => ({ getSettings: vi.fn() }));
vi.mock("@/lib/api/stays", () => ({ listCurrentResidents: vi.fn() }));
vi.mock("@/lib/api/finance", () => ({ getReceipt: vi.fn() }));

import {
  createServiceOrder,
  listServiceItems,
  listServiceOrders,
  listTables,
  setServiceOrderStatus,
  settleServiceOrderDirect,
} from "@/lib/api/services";
import { getSettings } from "@/lib/api/hotel";
import { listCurrentResidents } from "@/lib/api/stays";
import type {
  PaginatedResponse,
  ServiceItem,
  ServiceOrder,
  ServiceOrderListItem,
  Stay,
} from "@/lib/api/types";
import { OrderCreateModal, OrdersTab } from "../OrdersTab";
import { renderWithProviders } from "@/test-utils";

function page<T>(results: T[], count = results.length): PaginatedResponse<T> {
  return { count, next: null, previous: null, results };
}

function listItem(over: Partial<ServiceOrderListItem> = {}): ServiceOrderListItem {
  return {
    id: 1,
    order_number: "SO-001",
    order_type: "table",
    outlet: "restaurant",
    status: "submitted",
    settlement: "unsettled",
    stay: null,
    room: null,
    room_number: "",
    table: 5,
    table_number: "T005",
    customer_name: "",
    business_date: "2026-07-21",
    currency: "USD",
    ordered_at: "2026-07-21T10:00:00Z",
    requested_delivery_time: null,
    delivered_at: null,
    is_posted: false,
    posted_at: null,
    settled_at: null,
    total: "88.00",
    ...over,
  };
}

function serviceItem(over: Partial<ServiceItem> = {}): ServiceItem {
  return {
    id: 1,
    category: 1,
    category_name: "Drinks",
    outlet: "restaurant",
    name: "Espresso",
    code: "ESP",
    description: "",
    unit_price: "8.00",
    currency: "USD",
    tax_rate: "0",
    is_available: true,
    is_active: true,
    sort_order: 0,
    created_at: "2026-07-21T00:00:00Z",
    updated_at: "2026-07-21T00:00:00Z",
    ...over,
  };
}

function stay(over: Partial<Stay> = {}): Stay {
  return {
    id: 1,
    room: 101,
    room_number: "101",
    primary_guest: 1,
    primary_guest_name: "Jane Doe",
    status: "in_house",
    ...over,
  } as unknown as Stay;
}

function serviceOrder(over: Partial<ServiceOrder> = {}): ServiceOrder {
  return {
    id: 10,
    order_number: "SO-010",
    status: "submitted",
    currency: "USD",
    totals: { subtotal: "8.00", tax_total: "0.00", total: "8.00", currency: "USD" },
    ...over,
  } as unknown as ServiceOrder;
}

/** Placeholder of the resident/room smart-search field (EN). */
const RESIDENT_SEARCH = "Search by room number or guest name…";

beforeEach(() => {
  vi.clearAllMocks();
  access.set(["service_orders.view", "service_orders.status_update"]);
  vi.mocked(listServiceOrders).mockResolvedValue(page([]));
  vi.mocked(listServiceItems).mockResolvedValue(page([]));
  vi.mocked(listTables).mockResolvedValue(page([]));
  vi.mocked(listCurrentResidents).mockResolvedValue(page([]));
  vi.mocked(getSettings).mockResolvedValue({
    default_currency: "USD",
    restaurant_enabled: true,
    cafe_enabled: true,
  } as never);
  vi.mocked(setServiceOrderStatus).mockResolvedValue({} as never);
});

describe("OrdersTab — visible cycle (new → delivered)", () => {
  it("a new order's single primary action delivers it (status=delivered)", async () => {
    vi.mocked(listServiceOrders).mockResolvedValue(
      page([listItem({ status: "submitted" })]),
    );
    renderWithProviders(<OrdersTab />);
    const btn = await screen.findByRole("button", { name: "Mark delivered" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(setServiceOrderStatus).toHaveBeenCalledWith(1, "delivered"),
    );
  });

  it("a delivered order no longer offers Mark delivered", async () => {
    vi.mocked(listServiceOrders).mockResolvedValue(
      page([listItem({ status: "delivered", settlement: "unsettled" })]),
    );
    renderWithProviders(<OrdersTab />);
    // The card always renders Details + Print directly (no "More" menu anymore).
    await screen.findByRole("button", { name: "Details" });
    expect(
      screen.queryByRole("button", { name: "Mark delivered" }),
    ).not.toBeInTheDocument();
  });
});

describe("OrdersTab — direct card actions + financial permission gating", () => {
  it("every action is a DIRECT button — there is no 'More' menu", async () => {
    vi.mocked(listServiceOrders).mockResolvedValue(
      page([listItem({ status: "submitted", settlement: "direct" })]),
    );
    renderWithProviders(<OrdersTab />);
    await screen.findByRole("button", { name: "Details" });
    expect(screen.queryByRole("button", { name: "More" })).not.toBeInTheDocument();
    // A NEW order shows Mark delivered + Details + Print directly.
    expect(screen.getByRole("button", { name: "Mark delivered" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Print" })).toBeInTheDocument();
  });

  it("offers Return / exchange (direct button) only with finance.refund", async () => {
    vi.mocked(listServiceOrders).mockResolvedValue(
      page([
        listItem({
          status: "delivered",
          settlement: "direct",
          settled_at: "2026-07-21T10:05:00Z",
        }),
      ]),
    );
    access.set(["service_orders.view"]); // no finance.refund
    const { unmount } = renderWithProviders(<OrdersTab />);
    await screen.findByRole("button", { name: "Details" });
    expect(
      screen.queryByRole("button", { name: "Return / exchange" }),
    ).not.toBeInTheDocument();
    unmount();

    access.set(["service_orders.view", "finance.refund"]);
    renderWithProviders(<OrdersTab />);
    expect(
      await screen.findByRole("button", { name: "Return / exchange" }),
    ).toBeInTheDocument();
  });

  it("offers Cancel for a NEW order only (not after delivery)", async () => {
    // A delivered order: no Cancel (return/exchange instead).
    vi.mocked(listServiceOrders).mockResolvedValue(
      page([listItem({ status: "delivered", settlement: "direct", settled_at: "2026-07-21T10:05:00Z" })]),
    );
    access.set(["service_orders.view", "finance.refund"]);
    const { unmount } = renderWithProviders(<OrdersTab />);
    await screen.findByRole("button", { name: "Details" });
    expect(screen.queryByRole("button", { name: "Cancel order" })).not.toBeInTheDocument();
    unmount();

    // A NEW settled order: Cancel is offered (with finance.refund for the reversal).
    vi.mocked(listServiceOrders).mockResolvedValue(
      page([listItem({ status: "submitted", settlement: "direct" })]),
    );
    renderWithProviders(<OrdersTab />);
    expect(
      await screen.findByRole("button", { name: "Cancel order" }),
    ).toBeInTheDocument();
  });
});

describe("OrderCreateModal — single-page form (source / items / payment)", () => {
  function open() {
    renderWithProviders(
      <OrderCreateModal open onClose={() => {}} onSaved={() => {}} />,
    );
  }

  it("1) choosing Room shows the resident/stay search only", async () => {
    open();
    fireEvent.click(await screen.findByRole("radio", { name: /Room/ }));
    expect(screen.getByPlaceholderText(RESIDENT_SEARCH)).toBeInTheDocument();
    expect(screen.queryByLabelText("Customer name")).toBeNull();
    expect(
      screen.queryByRole("switch", { name: /charge to their room/ }),
    ).toBeNull();
  });

  it("2) choosing Table shows the 'charge to room' resident-link toggle", async () => {
    open();
    fireEvent.click(await screen.findByRole("radio", { name: /Table/ }));
    expect(
      await screen.findByRole("switch", { name: /charge to their room/ }),
    ).toBeInTheDocument();
    // Resident search stays hidden until the toggle is switched on.
    expect(screen.queryByPlaceholderText(RESIDENT_SEARCH)).toBeNull();
  });

  it("table mode uses a compact select → chip (no tall table list)", async () => {
    vi.mocked(listTables).mockResolvedValue(
      page([
        {
          id: 7,
          outlet: "restaurant",
          number: "7",
          name: "",
          capacity: 4,
          status: "available",
          is_occupied: false,
        } as never,
      ]),
    );
    open();
    fireEvent.click(await screen.findByRole("radio", { name: /Table/ }));
    // A compact ONE-LINE select (labelled "Available tables"), not a list of cards.
    const select = await screen.findByLabelText("Available tables");
    fireEvent.change(select, { target: { value: "7" } });
    // After selecting, the table collapses to a small chip with a Change button.
    expect(await screen.findByRole("button", { name: "Change" })).toBeInTheDocument();
  });

  it("3) choosing Direct customer hides room + table (+ stay)", async () => {
    open();
    fireEvent.click(await screen.findByRole("radio", { name: /Direct customer/ }));
    expect(screen.queryByPlaceholderText(RESIDENT_SEARCH)).toBeNull();
    expect(
      screen.queryByRole("switch", { name: /charge to their room/ }),
    ).toBeNull();
    expect(screen.getByLabelText("Customer name")).toBeInTheDocument();
  });

  it("4) items show only AFTER typing, and the search filters (by outlet)", async () => {
    vi.mocked(listServiceItems).mockResolvedValue(
      page([
        serviceItem({ id: 1, name: "Espresso" }),
        serviceItem({ id: 2, name: "Latte", code: "LAT", unit_price: "6.00" }),
      ]),
    );
    open();
    const box = await screen.findByLabelText("Find an item");
    // Nothing is shown before the user types (owner correction 5).
    expect(screen.queryByRole("button", { name: /Espresso/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Latte/ })).toBeNull();

    fireEvent.change(box, { target: { value: "esp" } });
    expect(await screen.findByRole("button", { name: /Espresso/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Latte/ })).toBeNull();
  });

  // Items appear only after typing (owner correction 5); type, then click the result.
  async function selectItem(label = "Espresso", query = "esp") {
    fireEvent.change(await screen.findByLabelText("Find an item"), {
      target: { value: query },
    });
    fireEvent.click(await screen.findByRole("button", { name: new RegExp(label) }));
  }

  it("5) adding an item, stepping quantity, and re-adding merges one line", async () => {
    vi.mocked(listServiceItems).mockResolvedValue(
      page([serviceItem({ id: 1, name: "Espresso" })]),
    );
    open();
    await selectItem();
    expect(
      screen.getAllByRole("button", { name: "Increase quantity" }),
    ).toHaveLength(1);

    // Step the quantity up, then re-add the SAME item — it merges (still one line).
    // Adding clears the item search (owner correction #7: results hide after each
    // add), so re-type to bring the result back before clicking it again.
    fireEvent.click(screen.getByRole("button", { name: "Increase quantity" }));
    await selectItem();
    expect(
      screen.getAllByRole("button", { name: "Increase quantity" }),
    ).toHaveLength(1);

    const line = screen
      .getByRole("button", { name: "Increase quantity" })
      .closest(".svc-line") as HTMLElement;
    expect(within(line).getByText("3")).toBeInTheDocument();
  });

  it("6) an added item shows its unit price + currency", async () => {
    vi.mocked(listServiceItems).mockResolvedValue(
      page([serviceItem({ id: 1, name: "Espresso", unit_price: "8.00" })]),
    );
    open();
    await selectItem();
    const line = screen
      .getByRole("button", { name: "Increase quantity" })
      .closest(".svc-line") as HTMLElement;
    expect(within(line).getAllByText("$8.00").length).toBeGreaterThanOrEqual(1);
  });

  it("7) cash payment computes and shows the change", async () => {
    vi.mocked(listServiceItems).mockResolvedValue(
      page([serviceItem({ id: 1, name: "Espresso", unit_price: "8.00", tax_rate: "0" })]),
    );
    open();
    await selectItem();
    // Cash is the default method; enter more than the $8.00 total.
    fireEvent.change(screen.getByLabelText("Amount received"), {
      target: { value: "20" },
    });
    expect(screen.getAllByText("$12.00").length).toBeGreaterThanOrEqual(1);
  });

  it("electronic requires the received amount to equal the total", async () => {
    vi.mocked(listServiceItems).mockResolvedValue(
      page([serviceItem({ id: 1, name: "Espresso", unit_price: "8.00", tax_rate: "0" })]),
    );
    open();
    fireEvent.click(await screen.findByRole("radio", { name: /Direct customer/ }));
    await selectItem();
    // Switch to electronic.
    fireEvent.click(screen.getByRole("radio", { name: /Electronic/ }));
    // A mismatched received amount blocks Create…
    fireEvent.change(screen.getByLabelText("Amount received"), { target: { value: "5" } });
    expect(screen.getByRole("button", { name: "Create order" })).toBeDisabled();
    // …matching the total enables it.
    fireEvent.change(screen.getByLabelText("Amount received"), { target: { value: "8" } });
    expect(screen.getByRole("button", { name: "Create order" })).toBeEnabled();
  });

  it("8) 'On room account' is hidden until a stay is linked", async () => {
    vi.mocked(listCurrentResidents).mockResolvedValue(page([stay()]));
    open();
    // Default room source, no stay linked yet.
    expect(screen.queryByRole("radio", { name: /On room account/ })).toBeNull();

    // Rooms show only after a (server-side) search — type, then pick the resident.
    fireEvent.change(await screen.findByPlaceholderText(RESIDENT_SEARCH), {
      target: { value: "jane" },
    });
    fireEvent.click(await screen.findByRole("button", { name: /Jane Doe/ }));
    expect(
      await screen.findByRole("radio", { name: /On room account/ }),
    ).toBeInTheDocument();

    // A direct customer never gets the room-account option.
    fireEvent.click(screen.getByRole("radio", { name: /Direct customer/ }));
    expect(screen.queryByRole("radio", { name: /On room account/ })).toBeNull();
  });

  it("9) Create is disabled while required data is missing", async () => {
    open();
    // Room source, no stay, no items, no cash tendered → cannot create.
    await screen.findByRole("radio", { name: /Room/ });
    expect(screen.getByRole("button", { name: "Create order" })).toBeDisabled();
  });

  it("10) the create form has no 'Mark delivered' button", async () => {
    open();
    await screen.findByRole("radio", { name: /Room/ });
    expect(
      screen.queryByRole("button", { name: "Mark delivered" }),
    ).not.toBeInTheDocument();
  });

  it("a full CASH create fires create → settle and does NOT deliver (order stays NEW)", async () => {
    vi.mocked(listServiceItems).mockResolvedValue(
      page([serviceItem({ id: 1, name: "Espresso", unit_price: "8.00", tax_rate: "0" })]),
    );
    // Official cycle: the order is settled at creation and STAYS submitted (NEW).
    vi.mocked(createServiceOrder).mockResolvedValue(
      serviceOrder({ id: 10, status: "submitted" }),
    );
    vi.mocked(settleServiceOrderDirect).mockResolvedValue(
      serviceOrder({ id: 10, status: "submitted", settlement: "direct" }),
    );

    renderWithProviders(
      <OrderCreateModal open onClose={() => {}} onSaved={() => {}} />,
    );

    // Direct customer — no stay/table required.
    fireEvent.click(await screen.findByRole("radio", { name: /Direct customer/ }));
    await selectItem();
    fireEvent.change(screen.getByLabelText("Amount received"), {
      target: { value: "8" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create order" }));

    await waitFor(() => expect(createServiceOrder).toHaveBeenCalledTimes(1));
    expect(vi.mocked(createServiceOrder).mock.calls[0][0]).toMatchObject({
      order_type: "direct",
      outlet: "restaurant",
    });
    await waitFor(() =>
      expect(settleServiceOrderDirect).toHaveBeenCalledWith(
        10,
        expect.objectContaining({
          method: "cash",
          amount_received: "8",
          settlement_key: "test-key",
        }),
      ),
    );
    // Deliver is NOT part of the create form — it is a later, card-only action.
    expect(setServiceOrderStatus).not.toHaveBeenCalled();
  });
});
