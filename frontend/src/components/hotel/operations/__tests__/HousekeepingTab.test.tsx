import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * HousekeepingTab (WP12 / owner §17: UPCOMING ARRIVAL, OCCUPIED CLEANING, come-
 * back-later, INSPECTION, PERMISSIONS, NO FREE MARK-AVAILABLE, search / filters /
 * pagination, states). The cleaning card computes ONE primary action from state +
 * permission and folds the rest into the card menu; an occupied room can never be
 * "made available" from here; the arrival hint never leaks a reservation number.
 */

const nav = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
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
  approveInspection,
  comeBackLaterHousekeepingTask,
  completeHousekeepingTask,
  listArrivalsNotReady,
  listHousekeepingTasks,
  rejectInspection,
  setHousekeepingStatus,
} from "@/lib/api/operations";
import { listRoomOptions } from "@/lib/api/rooms";
import { listStaff } from "@/lib/api/staff";
import { listGuests } from "@/lib/api/guests";
import { listCurrentResidents } from "@/lib/api/stays";
import type { PaginatedResponse } from "@/lib/api/types";
import { HousekeepingTab } from "../HousekeepingTab";
import {
  apiError,
  makeArrivalRow,
  makeHkTask,
  renderWithProviders,
} from "@/test-utils";

function page<T>(results: T[], count = results.length): PaginatedResponse<T> {
  return { count, next: null, previous: null, results };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function tasks(rows: ReturnType<typeof makeHkTask>[], count = rows.length) {
  vi.mocked(listHousekeepingTasks).mockResolvedValue(page(rows, count));
}

beforeEach(() => {
  vi.clearAllMocks();
  access.set(["housekeeping.status_update", "housekeeping.assign", "housekeeping.inspect"]);
  vi.mocked(listHousekeepingTasks).mockResolvedValue(page([]));
  vi.mocked(listArrivalsNotReady).mockResolvedValue([]);
  vi.mocked(listRoomOptions).mockResolvedValue(page([]));
  vi.mocked(listStaff).mockResolvedValue(page([]));
  vi.mocked(listGuests).mockResolvedValue(page([]));
  vi.mocked(listCurrentResidents).mockResolvedValue(page([]));
});

describe("HousekeepingTab — upcoming arrival hint (never a reservation number)", () => {
  it("shows the 'Arrival soon' badge with the arrival date and NO booking reference", async () => {
    vi.mocked(listArrivalsNotReady).mockResolvedValue([makeArrivalRow()]);
    tasks([
      makeHkTask({
        upcoming_arrival: {
          has_upcoming: true,
          arrival_date: "2026-07-20",
          arrival_time: "14:00:00",
        },
      }),
    ]);
    const { container } = renderWithProviders(<HousekeepingTab />);

    const badge = await screen.findByText(/Arrival soon/);
    // The badge carries only the date — a year anchor proves the date rendered.
    expect(badge.textContent).toMatch(/2026/);
    // A housekeeping-only card must NEVER expose a reservation number.
    expect(screen.queryByText(/R00\d{3}/)).not.toBeInTheDocument();
    expect(container.textContent ?? "").not.toMatch(/reservation/i);
  });

  it("omits the arrival badge when there is no upcoming arrival", async () => {
    tasks([makeHkTask({ upcoming_arrival: { has_upcoming: false, arrival_date: null, arrival_time: null } })]);
    renderWithProviders(<HousekeepingTab />);
    await screen.findByText("Standard");
    expect(screen.queryByText(/Arrival soon/)).not.toBeInTheDocument();
  });
});

describe("HousekeepingTab — occupied cleaning completion", () => {
  it("requires a service outcome and offers NO 'mark available' for an occupied room", async () => {
    tasks([makeHkTask({ status: "in_progress", is_occupied: true })]);
    renderWithProviders(<HousekeepingTab />);

    const complete = await screen.findByRole("button", { name: "Complete" });
    fireEvent.click(complete);

    const dialog = await screen.findByRole("dialog");
    // The mandatory service-result select is present with the four outcomes.
    const outcome = within(dialog).getByLabelText("Service result") as HTMLSelectElement;
    expect(
      within(outcome).getByRole("option", { name: "Cleaned" }),
    ).toBeInTheDocument();
    expect(within(outcome).getByRole("option", { name: "Guest refused" })).toBeInTheDocument();
    expect(within(outcome).getByRole("option", { name: "Do not disturb" })).toBeInTheDocument();
    expect(within(outcome).getByRole("option", { name: "No access" })).toBeInTheDocument();

    // No "make the room available" control anywhere in the occupied flow.
    expect(within(dialog).queryByText("Make the room available")).not.toBeInTheDocument();
    expect(
      within(dialog).queryByRole("button", { name: /mark available|release/i }),
    ).not.toBeInTheDocument();

    fireEvent.change(outcome, { target: { value: "guest_refused" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Complete" }));

    // Completion posts the outcome and NEVER asks to release the room.
    await waitFor(() =>
      expect(completeHousekeepingTask).toHaveBeenCalledWith(1, false, "", "guest_refused"),
    );
  });

  it("keeps 'come back later' as a SEPARATE non-terminal action (task stays active)", async () => {
    tasks([makeHkTask({ status: "in_progress", is_occupied: true })]);
    renderWithProviders(<HousekeepingTab />);
    await screen.findByRole("button", { name: "Complete" });

    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Come back later" }));

    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Come back later" }));

    await waitFor(() => expect(comeBackLaterHousekeepingTask).toHaveBeenCalledWith(1, {}));
    // It is NOT a completion and NOT a status change — the task stays active.
    expect(completeHousekeepingTask).not.toHaveBeenCalled();
    expect(setHousekeepingStatus).not.toHaveBeenCalled();
  });
});

describe("HousekeepingTab — inspection gate", () => {
  it("shows approve (primary) + reject (menu) only with the inspect permission", async () => {
    tasks([makeHkTask({ status: "awaiting_inspection" })]);
    renderWithProviders(<HousekeepingTab />);

    const approve = await screen.findByRole("button", { name: "Approve inspection" });
    fireEvent.click(approve);
    await waitFor(() => expect(approveInspection).toHaveBeenCalledWith(1));
  });

  it("rejection requires a reason", async () => {
    tasks([makeHkTask({ status: "awaiting_inspection" })]);
    renderWithProviders(<HousekeepingTab />);
    await screen.findByRole("button", { name: "Approve inspection" });

    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Reject inspection" }));

    const dialog = await screen.findByRole("dialog");
    // Submitting empty surfaces the required-reason error and does NOT call the API.
    fireEvent.click(within(dialog).getByRole("button", { name: "Reject inspection" }));
    expect(
      await within(dialog).findByText("An inspection rejection reason is required."),
    ).toBeInTheDocument();
    expect(rejectInspection).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByLabelText("Rejection reason (required)"), {
      target: { value: "Bathroom still dirty" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Reject inspection" }));
    await waitFor(() =>
      expect(rejectInspection).toHaveBeenCalledWith(1, "Bathroom still dirty"),
    );
  });

  it("hides approve/reject when the inspect permission is missing", async () => {
    access.set(["housekeeping.status_update"]);
    tasks([makeHkTask({ status: "awaiting_inspection" })]);
    renderWithProviders(<HousekeepingTab />);
    await screen.findByText("Standard");
    expect(
      screen.queryByRole("button", { name: "Approve inspection" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More" })).not.toBeInTheDocument();
  });
});

describe("HousekeepingTab — one primary action gated by permission", () => {
  it("offers Assign (not Start) when only the assign permission is held", async () => {
    access.set(["housekeeping.assign"]);
    tasks([makeHkTask({ status: "pending", assigned_to: null })]);
    const { container } = renderWithProviders(<HousekeepingTab />);
    await screen.findByText("Standard");

    // Exactly one primary button, and it is Assign (Start needs status_update).
    expect(container.querySelectorAll(".op-card__primary")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Assign" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start" })).not.toBeInTheDocument();
  });

  it("starts a task via setHousekeepingStatus with the status_update permission", async () => {
    access.set(["housekeeping.status_update"]);
    tasks([makeHkTask({ status: "assigned", assigned_to: 501, assigned_to_name: "Sara" })]);
    renderWithProviders(<HousekeepingTab />);

    fireEvent.click(await screen.findByRole("button", { name: "Start" }));
    await waitFor(() =>
      expect(setHousekeepingStatus).toHaveBeenCalledWith(1, "in_progress"),
    );
  });

  it("renders no action controls at all when the user holds no operations permission", async () => {
    access.set([]);
    tasks([makeHkTask({ status: "pending" })]);
    const { container } = renderWithProviders(<HousekeepingTab />);
    await screen.findByText("Standard");
    expect(container.querySelector(".op-card__actions")).toBeNull();
    expect(screen.queryByRole("button", { name: "More" })).not.toBeInTheDocument();
    // The create action is gated too.
    expect(
      screen.queryByRole("button", { name: "New cleaning task" }),
    ).not.toBeInTheDocument();
  });
});

describe("HousekeepingTab — no free mark-available anywhere", () => {
  it("exposes NO control that directly releases a room across task states", async () => {
    tasks([
      makeHkTask({ id: 1, task_number: "HK00001", status: "pending" }),
      makeHkTask({ id: 2, task_number: "HK00002", status: "in_progress", is_occupied: true }),
      makeHkTask({ id: 3, task_number: "HK00003", status: "awaiting_inspection" }),
    ]);
    renderWithProviders(<HousekeepingTab />);
    await screen.findByText("HK00001");

    expect(
      screen.queryByRole("button", { name: /mark available|release/i }),
    ).not.toBeInTheDocument();
    // The operations API surface has no room-status setter; nothing here calls one.
    expect(setHousekeepingStatus).not.toHaveBeenCalled();
  });
});

describe("HousekeepingTab — search, filters and pagination", () => {
  it("forwards the typed search term to the list endpoint on submit", async () => {
    tasks([makeHkTask()]);
    renderWithProviders(<HousekeepingTab />);
    await screen.findByText("Standard");

    const input = screen.getByLabelText("Search");
    fireEvent.change(input, { target: { value: "101" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    await waitFor(() =>
      expect(
        vi.mocked(listHousekeepingTasks).mock.calls.some(
          ([p]) => p?.search === "101" && "task_type" in (p ?? {}),
        ),
      ).toBe(true),
    );
  });

  it("resets to page 1 when a filter changes", async () => {
    tasks([makeHkTask()], 30); // > PAGE_SIZE so page 2 is reachable
    renderWithProviders(<HousekeepingTab />);
    await screen.findByText("Standard");

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(
        vi.mocked(listHousekeepingTasks).mock.calls.some(([p]) => p?.page === 2),
      ).toBe(true),
    );

    // Changing the status filter drops back to page 1.
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "in_progress" } });
    await waitFor(() =>
      expect(
        vi.mocked(listHousekeepingTasks).mock.calls.some(
          ([p]) => p?.status === "in_progress" && p?.page === 1 && "task_type" in (p ?? {}),
        ),
      ).toBe(true),
    );
  });

  it("pages with Next/Previous (server pagination)", async () => {
    tasks([makeHkTask()], 30);
    renderWithProviders(<HousekeepingTab />);
    await screen.findByText("Standard");

    const prev = screen.getByRole("button", { name: "Previous" });
    expect(prev).toBeDisabled(); // page 1
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(
        vi.mocked(listHousekeepingTasks).mock.calls.some(([p]) => p?.page === 2),
      ).toBe(true),
    );
  });
});

describe("HousekeepingTab — stat filter", () => {
  it("applies the matching status filter when a stat tile is clicked (aria-pressed)", async () => {
    tasks([makeHkTask()], 3);
    renderWithProviders(<HousekeepingTab />);
    await screen.findByText("Standard");

    const stat = screen.getByRole("button", { name: /Needs cleaning/ });
    fireEvent.click(stat);

    await waitFor(() =>
      expect(
        vi.mocked(listHousekeepingTasks).mock.calls.some(
          ([p]) => p?.status === "pending" && "task_type" in (p ?? {}),
        ),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Needs cleaning/ })).toHaveAttribute(
        "aria-pressed",
        "true",
      ),
    );
  });
});

describe("HousekeepingTab — async states", () => {
  it("shows the loading state while the first load is in flight", async () => {
    const d = deferred<PaginatedResponse<ReturnType<typeof makeHkTask>>>();
    vi.mocked(listHousekeepingTasks).mockReturnValue(d.promise);
    const { container } = renderWithProviders(<HousekeepingTab />);

    // The full-screen INITIAL loader is a `.state` status panel. The room-picker
    // in the filter bar has its OWN polite status region, so target the initial
    // loader specifically (not a bare role=status).
    expect(container.querySelector(".state[role='status']")).toBeInTheDocument();
    await act(async () => {
      d.resolve(page([]));
    });
    // Once the first load settles, the full loader is gone (the cards region and
    // its reserved background-refetch status row take over).
    await waitFor(() =>
      expect(container.querySelector(".state[role='status']")).not.toBeInTheDocument(),
    );
  });

  it("shows an error state with a Retry that recovers", async () => {
    vi.mocked(listHousekeepingTasks).mockRejectedValue(apiError("server_error", 500));
    renderWithProviders(<HousekeepingTab />);

    const retry = await screen.findByRole("button", { name: "Retry" });
    vi.mocked(listHousekeepingTasks).mockResolvedValue(page([makeHkTask()]));
    fireEvent.click(retry);
    await screen.findByText("Standard");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("shows the empty state when there are no tasks", async () => {
    tasks([]);
    renderWithProviders(<HousekeepingTab />);
    expect(await screen.findByText("No housekeeping tasks")).toBeInTheDocument();
  });
});

describe("HousekeepingTab — RTL (ar locale)", () => {
  it("renders the Arabic arrival badge for an upcoming arrival", async () => {
    tasks([
      makeHkTask({
        upcoming_arrival: { has_upcoming: true, arrival_date: "2026-07-20", arrival_time: null },
      }),
    ]);
    renderWithProviders(<HousekeepingTab />, { locale: "ar" });
    expect(await screen.findByText(/وصول قريب/)).toBeInTheDocument();
  });
});

describe("HousekeepingTab — a11y M1 (non-destructive refetch + live region + focus)", () => {
  it("announces the settled result count in the stable live region", async () => {
    tasks([makeHkTask()], 1);
    renderWithProviders(<HousekeepingTab />);
    await screen.findByText("Standard");
    await waitFor(() =>
      expect(screen.getByTestId("hk-results-announce")).toHaveTextContent("1 results"),
    );
  });

  it("keeps the cards mounted with NO full-screen loader during a background refetch", async () => {
    tasks([makeHkTask()], 1);
    const { container } = renderWithProviders(<HousekeepingTab />);
    await screen.findByText("Standard");

    // Hold the next (filter-triggered) refetch in flight.
    const d = deferred<PaginatedResponse<ReturnType<typeof makeHkTask>>>();
    vi.mocked(listHousekeepingTasks).mockReturnValue(d.promise);
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "pending" } });

    // The existing card stays mounted; the full-screen initial loader never shows.
    expect(screen.getByText("Standard")).toBeInTheDocument();
    expect(container.querySelector(".state[role='status']")).not.toBeInTheDocument();

    await act(async () => {
      d.resolve(page([makeHkTask()], 1));
    });
    await screen.findByText("Standard");
  });

  it("moves focus to the stable results anchor (never <body>) after an action drops the card", async () => {
    access.set(["housekeeping.status_update"]);
    tasks([makeHkTask({ status: "assigned", assigned_to: 501, assigned_to_name: "Sara" })], 1);
    renderWithProviders(<HousekeepingTab />);
    const start = await screen.findByRole("button", { name: "Start" });
    start.focus();

    // The action's reload returns an empty list (the card leaves the view).
    vi.mocked(listHousekeepingTasks).mockResolvedValue(page([]));
    fireEvent.click(start);

    await screen.findByText("No housekeeping tasks");
    expect(document.activeElement).not.toBe(document.body);
    expect(document.activeElement).toHaveClass("op-results");
  });
});
