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
    await screen.findByRole("button", { name: "More" });
    expect(
      screen.queryByRole("button", { name: "Mark delivered" }),
    ).not.toBeInTheDocument();
  });
});

describe("OrdersTab — financial permission gating on the surface", () => {
  async function openMore() {
    fireEvent.click(await screen.findByRole("button", { name: "More" }));
  }

  it("offers Direct payment only with service_orders.settle_direct", async () => {
    vi.mocked(listServiceOrders).mockResolvedValue(
      page([listItem({ status: "delivered", settlement: "unsettled" })]),
    );
    access.set(["service_orders.view"]); // no settle_direct
    const { unmount } = renderWithProviders(<OrdersTab />);
    await openMore();
    expect(
      screen.queryByRole("menuitem", { name: "Direct payment" }),
    ).not.toBeInTheDocument();
    unmount();

    access.set(["service_orders.view", "service_orders.settle_direct"]);
    renderWithProviders(<OrdersTab />);
    await openMore();
    expect(
      await screen.findByRole("menuitem", { name: "Direct payment" }),
    ).toBeInTheDocument();
  });

  it("offers Return / exchange only with finance.refund", async () => {
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
    await openMore();
    expect(
      screen.queryByRole("menuitem", { name: "Return / exchange" }),
    ).not.toBeInTheDocument();
    unmount();

    access.set(["service_orders.view", "finance.refund"]);
    renderWithProviders(<OrdersTab />);
    await openMore();
    expect(
      await screen.findByRole("menuitem", { name: "Return / exchange" }),
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

  it("3) choosing Direct customer hides room + table (+ stay)", async () => {
    open();
    fireEvent.click(await screen.findByRole("radio", { name: /Direct customer/ }));
    expect(screen.queryByPlaceholderText(RESIDENT_SEARCH)).toBeNull();
    expect(
      screen.queryByRole("switch", { name: /charge to their room/ }),
    ).toBeNull();
    expect(screen.getByLabelText("Customer name")).toBeInTheDocument();
  });

  it("4) item smart-search filters the loaded catalog", async () => {
    vi.mocked(listServiceItems).mockResolvedValue(
      page([
        serviceItem({ id: 1, name: "Espresso" }),
        serviceItem({ id: 2, name: "Latte", code: "LAT", unit_price: "6.00" }),
      ]),
    );
    open();
    expect(await screen.findByRole("button", { name: /Espresso/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Latte/ })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Find an item"), {
      target: { value: "esp" },
    });
    expect(screen.getByRole("button", { name: /Espresso/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Latte/ })).toBeNull();
  });

  it("5) adding an item, stepping quantity, and re-adding merges one line", async () => {
    vi.mocked(listServiceItems).mockResolvedValue(
      page([serviceItem({ id: 1, name: "Espresso" })]),
    );
    open();
    fireEvent.click(await screen.findByRole("button", { name: /Espresso/ }));
    expect(
      screen.getAllByRole("button", { name: "Increase quantity" }),
    ).toHaveLength(1);

    // Step the quantity up, then re-add the SAME item — it merges (still one line).
    fireEvent.click(screen.getByRole("button", { name: "Increase quantity" }));
    fireEvent.click(screen.getByRole("button", { name: /Espresso/ }));
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
    fireEvent.click(await screen.findByRole("button", { name: /Espresso/ }));
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
    fireEvent.click(await screen.findByRole("button", { name: /Espresso/ }));
    // Cash is the default method; enter more than the $8.00 total.
    fireEvent.change(screen.getByLabelText("Amount received"), {
      target: { value: "20" },
    });
    expect(screen.getAllByText("$12.00").length).toBeGreaterThanOrEqual(1);
  });

  it("8) 'On room account' is hidden until a stay is linked", async () => {
    vi.mocked(listCurrentResidents).mockResolvedValue(page([stay()]));
    open();
    // Default room source, no stay linked yet.
    expect(screen.queryByRole("radio", { name: /On room account/ })).toBeNull();

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
    fireEvent.click(await screen.findByRole("button", { name: /Espresso/ }));
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
