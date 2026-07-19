import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * LostReportsSection (the guest-reported "lost report" cycle inside the Lost-&-
 * Found tab): list + stat tiles + filters, the state-driven primary action and
 * "More" menu, the manual MATCH flow (candidate picker → matchLostReport), the
 * handover / unmatch / close-unfound / cancel actions, backend-error toasts, and
 * the a11y live-region + focus-restore behaviour it inherits from the found tab.
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
  listLostReports: vi.fn(),
  getLostReport: vi.fn(),
  createLostReport: vi.fn(),
  updateLostReport: vi.fn(),
  setLostReportStatus: vi.fn(),
  matchLostReport: vi.fn(),
  unmatchLostReport: vi.fn(),
  handoverLostReport: vi.fn(),
  closeUnfoundLostReport: vi.fn(),
  cancelLostReport: vi.fn(),
  listLostReportCandidates: vi.fn(),
}));

vi.mock("@/lib/api/guests", () => ({ listGuests: vi.fn() }));
vi.mock("@/lib/api/staff", () => ({ listStaff: vi.fn() }));

import {
  cancelLostReport,
  closeUnfoundLostReport,
  handoverLostReport,
  listLostReportCandidates,
  listLostReports,
  matchLostReport,
  setLostReportStatus,
  unmatchLostReport,
} from "@/lib/api/operations";
import { listGuests } from "@/lib/api/guests";
import type { LostReportListItem, PaginatedResponse } from "@/lib/api/types";
import { LostReportsSection } from "../LostReportsSection";
import { apiError, makeLfItem, renderWithProviders } from "@/test-utils";

function page<T>(results: T[], count = results.length): PaginatedResponse<T> {
  return { count, next: null, previous: null, results };
}

function makeLrReport(overrides: Partial<LostReportListItem> = {}): LostReportListItem {
  return {
    id: 1,
    report_number: "LR00001",
    description: "Blue backpack",
    category: "other",
    status: "open",
    last_seen_location: "Lobby",
    reporter_name: "Ali Guest",
    lost_at: "2026-07-19T08:00:00Z",
    stay: null,
    guest: null,
    guest_name: "",
    reservation: null,
    reservation_number: "",
    room_number: "",
    matched_found_item: null,
    matched_found_item_summary: null,
    created_at: "2026-07-19T08:00:00Z",
    updated_at: "2026-07-19T08:00:00Z",
    matched_at: null,
    returned_at: null,
    record_type: "lost_report",
    ...overrides,
  };
}

function reports(rows: LostReportListItem[], count = rows.length) {
  vi.mocked(listLostReports).mockResolvedValue(page(rows, count));
}

function render() {
  return renderWithProviders(
    <LostReportsSection createOpen={false} onCreateClose={() => {}} />,
  );
}

