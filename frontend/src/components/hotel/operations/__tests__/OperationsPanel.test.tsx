import { fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * OperationsPanel (WP12 / owner §17 "TABS"). EXACTLY three tabs — Cleaning /
 * Maintenance / Lost & found. The old Overview + Room-board tabs are GONE (their
 * counters moved onto the per-tab stat row). Verifies the WAI-ARIA tab pattern
 * (role=tablist/tab/tabpanel + aria-selected + roving tabIndex), keyboard arrow
 * navigation, `?tab=` deep-linking, the per-tab stat row, and RTL behaviour.
 *
 * The whole operations API + the room/staff/guest feeds + next/navigation + the
 * cosmetic access gate are mocked so the panel renders deterministically.
 */

// --- next/navigation (OperationsPanel reads ?tab=, the tabs use useQuickAction) --
const nav = vi.hoisted(() => {
  const replace = vi.fn();
  const push = vi.fn();
  let params = new URLSearchParams("");
  return {
    replace,
    push,
    setSearch(qs: string) {
      params = new URLSearchParams(qs);
    },
    getSearch() {
      return params;
    },
  };
});

vi.mock("next/navigation", () => ({
  useSearchParams: () => nav.getSearch(),
  usePathname: () => "/hotel/operations",
  useRouter: () => ({
    replace: nav.replace,
    push: nav.push,
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

// --- cosmetic permission gate ------------------------------------------------
const access = vi.hoisted(() => {
  let permissions = new Set<string>();
  let manager = false;
  return {
    set(codes: string[], isManager = false) {
      permissions = new Set(codes);
      manager = isManager;
    },
    hook() {
      return {
        loading: false,
        isManager: manager,
        permissions,
        can: (...codes: string[]) =>
          manager || codes.some((code) => permissions.has(code)),
        refresh: () => {},
      };
    },
  };
});

vi.mock("@/lib/session/HotelAccessContext", () => ({
  useHotelAccess: () => access.hook(),
}));

vi.mock("@/lib/api/operations", () => ({
  getOperationsOverview: vi.fn(),
  listHousekeepingTasks: vi.fn(),
  listArrivalsNotReady: vi.fn(),
  createHousekeepingTask: vi.fn(),
  updateHousekeepingTask: vi.fn(),
  setHousekeepingStatus: vi.fn(),
  assignHousekeepingTask: vi.fn(),
  completeHousekeepingTask: vi.fn(),
  comeBackLaterHousekeepingTask: vi.fn(),
  cancelHousekeepingTask: vi.fn(),
  approveInspection: vi.fn(),
  rejectInspection: vi.fn(),
  listMaintenanceRequests: vi.fn(),
  createMaintenanceRequest: vi.fn(),
  setMaintenanceStatus: vi.fn(),
  assignMaintenanceRequest: vi.fn(),
  resolveMaintenanceRequest: vi.fn(),
  closeMaintenanceRequest: vi.fn(),
  cancelMaintenanceRequest: vi.fn(),
  listLostFoundItems: vi.fn(),
  createLostFoundItem: vi.fn(),
  setLostFoundStatus: vi.fn(),
  claimLostFoundItem: vi.fn(),
  returnLostFoundItem: vi.fn(),
  disposeLostFoundItem: vi.fn(),
  closeLostFoundItem: vi.fn(),
}));

vi.mock("@/lib/api/rooms", () => ({ listRoomOptions: vi.fn() }));
vi.mock("@/lib/api/staff", () => ({ listStaff: vi.fn() }));
vi.mock("@/lib/api/guests", () => ({ listGuests: vi.fn() }));
vi.mock("@/lib/api/stays", () => ({ listCurrentResidents: vi.fn() }));

import {
  getOperationsOverview,
  listArrivalsNotReady,
  listHousekeepingTasks,
  listLostFoundItems,
  listMaintenanceRequests,
} from "@/lib/api/operations";
import { listRoomOptions } from "@/lib/api/rooms";
import { listStaff } from "@/lib/api/staff";
import { listGuests } from "@/lib/api/guests";
import { listCurrentResidents } from "@/lib/api/stays";
import type { PaginatedResponse } from "@/lib/api/types";
import { OperationsPanel } from "../OperationsPanel";
import { makeOverview, renderWithProviders } from "@/test-utils";

function page<T>(results: T[], count = results.length): PaginatedResponse<T> {
  return { count, next: null, previous: null, results };
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.setSearch("");
  access.set([], true); // manager → every cosmetic gate passes
  vi.mocked(listHousekeepingTasks).mockResolvedValue(page([]));
  vi.mocked(listArrivalsNotReady).mockResolvedValue([]);
  vi.mocked(listMaintenanceRequests).mockResolvedValue(page([]));
  vi.mocked(getOperationsOverview).mockResolvedValue(makeOverview());
  vi.mocked(listLostFoundItems).mockResolvedValue(page([]));
  vi.mocked(listRoomOptions).mockResolvedValue(page([]));
  vi.mocked(listStaff).mockResolvedValue(page([]));
  vi.mocked(listGuests).mockResolvedValue(page([]));
  vi.mocked(listCurrentResidents).mockResolvedValue(page([]));
});

describe("OperationsPanel — exactly three tabs", () => {
  it("renders Cleaning / Maintenance / Lost & found and nothing else", async () => {
    renderWithProviders(<OperationsPanel />);
    await screen.findByText("No housekeeping tasks");

    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
    expect(tabs.map((t) => t.textContent)).toEqual([
      "Cleaning",
      "Maintenance",
      "Lost & found",
    ]);
  });

  it("has NO Overview and NO Room-board tab (they were removed)", async () => {
    renderWithProviders(<OperationsPanel />);
    await screen.findByText("No housekeeping tasks");
    expect(screen.queryByRole("tab", { name: /overview/i })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: /room ?board|board/i }),
    ).not.toBeInTheDocument();
  });
});

describe("OperationsPanel — accessible tab pattern", () => {
  it("exposes a labelled tablist, aria-selected + roving tabIndex, and a linked tabpanel", async () => {
    renderWithProviders(<OperationsPanel />);
    await screen.findByText("No housekeeping tasks");

    const tablist = screen.getByRole("tablist", { name: "Operations sections" });
    expect(tablist).toBeInTheDocument();

    const cleaning = screen.getByRole("tab", { name: "Cleaning" });
    const maintenance = screen.getByRole("tab", { name: "Maintenance" });
    // Selected tab: aria-selected=true + tabIndex 0; the rest are -1 (roving).
    expect(cleaning).toHaveAttribute("aria-selected", "true");
    expect(cleaning).toHaveAttribute("tabindex", "0");
    expect(maintenance).toHaveAttribute("aria-selected", "false");
    expect(maintenance).toHaveAttribute("tabindex", "-1");

    // The panel is a tabpanel labelled by the active tab.
    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", cleaning.id);
  });

  it("switches panel + selection when another tab is clicked", async () => {
    renderWithProviders(<OperationsPanel />);
    await screen.findByText("No housekeeping tasks");

    fireEvent.click(screen.getByRole("tab", { name: "Maintenance" }));
    await screen.findByText("No maintenance requests");
    expect(screen.getByRole("tab", { name: "Maintenance" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Cleaning" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
    expect(screen.queryByText("No housekeeping tasks")).not.toBeInTheDocument();
  });
});

describe("OperationsPanel — keyboard arrow navigation (LTR)", () => {
  it("moves selection with ArrowRight, End and Home", async () => {
    renderWithProviders(<OperationsPanel />);
    await screen.findByText("No housekeeping tasks");

    const cleaning = screen.getByRole("tab", { name: "Cleaning" });
    cleaning.focus();

    fireEvent.keyDown(cleaning, { key: "ArrowRight" });
    await screen.findByText("No maintenance requests");
    expect(screen.getByRole("tab", { name: "Maintenance" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Maintenance" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    fireEvent.keyDown(screen.getByRole("tab", { name: "Maintenance" }), { key: "End" });
    await screen.findByText("No lost & found items");
    expect(screen.getByRole("tab", { name: "Lost & found" })).toHaveFocus();

    fireEvent.keyDown(screen.getByRole("tab", { name: "Lost & found" }), { key: "Home" });
    await screen.findByText("No housekeeping tasks");
    expect(screen.getByRole("tab", { name: "Cleaning" })).toHaveFocus();
  });
});

describe("OperationsPanel — ?tab= deep link", () => {
  it("opens the maintenance tab directly when the URL carries tab=maintenance", async () => {
    nav.setSearch("tab=maintenance");
    renderWithProviders(<OperationsPanel />);
    await screen.findByText("No maintenance requests");
    expect(screen.getByRole("tab", { name: "Maintenance" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("falls back to Cleaning for an unknown ?tab= value", async () => {
    nav.setSearch("tab=overview");
    renderWithProviders(<OperationsPanel />);
    await screen.findByText("No housekeeping tasks");
    expect(screen.getByRole("tab", { name: "Cleaning" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});

describe("OperationsPanel — the stat row renders per tab", () => {
  it("shows the cleaning counters on the Cleaning tab", async () => {
    renderWithProviders(<OperationsPanel />);
    await screen.findByText("No housekeeping tasks");
    const stats = screen.getByRole("group", { name: "Housekeeping tasks" });
    expect(within(stats).getByText("Needs cleaning")).toBeInTheDocument();
    expect(within(stats).getByText("Upcoming arrival")).toBeInTheDocument();
  });

  it("shows the maintenance counters (incl. blocking rooms) on the Maintenance tab", async () => {
    renderWithProviders(<OperationsPanel />);
    await screen.findByText("No housekeeping tasks");
    fireEvent.click(screen.getByRole("tab", { name: "Maintenance" }));
    await screen.findByText("No maintenance requests");
    const stats = screen.getByRole("group", { name: "Maintenance requests" });
    expect(within(stats).getByText("Blocking rooms")).toBeInTheDocument();
  });

  it("shows the lost & found counters on the Lost & found tab", async () => {
    renderWithProviders(<OperationsPanel />);
    await screen.findByText("No housekeeping tasks");
    fireEvent.click(screen.getByRole("tab", { name: "Lost & found" }));
    await screen.findByText("No lost & found items");
    const stats = screen.getByRole("group", { name: "Lost & found" });
    expect(within(stats).getByText("Stored")).toBeInTheDocument();
  });
});

describe("OperationsPanel — aria-controls references only the mounted panel", () => {
  it("points the ACTIVE tab at the one mounted tabpanel and drops it on inactive tabs", async () => {
    renderWithProviders(<OperationsPanel />);
    await screen.findByText("No housekeeping tasks");

    const cleaning = screen.getByRole("tab", { name: "Cleaning" });
    const maintenance = screen.getByRole("tab", { name: "Maintenance" });
    const panel = screen.getByRole("tabpanel");

    // The active tab controls the mounted panel — and its id RESOLVES to it.
    const controls = cleaning.getAttribute("aria-controls");
    expect(controls).toBe(panel.id);
    expect(document.getElementById(controls as string)).toBe(panel);
    // Inactive tabs carry NO dangling aria-controls (their panel isn't mounted).
    expect(maintenance).not.toHaveAttribute("aria-controls");

    // Activating Maintenance mounts + references ITS panel and clears Cleaning's.
    fireEvent.click(maintenance);
    await screen.findByText("No maintenance requests");
    const panel2 = screen.getByRole("tabpanel");
    const controls2 = maintenance.getAttribute("aria-controls");
    expect(controls2).toBe(panel2.id);
    expect(document.getElementById(controls2 as string)).toBe(panel2);
    expect(screen.getByRole("tab", { name: "Cleaning" })).not.toHaveAttribute(
      "aria-controls",
    );
  });
});

describe("OperationsPanel — RTL (ar locale)", () => {
  it("labels the tablist in Arabic and treats ArrowLeft as forward", async () => {
    renderWithProviders(<OperationsPanel />, { locale: "ar" });
    await screen.findByText("لا توجد مهام تنظيف");

    // Arabic tab labels render (RTL dictionary).
    expect(screen.getByRole("tablist", { name: "أقسام التشغيل" })).toBeInTheDocument();
    const cleaning = screen.getByRole("tab", { name: "التنظيف" });
    cleaning.focus();

    // Under RTL, ArrowLeft advances to the NEXT tab (Maintenance).
    fireEvent.keyDown(cleaning, { key: "ArrowLeft" });
    await screen.findByText("لا توجد طلبات صيانة");
    expect(screen.getByRole("tab", { name: "الصيانة" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});
