import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * MaintenanceTab (WP12 / owner §17: blocking indicator, priority display, FULL
 * assignee select, close gated by permission + offering room_next_status, no free
 * mark-available, states). The room is never released automatically — closing a
 * request asks explicitly for the room's next status.
 */

const nav = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));

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
  closeMaintenanceRequest,
  getOperationsOverview,
  listMaintenanceRequests,
  setMaintenanceStatus,
} from "@/lib/api/operations";
import { listRoomOptions } from "@/lib/api/rooms";
import { listStaff } from "@/lib/api/staff";
import { listGuests } from "@/lib/api/guests";
import { listCurrentResidents } from "@/lib/api/stays";
import type { PaginatedResponse } from "@/lib/api/types";
import { MaintenanceTab } from "../MaintenanceTab";
import {
  apiError,
  makeMtRequest,
  makeOverview,
  makeStaffRow,
  renderWithProviders,
} from "@/test-utils";

function page<T>(results: T[], count = results.length): PaginatedResponse<T> {
  return { count, next: null, previous: null, results };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function requests(rows: ReturnType<typeof makeMtRequest>[], count = rows.length) {
  vi.mocked(listMaintenanceRequests).mockResolvedValue(page(rows, count));
}

beforeEach(() => {
  vi.clearAllMocks();
  access.set([
    "maintenance.status_update",
    "maintenance.assign",
    "maintenance.close",
    "maintenance.create",
  ]);
  vi.mocked(listMaintenanceRequests).mockResolvedValue(page([]));
  vi.mocked(getOperationsOverview).mockResolvedValue(makeOverview());
  vi.mocked(listRoomOptions).mockResolvedValue(page([]));
  vi.mocked(listStaff).mockResolvedValue(page([]));
  vi.mocked(listGuests).mockResolvedValue(page([]));
  vi.mocked(listCurrentResidents).mockResolvedValue(page([]));
});

describe("MaintenanceTab — blocking indicator + priority", () => {
  it("shows the blocking badge (danger accent) and the priority badge", async () => {
    requests([
      makeMtRequest({
        priority: "high",
        affects_room_availability: true,
        room_block_status: "maintenance",
      }),
    ]);
    const { container } = renderWithProviders(<MaintenanceTab />);
    await screen.findByText("Broken air conditioner");

    const card = container.querySelector(".op-card") as HTMLElement;
    // A room-blocking request carries the blocking indicator…
    expect(within(card).getByText(/Blocks the room/)).toBeInTheDocument();
    // …the priority is shown as its own badge (scoped to the card — the filter
    // select also lists a "High" option)…
    expect(within(card).getByText("High")).toBeInTheDocument();
    // …and the card's accent rail switches to danger.
    expect(card.style.getPropertyValue("--op-accent")).toBe("var(--color-danger)");
  });

  it("shows no blocking badge for a non-blocking request", async () => {
    requests([makeMtRequest({ affects_room_availability: false })]);
    renderWithProviders(<MaintenanceTab />);
    await screen.findByText("Broken air conditioner");
    expect(screen.queryByText(/Blocks the room/)).not.toBeInTheDocument();
  });
});

describe("MaintenanceTab — start action gated by permission", () => {
  it("starts an open request via setMaintenanceStatus with status_update", async () => {
    access.set(["maintenance.status_update"]);
    requests([makeMtRequest({ status: "open" })]);
    renderWithProviders(<MaintenanceTab />);

    fireEvent.click(await screen.findByRole("button", { name: "Start" }));
    await waitFor(() =>
      expect(setMaintenanceStatus).toHaveBeenCalledWith(1, "in_progress"),
    );
  });

  it("shows no Start without status_update", async () => {
    access.set(["maintenance.assign"]);
    requests([makeMtRequest({ status: "open" })]);
    renderWithProviders(<MaintenanceTab />);
    await screen.findByText("Broken air conditioner");
    expect(screen.queryByRole("button", { name: "Start" })).not.toBeInTheDocument();
  });
});

describe("MaintenanceTab — close gated by permission + room_next_status", () => {
  it("offers Close only with the close permission and asks for the room's next status", async () => {
    requests([makeMtRequest({ status: "resolved", room: 11, room_number: "101" })]);
    renderWithProviders(<MaintenanceTab />);

    fireEvent.click(await screen.findByRole("button", { name: "Close" }));
    const dialog = await screen.findByRole("dialog");

    // The room's next status is chosen EXPLICITLY (never released automatically).
    const nextStatus = within(dialog).getByLabelText(
      "Room status after closing",
    ) as HTMLSelectElement;
    expect(within(nextStatus).getByRole("option", { name: "Keep current status" })).toBeInTheDocument();
    expect(within(nextStatus).getByRole("option", { name: "Mark dirty (needs cleaning)" })).toBeInTheDocument();
    expect(within(nextStatus).getByRole("option", { name: "Mark available" })).toBeInTheDocument();

    // Submit the close form (the header X is also labelled "Close").
    fireEvent.submit(dialog.querySelector("#mt-close-form") as HTMLFormElement);
    await waitFor(() =>
      expect(closeMaintenanceRequest).toHaveBeenCalledWith(1, "dirty", ""),
    );
  });

  it("hides Close without the close permission", async () => {
    access.set(["maintenance.status_update"]);
    requests([makeMtRequest({ status: "resolved" })]);
    renderWithProviders(<MaintenanceTab />);
    await screen.findByText("Broken air conditioner");
    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  });
});

describe("MaintenanceTab — full assignee select", () => {
  it("offers every active staff member (not just assign-to-me) in the create form", async () => {
    vi.mocked(listStaff).mockResolvedValue(
      page([
        makeStaffRow({ user_id: 501, full_name: "Sara Cleaner" }),
        makeStaffRow({ user_id: 502, full_name: "Omar Fix" }),
        makeStaffRow({ user_id: 503, full_name: "Inactive Ivy", is_active: false }),
      ]),
    );
    requests([]);
    renderWithProviders(<MaintenanceTab />);
    await screen.findByText("No maintenance requests");

    fireEvent.click(screen.getByRole("button", { name: "New maintenance request" }));
    const dialog = await screen.findByRole("dialog");

    const assignee = within(dialog).getByLabelText("Staff member") as HTMLSelectElement;
    await waitFor(() =>
      expect(within(assignee).getByRole("option", { name: "Sara Cleaner" })).toBeInTheDocument(),
    );
    // The FULL active roster is offered…
    expect(within(assignee).getByRole("option", { name: "Omar Fix" })).toBeInTheDocument();
    // …and inactive members are excluded.
    expect(within(assignee).queryByRole("option", { name: "Inactive Ivy" })).not.toBeInTheDocument();
  });
});

describe("MaintenanceTab — no free mark-available", () => {
  it("has no direct release control on the list view", async () => {
    requests([
      makeMtRequest({ id: 1, request_number: "MT00001", status: "resolved", room: 11 }),
      makeMtRequest({ id: 2, request_number: "MT00002", status: "open", room: 12 }),
    ]);
    renderWithProviders(<MaintenanceTab />);
    await screen.findByText("MT00001");
    expect(
      screen.queryByRole("button", { name: /mark available|release/i }),
    ).not.toBeInTheDocument();
  });
});

describe("MaintenanceTab — async states", () => {
  it("shows the loading state, then the empty state", async () => {
    const d = deferred<PaginatedResponse<ReturnType<typeof makeMtRequest>>>();
    vi.mocked(listMaintenanceRequests).mockReturnValue(d.promise);
    renderWithProviders(<MaintenanceTab />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    await act(async () => {
      d.resolve(page([]));
    });
    expect(await screen.findByText("No maintenance requests")).toBeInTheDocument();
  });

  it("shows an error state with a Retry that recovers", async () => {
    vi.mocked(listMaintenanceRequests).mockRejectedValue(apiError("server_error", 500));
    renderWithProviders(<MaintenanceTab />);
    const retry = await screen.findByRole("button", { name: "Retry" });
    vi.mocked(listMaintenanceRequests).mockResolvedValue(page([makeMtRequest()]));
    fireEvent.click(retry);
    await screen.findByText("Broken air conditioner");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});

describe("MaintenanceTab — card shows description + duration (F3a fields)", () => {
  it("renders a clamped description note (with a full-text title) and a started_at duration", async () => {
    requests([
      makeMtRequest({
        status: "in_progress",
        description: "AC compressor is leaking water onto the carpet",
        started_at: "2026-07-19T08:00:00Z",
        resolved_at: "2026-07-19T09:30:00Z",
      }),
    ]);
    const { container } = renderWithProviders(<MaintenanceTab />);
    await screen.findByText("Broken air conditioner");

    // The description is a clamped note whose FULL text stays in a title tooltip.
    const note = container.querySelector(".op-card__note") as HTMLElement;
    expect(note).toBeInTheDocument();
    expect(note).toHaveTextContent("AC compressor is leaking water onto the carpet");
    expect(note).toHaveAttribute(
      "title",
      "AC compressor is leaking water onto the carpet",
    );

    // A Duration fact appears once the request carries a start timestamp.
    const card = container.querySelector(".op-card") as HTMLElement;
    expect(within(card).getByText("Duration")).toBeInTheDocument();
  });

  it("omits the description note and the duration fact when both are absent", async () => {
    requests([makeMtRequest({ status: "open", description: "", started_at: null })]);
    const { container } = renderWithProviders(<MaintenanceTab />);
    await screen.findByText("Broken air conditioner");
    expect(container.querySelector(".op-card__note")).not.toBeInTheDocument();
    const card = container.querySelector(".op-card") as HTMLElement;
    expect(within(card).queryByText("Duration")).not.toBeInTheDocument();
  });
});

describe("MaintenanceTab — a11y M1 (non-destructive refetch + live region + focus)", () => {
  it("announces the settled result count in the stable live region", async () => {
    requests([makeMtRequest({ status: "open" })], 1);
    renderWithProviders(<MaintenanceTab />);
    await screen.findByText("Broken air conditioner");
    await waitFor(() =>
      expect(screen.getByTestId("mt-results-announce")).toHaveTextContent("1 results"),
    );
  });

  it("keeps the cards mounted with NO full-screen loader during a background refetch", async () => {
    requests([makeMtRequest({ status: "open" })], 1);
    const { container } = renderWithProviders(<MaintenanceTab />);
    await screen.findByText("Broken air conditioner");

    // Hold the next (filter-triggered) refetch in flight.
    const d = deferred<PaginatedResponse<ReturnType<typeof makeMtRequest>>>();
    vi.mocked(listMaintenanceRequests).mockReturnValue(d.promise);
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "open" } });

    // The existing card stays mounted; the full-screen initial loader never shows.
    expect(screen.getByText("Broken air conditioner")).toBeInTheDocument();
    expect(container.querySelector(".state[role='status']")).not.toBeInTheDocument();

    await act(async () => {
      d.resolve(page([makeMtRequest({ status: "open" })], 1));
    });
    await screen.findByText("Broken air conditioner");
  });

  it("surfaces a background-refetch failure as a non-blocking toast, keeping the cards", async () => {
    requests([makeMtRequest({ status: "open" })], 1);
    renderWithProviders(<MaintenanceTab />);
    await screen.findByText("Broken air conditioner");

    vi.mocked(listMaintenanceRequests).mockRejectedValue(apiError("server_error", 500));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "resolved" } });

    // A toast appears; the full ErrorState + Retry does NOT, and the card stays.
    await screen.findByText("Something went wrong. Please try again.");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.getByText("Broken air conditioner")).toBeInTheDocument();
  });

  it("moves focus to the stable results anchor (never <body>) after an action drops the card", async () => {
    access.set(["maintenance.status_update"]);
    requests([makeMtRequest({ status: "open" })], 1);
    renderWithProviders(<MaintenanceTab />);
    const start = await screen.findByRole("button", { name: "Start" });
    start.focus();

    // The action's reload returns an empty list (the card leaves the view).
    vi.mocked(listMaintenanceRequests).mockResolvedValue(page([]));
    fireEvent.click(start);

    await screen.findByText("No maintenance requests");
    expect(document.activeElement).not.toBe(document.body);
    expect(document.activeElement).toHaveClass("op-results");
  });
});