/** Open the state-computed "More" menu for the (single) card on screen. */
function openMenu() {
  fireEvent.click(screen.getByRole("button", { name: "More" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  access.set(["lost_found.status_update", "lost_found.create"]);
  vi.mocked(listLostReports).mockResolvedValue(page([]));
  vi.mocked(listLostReportCandidates).mockResolvedValue([]);
  vi.mocked(listGuests).mockResolvedValue(page([]));
});

describe("LostReportsSection — list, tiles and filters", () => {
  it("renders the report card, the stat tiles and the search filter", async () => {
    reports([makeLrReport()]);
    render();
    await screen.findByText("Blue backpack");

    // Stat row (StatCards, aria-label = the section title).
    const statGroup = screen.getByRole("group", { name: "Lost reports" });
    expect(within(statGroup).getByText("Open")).toBeInTheDocument();
    expect(within(statGroup).getByText("Searching")).toBeInTheDocument();
    expect(within(statGroup).getByText("Matched")).toBeInTheDocument();
    // Filters.
    expect(screen.getByLabelText("Search")).toBeInTheDocument();
  });

  it("shows the lost-report TYPE badge on the card", async () => {
    reports([makeLrReport()]);
    render();
    await screen.findByText("Blue backpack");
    expect(screen.getByText("Lost report")).toBeInTheDocument();
  });

  it("toggles the status filter from a stat tile", async () => {
    reports([makeLrReport()], 3);
    render();
    await screen.findByText("Blue backpack");

    const statGroup = screen.getByRole("group", { name: "Lost reports" });
    fireEvent.click(within(statGroup).getByRole("button", { name: /Searching/ }));
    await waitFor(() =>
      expect(
        vi
          .mocked(listLostReports)
          .mock.calls.some(
            ([p]) => p?.status === "searching" && "category" in (p ?? {}),
          ),
      ).toBe(true),
    );
  });

  it("announces the settled result count in the stable live region", async () => {
    reports([makeLrReport()], 1);
    render();
    await screen.findByText("Blue backpack");
    await waitFor(() =>
      expect(screen.getByTestId("lr-results-announce")).toHaveTextContent("1 results"),
    );
  });
});

describe("LostReportsSection — primary action + menu per state", () => {
  it("open: primary Match plus a start-searching / close / cancel menu", async () => {
    reports([makeLrReport({ status: "open" })]);
    render();
    expect(await screen.findByRole("button", { name: "Match" })).toBeInTheDocument();

    openMenu();
    expect(screen.getByRole("menuitem", { name: "Start searching" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Close as not found" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Cancel report" })).toBeInTheDocument();
  });

  it("searching: primary Match, but NO start-searching menu item", async () => {
    reports([makeLrReport({ status: "searching" })]);
    render();
    await screen.findByRole("button", { name: "Match" });
    openMenu();
    expect(
      screen.queryByRole("menuitem", { name: "Start searching" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Cancel report" })).toBeInTheDocument();
  });

  it("matched: primary Hand over plus an Unmatch menu item, and the matched summary", async () => {
    reports([
      makeLrReport({
        status: "matched",
        matched_found_item: 9,
        matched_found_item_summary: { item_number: "LF00009", title: "Silver phone" },
      }),
    ]);
    render();
    expect(await screen.findByRole("button", { name: "Hand over" })).toBeInTheDocument();
    expect(screen.getByText("LF00009")).toBeInTheDocument();
    expect(screen.getByText(/Silver phone/)).toBeInTheDocument();

    openMenu();
    expect(screen.getByRole("menuitem", { name: "Unmatch" })).toBeInTheDocument();
  });

  it("terminal (returned): no primary and no menu", async () => {
    reports([makeLrReport({ status: "returned" })]);
    render();
    await screen.findByText("Blue backpack");
    expect(screen.queryByRole("button", { name: "Match" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hand over" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More" })).not.toBeInTheDocument();
  });

  it("permission gate: without status_update there is no primary or menu", async () => {
    access.set(["lost_found.create"]);
    reports([makeLrReport({ status: "open" })]);
    render();
    await screen.findByText("Blue backpack");
    expect(screen.queryByRole("button", { name: "Match" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More" })).not.toBeInTheDocument();
  });
});

describe("LostReportsSection — the manual MATCH flow", () => {
  it("loads candidates for the report's category and submits matchLostReport", async () => {
    reports([makeLrReport({ status: "searching", category: "electronics" })]);
    vi.mocked(listLostReportCandidates).mockResolvedValue([
      makeLfItem({ id: 9, item_number: "LF00009", title: "Silver phone", category: "electronics" }),
    ]);
    render();
    await screen.findByText("Blue backpack");

    fireEvent.click(screen.getByRole("button", { name: "Match" }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByText("Silver phone");
    expect(listLostReportCandidates).toHaveBeenCalledWith(1, {
      search: undefined,
      category: "electronics",
    });

    // Each Select now carries an item-specific accessible name (a11y M-1).
    fireEvent.click(within(dialog).getByRole("button", { name: /Select: Silver phone/ }));
    await waitFor(() => expect(matchLostReport).toHaveBeenCalledWith(1, 9));
  });

  it("surfaces a 409 already-matched conflict as an error toast", async () => {
    reports([makeLrReport({ status: "searching" })]);
    vi.mocked(listLostReportCandidates).mockResolvedValue([
      makeLfItem({ id: 9, item_number: "LF00009", title: "Silver phone" }),
    ]);
    vi.mocked(matchLostReport).mockRejectedValue(
      apiError("found_item_already_matched", 409),
    );
    render();
    await screen.findByText("Blue backpack");

    fireEvent.click(screen.getByRole("button", { name: "Match" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(
      await within(dialog).findByRole("button", { name: /Select: Silver phone/ }),
    );

    expect(
      await screen.findByText(/already matched to another lost report/),
    ).toBeInTheDocument();
  });

  it("shows a distinct error state (with retry) when the candidate fetch fails", async () => {
    reports([makeLrReport({ status: "searching" })]);
    vi.mocked(listLostReportCandidates).mockRejectedValue(apiError("server_error", 500));
    render();
    await screen.findByText("Blue backpack");

    fireEvent.click(screen.getByRole("button", { name: "Match" }));
    const dialog = await screen.findByRole("dialog");

    // A real error surface (Retry), NOT the "no matches" empty state.
    const retry = await within(dialog).findByRole("button", { name: "Retry" });
    expect(
      within(dialog).queryByText("No matching found items."),
    ).not.toBeInTheDocument();

    vi.mocked(listLostReportCandidates).mockResolvedValue([
      makeLfItem({ id: 9, item_number: "LF00009", title: "Silver phone" }),
    ]);
    fireEvent.click(retry);
    await within(dialog).findByText("Silver phone");
  });

  it("lets staff clear the seeded category to search across all categories", async () => {
    reports([makeLrReport({ status: "searching", category: "electronics" })]);
    vi.mocked(listLostReportCandidates).mockResolvedValue([
      makeLfItem({ id: 9, item_number: "LF00009", title: "Silver phone" }),
    ]);
    render();
    await screen.findByText("Blue backpack");

    fireEvent.click(screen.getByRole("button", { name: "Match" }));
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByText("Silver phone");

    // Clear the seeded category → a refetch with NO category filter.
    fireEvent.change(within(dialog).getByLabelText("Category"), {
      target: { value: "" },
    });
    await waitFor(() =>
      expect(
        vi
          .mocked(listLostReportCandidates)
          .mock.calls.some(([id, p]) => id === 1 && p?.category === undefined),
      ).toBe(true),
    );
  });
});

describe("LostReportsSection — handover / unmatch / close / cancel", () => {
  it("hands over the matched item", async () => {
    reports([
      makeLrReport({
        status: "matched",
        matched_found_item: 9,
        matched_found_item_summary: { item_number: "LF00009", title: "Silver phone" },
      }),
    ]);
    render();
    fireEvent.click(await screen.findByRole("button", { name: "Hand over" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.change(within(dialog).getByLabelText("Recipient name"), {
      target: { value: "Sara Owner" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Hand over" }));
    await waitFor(() =>
      expect(handoverLostReport).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ recipient_name: "Sara Owner" }),
      ),
    );
  });

  it("requires a reason then unmatches", async () => {
    reports([
      makeLrReport({
        status: "matched",
        matched_found_item: 9,
        matched_found_item_summary: { item_number: "LF00009", title: "Silver phone" },
      }),
    ]);
    render();
    await screen.findByText("Blue backpack");
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Unmatch" }));
    const dialog = await screen.findByRole("dialog");

    // Empty reason is blocked (no API call).
    fireEvent.click(within(dialog).getByRole("button", { name: "Unmatch" }));
    expect(unmatchLostReport).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByLabelText("Reason"), {
      target: { value: "wrong item" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Unmatch" }));
    await waitFor(() => expect(unmatchLostReport).toHaveBeenCalledWith(1, "wrong item"));
  });

  it("closes an open report as not found", async () => {
    reports([makeLrReport({ status: "open" })]);
    render();
    await screen.findByText("Blue backpack");
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Close as not found" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Reason"), {
      target: { value: "never recovered" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Close as not found" }));
    await waitFor(() =>
      expect(closeUnfoundLostReport).toHaveBeenCalledWith(1, "never recovered"),
    );
  });

  it("cancels a report", async () => {
    reports([makeLrReport({ status: "open" })]);
    render();
    await screen.findByText("Blue backpack");
    openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Cancel report" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Reason"), {
      target: { value: "duplicate" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel report" }));
    await waitFor(() => expect(cancelLostReport).toHaveBeenCalledWith(1, "duplicate"));
  });
});

describe("LostReportsSection — a11y focus restore", () => {
  it("moves focus to the results anchor after start-searching drops the card", async () => {
    reports([makeLrReport({ status: "open" })], 1);
    render();
    await screen.findByText("Blue backpack");

    openMenu();
    // After the action the list settles empty, dropping the acting card.
    vi.mocked(listLostReports).mockResolvedValue(page([]));
    vi.mocked(setLostReportStatus).mockResolvedValue({} as never);
    fireEvent.click(screen.getByRole("menuitem", { name: "Start searching" }));

    await screen.findByText("No lost reports");
    await waitFor(() => expect(setLostReportStatus).toHaveBeenCalledWith(1, "searching"));
    expect(document.activeElement).not.toBe(document.body);
    expect(document.activeElement).toHaveClass("op-results");
  });
});
