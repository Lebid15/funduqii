import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * OrdersTab — PR #55 owner-approved focused coverage (C5): the VISIBLE order
 * cycle (new → delivered) and the FINANCIAL permission gating on the surface
 * (direct payment → service_orders.settle_direct; return/exchange →
 * finance.refund), plus the C4 direct-customer create source. Money safety is
 * enforced server-side; this proves the surface offers the right actions to the
 * right roles and shapes.
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
  listServiceItems,
  listServiceOrders,
  listTables,
  setServiceOrderStatus,
} from "@/lib/api/services";
import { getSettings } from "@/lib/api/hotel";
import { listCurrentResidents } from "@/lib/api/stays";
import type { PaginatedResponse, ServiceOrderListItem } from "@/lib/api/types";
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

describe("OrderCreateModal — direct customer source (C4)", () => {
  it("a direct order hides the stay/table fields and keeps a customer name", async () => {
    renderWithProviders(
      <OrderCreateModal open onClose={() => {}} onSaved={() => {}} />,
    );
    // Default room order exposes the stay picker.
    const typeSelect = await screen.findByLabelText("Order type");
    expect(screen.getByLabelText("Stay")).toBeInTheDocument();

    fireEvent.change(typeSelect, { target: { value: "direct" } });

    // A direct (walk-in) order has no stay link and no table — only a name.
    expect(screen.queryByLabelText("Stay")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Table")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Customer name")).toBeInTheDocument();
  });
});
