import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * GuestsPanel (MANDATE W7, list item 2). Verifies the panel renders a CARD GRID
 * (never a DataTable), exposes NO standalone "add guest" control, forwards the
 * search term verbatim to the directory endpoint, and — through the real edit
 * flow — never re-sends a server-masked document number.
 *
 * The API layer and the cosmetic hotel-access gate are mocked so the test is
 * deterministic (no network, no timers).
 */

// --- Mutable cosmetic-permission gate (hoisted so the vi.mock factory sees it) --
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

vi.mock("@/lib/api/guests", () => ({
  listGuestDirectory: vi.fn(),
  getGuestProfile: vi.fn(),
  setGuestVip: vi.fn(),
  blockGuest: vi.fn(),
  unblockGuest: vi.fn(),
  updateGuest: vi.fn(),
  deleteGuest: vi.fn(),
  listGuestStays: vi.fn(),
  listGuestReservations: vi.fn(),
  listGuestDocuments: vi.fn(),
  listGuestChangeLog: vi.fn(),
}));

import {
  getGuestProfile,
  listGuestDirectory,
  listGuestReservations,
  listGuestStays,
  updateGuest,
} from "@/lib/api/guests";
import type { PaginatedResponse } from "@/lib/api/types";
import { GuestsPanel } from "../GuestsPanel";
import {
  makeDirectoryRow,
  makeProfile,
  renderWithProviders,
} from "@/test-utils";

function page<T>(results: T[], count = results.length): PaginatedResponse<T> {
  return { count, next: null, previous: null, results };
}

beforeEach(() => {
  vi.clearAllMocks();
  access.set(["guests.update"]);
  vi.mocked(listGuestDirectory).mockResolvedValue(
    page([makeDirectoryRow({ id: 7, full_name: "Ali Hassan" })]),
  );
});

describe("GuestsPanel — layout", () => {
  it("renders a card grid (role=list), never a DataTable", async () => {
    renderWithProviders(<GuestsPanel />);
    const list = await screen.findByRole("list", { name: "Guests" });
    expect(list).toBeInTheDocument();
    within(list).getByText("Ali Hassan");
    // A DataTable would expose role=table — the directory must not.
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("exposes NO standalone add/create-guest control", async () => {
    renderWithProviders(<GuestsPanel />);
    await screen.findByText("Ali Hassan");
    expect(
      screen.queryByRole("button", { name: /new guest|add guest|create guest/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("New guest")).not.toBeInTheDocument();
  });
});

describe("GuestsPanel — search", () => {
  it("forwards the typed term verbatim to the directory endpoint", async () => {
    renderWithProviders(<GuestsPanel />);
    await screen.findByText("Ali Hassan");

    const input = screen.getByLabelText("Search");
    fireEvent.change(input, { target: { value: "Ali" } });
    const form = input.closest("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);

    await waitFor(() =>
      expect(
        vi
          .mocked(listGuestDirectory)
          .mock.calls.some(([params]) => params?.search === "Ali"),
      ).toBe(true),
    );
  });
});

describe("GuestsPanel — no comprehensive profile", () => {
  it("renders no 'view profile' control and no aggregated profile modal", async () => {
    access.set(["guests.update", "stays.view", "reservations.view"]);
    renderWithProviders(<GuestsPanel />);
    await screen.findByText("Ali Hassan");
    expect(
      screen.queryByRole("button", { name: /view profile|open profile/i }),
    ).not.toBeInTheDocument();
    // The removed profile modal titled its surface "Guest profile".
    expect(screen.queryByText("Guest profile")).not.toBeInTheDocument();
    // getGuestProfile is only fetched lazily when the edit form opens — not on load.
    expect(getGuestProfile).not.toHaveBeenCalled();
  });
});

describe("GuestsPanel — card icons open sub-modals directly", () => {
  it("opens the stays history modal from the bed icon", async () => {
    access.set(["stays.view"]);
    vi.mocked(listGuestStays).mockResolvedValue(page([]));
    renderWithProviders(<GuestsPanel />);
    const btn = await screen.findByRole("button", {
      name: "Stay history — Ali Hassan",
    });
    fireEvent.click(btn);
    expect(await screen.findByText("Stays · Ali Hassan")).toBeInTheDocument();
    await waitFor(() => expect(listGuestStays).toHaveBeenCalled());
  });

  it("opens the reservations history modal from the calendar icon", async () => {
    access.set(["reservations.view"]);
    vi.mocked(listGuestReservations).mockResolvedValue(page([]));
    renderWithProviders(<GuestsPanel />);
    const btn = await screen.findByRole("button", {
      name: "Reservation history — Ali Hassan",
    });
    fireEvent.click(btn);
    expect(
      await screen.findByText("Reservations · Ali Hassan"),
    ).toBeInTheDocument();
    await waitFor(() => expect(listGuestReservations).toHaveBeenCalled());
  });

  it("opens the personal-data edit modal from the pencil icon", async () => {
    access.set(["guests.update"]);
    vi.mocked(getGuestProfile).mockResolvedValue(
      makeProfile({ id: 7, full_name: "Ali Hassan" }),
    );
    renderWithProviders(<GuestsPanel />);
    const editBtn = await screen.findByRole("button", {
      name: "Edit — Ali Hassan",
    });
    fireEvent.click(editBtn);
    // The personal-data edit form opens once the record loads (its stable field).
    await screen.findByLabelText("Full name");
    expect(
      screen.getByRole("heading", { name: "Edit guest" }),
    ).toBeInTheDocument();
    // Personal-data form only — no reservations/stays/folio/documents/change-log.
    expect(screen.queryByText("Stay history")).not.toBeInTheDocument();
    expect(getGuestProfile).toHaveBeenCalledWith(7);
  });
});

describe("GuestsPanel — masked document never re-sent", () => {
  it("omits a server-masked document number when saving an unchanged edit", async () => {
    vi.mocked(getGuestProfile).mockResolvedValue(
      makeProfile({
        id: 7,
        full_name: "Ali Hassan",
        document_number: "••••1234",
        document_type: "national_id",
      }),
    );
    vi.mocked(updateGuest).mockResolvedValue(
      // The return value is not asserted on; a minimal cast keeps it typed.
      makeProfile({ id: 7 }) as never,
    );

    renderWithProviders(<GuestsPanel />);
    const editBtn = await screen.findByRole("button", {
      name: "Edit — Ali Hassan",
    });
    fireEvent.click(editBtn);

    // The edit form opens once the profile has loaded.
    await screen.findByRole("heading", { name: "Edit guest" });

    // The editable document field is BLANK — the masked value is only a
    // placeholder, never echoed into the input.
    const nameInput = (await screen.findByLabelText(
      "Full name",
    )) as HTMLInputElement;
    const docInput = screen.getByLabelText("Document number") as HTMLInputElement;
    await waitFor(() => expect(nameInput.value).toBe("Ali Hassan"));
    expect(docInput.value).toBe("");

    // Submit the edit untouched.
    const form = nameInput.closest("form") as HTMLFormElement | null;
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);

    await waitFor(() => expect(updateGuest).toHaveBeenCalledTimes(1));
    const [, body] = vi.mocked(updateGuest).mock.calls[0];
    expect(body).not.toHaveProperty("document_number");
    expect(body).not.toHaveProperty("document_type");
    // The unrelated fields still round-trip.
    expect(body.full_name).toBe("Ali Hassan");
  });
});
