import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
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
  apiError,
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
  /** Non-empty `search` terms sent to the directory endpoint so far. */
  const searchTerms = () =>
    vi
      .mocked(listGuestDirectory)
      .mock.calls.map(([params]) => params?.search)
      .filter((s): s is string => Boolean(s));

  it("forwards the typed term verbatim to the directory endpoint (Enter)", async () => {
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

  it("updates results automatically as the user types — no Enter needed", async () => {
    vi.mocked(listGuestDirectory).mockImplementation((params) =>
      Promise.resolve(
        page([
          makeDirectoryRow({
            id: params?.search === "Bob" ? 9 : 7,
            full_name: params?.search === "Bob" ? "Bob Stone" : "Ali Hassan",
          }),
        ]),
      ),
    );
    renderWithProviders(<GuestsPanel />);
    await screen.findByText("Ali Hassan");

    const input = screen.getByLabelText("Search");
    // Type WITHOUT submitting the form (no Enter, no button click).
    fireEvent.change(input, { target: { value: "Bob" } });

    // The debounced live search refetches on its own.
    expect(await screen.findByText("Bob Stone")).toBeInTheDocument();
    expect(
      vi
        .mocked(listGuestDirectory)
        .mock.calls.some(([params]) => params?.search === "Bob"),
    ).toBe(true);
  });

  it("debounces rapid keystrokes into a single request (no per-character call)", async () => {
    renderWithProviders(<GuestsPanel />);
    await screen.findByText("Ali Hassan");

    const input = screen.getByLabelText("Search");
    // Three quick keystrokes within one debounce window.
    fireEvent.change(input, { target: { value: "B" } });
    fireEvent.change(input, { target: { value: "Bo" } });
    fireEvent.change(input, { target: { value: "Bob" } });

    await waitFor(() => expect(searchTerms()).toContain("Bob"));
    // The intermediate terms never reached the endpoint — only the settled value.
    expect(searchTerms()).not.toContain("B");
    expect(searchTerms()).not.toContain("Bo");
    expect(searchTerms().filter((s) => s === "Bob")).toHaveLength(1);
  });

  it("resets pagination to page 1 when a new search begins", async () => {
    // count > PAGE_SIZE so Pagination renders and page 2 is reachable.
    vi.mocked(listGuestDirectory).mockImplementation(() =>
      Promise.resolve(page([makeDirectoryRow({ full_name: "Ali Hassan" })], 100)),
    );
    renderWithProviders(<GuestsPanel />);
    await screen.findByText("Ali Hassan");

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(
        vi.mocked(listGuestDirectory).mock.calls.some(([p]) => p?.page === 2),
      ).toBe(true),
    );

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "Ali" },
    });
    await waitFor(() =>
      expect(
        vi
          .mocked(listGuestDirectory)
          .mock.calls.some(([p]) => p?.search === "Ali" && p?.page === 1),
      ).toBe(true),
    );
  });

  it("clears the search and refetches ALL guests when the box is emptied", async () => {
    renderWithProviders(<GuestsPanel />);
    await screen.findByText("Ali Hassan");

    const input = screen.getByLabelText("Search");
    fireEvent.change(input, { target: { value: "Ali" } });
    await waitFor(() => expect(searchTerms()).toContain("Ali"));

    fireEvent.change(input, { target: { value: "" } });
    await waitFor(() => {
      const last = vi.mocked(listGuestDirectory).mock.calls.at(-1);
      // Empty term → no `search` param (the full list) AND back to page 1.
      expect(last?.[0]?.search).toBeUndefined();
      expect(last?.[0]?.page).toBe(1);
    });
  });

  it("preserves the search term when showInactive is toggled", async () => {
    renderWithProviders(<GuestsPanel />);
    await screen.findByText("Ali Hassan");

    const input = screen.getByLabelText("Search");
    fireEvent.change(input, { target: { value: "Ali" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);
    await waitFor(() => expect(searchTerms()).toContain("Ali"));

    fireEvent.click(screen.getByRole("switch", { name: "Show inactive" }));
    await waitFor(() =>
      expect(
        vi
          .mocked(listGuestDirectory)
          .mock.calls.some(
            ([p]) => p?.search === "Ali" && p?.is_active === undefined,
          ),
      ).toBe(true),
    );
  });

  it("forwards a national_id-style term verbatim — no client transformation", async () => {
    renderWithProviders(<GuestsPanel />);
    await screen.findByText("Ali Hassan");

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "1234567890" },
    });
    await waitFor(() => expect(searchTerms()).toContain("1234567890"));
    // Every non-empty term the client sent is EXACTLY what was typed (no partial,
    // no normalisation, no identity-oracle variant).
    searchTerms().forEach((s) => expect(s).toBe("1234567890"));
  });

  it("runs live search under an RTL (ar) locale", async () => {
    const { container } = renderWithProviders(<GuestsPanel />, { locale: "ar" });
    await screen.findByText("Ali Hassan");

    // Query by stable id (the label text is localised).
    const input = container.querySelector("#guest-search") as HTMLInputElement;
    expect(input).not.toBeNull();
    fireEvent.change(input, { target: { value: "علي" } });
    await waitFor(() => expect(searchTerms()).toContain("علي"));
  });

  it("aborts the previous in-flight request when a newer search starts", async () => {
    const signals: AbortSignal[] = [];
    vi.mocked(listGuestDirectory).mockImplementation((_params, signal) => {
      if (signal) signals.push(signal);
      // Never resolves — the request stays in-flight until it is aborted.
      return new Promise(() => {});
    });
    renderWithProviders(<GuestsPanel />);
    await waitFor(() => expect(signals.length).toBe(1));

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "Ali" },
    });
    await waitFor(() => expect(signals.length).toBe(2));

    // The superseded initial request was aborted; the newest one is live.
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
  });

  it("ignores a stale response that resolves after a newer one", async () => {
    const resolvers: Array<(v: unknown) => void> = [];
    vi.mocked(listGuestDirectory).mockImplementation(
      () => new Promise((resolve) => resolvers.push(resolve)),
    );
    renderWithProviders(<GuestsPanel />);
    await waitFor(() => expect(resolvers.length).toBe(1));

    // Initial load resolves with Ali.
    await act(async () => {
      resolvers[0](page([makeDirectoryRow({ id: 1, full_name: "Ali Hassan" })]));
    });
    await screen.findByText("Ali Hassan");

    const input = screen.getByLabelText("Search");
    // First search ("stale") fires and stays in-flight…
    fireEvent.change(input, { target: { value: "stale" } });
    await waitFor(() => expect(resolvers.length).toBe(2));
    // …then a newer search ("fresh") supersedes it.
    fireEvent.change(input, { target: { value: "fresh" } });
    await waitFor(() => expect(resolvers.length).toBe(3));

    // Resolve the NEWEST first, then the stale one.
    await act(async () => {
      resolvers[2](page([makeDirectoryRow({ id: 3, full_name: "Fresh Guest" })]));
    });
    await screen.findByText("Fresh Guest");
    await act(async () => {
      resolvers[1](page([makeDirectoryRow({ id: 2, full_name: "Stale Guest" })]));
    });

    // The stale response must NEVER overwrite the newer one.
    expect(screen.queryByText("Stale Guest")).not.toBeInTheDocument();
    expect(screen.getByText("Fresh Guest")).toBeInTheDocument();
  });
});

describe("GuestsPanel — loading / refetch feedback", () => {
  it("keeps the current cards mounted during a background refetch (no flicker)", async () => {
    const resolvers: Array<(v: unknown) => void> = [];
    vi.mocked(listGuestDirectory).mockImplementation(
      () => new Promise((resolve) => resolvers.push(resolve)),
    );
    renderWithProviders(<GuestsPanel />);
    await waitFor(() => expect(resolvers.length).toBe(1));
    await act(async () => {
      resolvers[0](page([makeDirectoryRow({ full_name: "Ali Hassan" })]));
    });
    await screen.findByText("Ali Hassan");

    // Start a live search → a BACKGROUND refetch begins.
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "x" } });
    await waitFor(() => expect(resolvers.length).toBe(2));

    // The existing card stays mounted (not swapped for the full-screen loader),
    // a subtle inline "Searching…" status shows, and the list is marked busy.
    expect(screen.getByText("Ali Hassan")).toBeInTheDocument();
    expect(screen.getByText("Searching…")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Guests" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("shows the error state with a retry that recovers", async () => {
    vi.mocked(listGuestDirectory).mockRejectedValueOnce(
      apiError("server_error", 500),
    );
    renderWithProviders(<GuestsPanel />);

    const retry = await screen.findByRole("button", { name: "Retry" });
    expect(screen.getByText("Could not load data")).toBeInTheDocument();

    // Recover on retry.
    vi.mocked(listGuestDirectory).mockResolvedValue(
      page([makeDirectoryRow({ full_name: "Ali Hassan" })]),
    );
    fireEvent.click(retry);
    await screen.findByText("Ali Hassan");
    expect(
      screen.queryByRole("button", { name: "Retry" }),
    ).not.toBeInTheDocument();
  });
});

describe("GuestsPanel — R5 polish (non-blocking refetch / no flicker / a11y)", () => {
  // FIX A — a BACKGROUND refetch error must NOT wipe the visible list.
  it("keeps loaded cards mounted on a BACKGROUND refetch error and surfaces a toast (no full ErrorState)", async () => {
    const controllers: Array<{
      resolve: (v: unknown) => void;
      reject: (e: unknown) => void;
    }> = [];
    vi.mocked(listGuestDirectory).mockImplementation(
      () =>
        new Promise((resolve, reject) => controllers.push({ resolve, reject })),
    );
    renderWithProviders(<GuestsPanel />);
    await waitFor(() => expect(controllers.length).toBe(1));

    // Initial load succeeds with one card.
    await act(async () => {
      controllers[0].resolve(page([makeDirectoryRow({ full_name: "Ali Hassan" })]));
    });
    await screen.findByText("Ali Hassan");

    // A live search fires a BACKGROUND refetch…
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "zzz" } });
    await waitFor(() => expect(controllers.length).toBe(2));

    // …which fails on a NON-abort error.
    await act(async () => {
      controllers[1].reject(apiError("server_error", 500));
    });

    // The previously-loaded card STAYS mounted (good results are not wiped)…
    expect(screen.getByText("Ali Hassan")).toBeInTheDocument();
    // …the full-screen ErrorState / retry is NOT shown (reserved for initial load)…
    expect(
      screen.queryByRole("button", { name: "Retry" }),
    ).not.toBeInTheDocument();
    // …and the error is surfaced NON-BLOCKINGLY as an error toast.
    await waitFor(() => {
      const toast = document.querySelector(".toast--error");
      expect(toast).not.toBeNull();
      expect(toast?.textContent).toContain("Something went wrong. Please try again.");
    });
  });

  // FIX A — an INITIAL-load error still shows the full ErrorState with a working
  // retry (the background path above must not have broken the initial path).
  it("still shows the full ErrorState with a working retry on an INITIAL-load error", async () => {
    vi.mocked(listGuestDirectory).mockRejectedValueOnce(
      apiError("server_error", 500),
    );
    renderWithProviders(<GuestsPanel />);

    const retry = await screen.findByRole("button", { name: "Retry" });
    expect(screen.getByText("Could not load data")).toBeInTheDocument();
    // No transient toast on the INITIAL failure — the blocking surface owns it.
    expect(document.querySelector(".toast--error")).toBeNull();

    vi.mocked(listGuestDirectory).mockResolvedValue(
      page([makeDirectoryRow({ full_name: "Ali Hassan" })]),
    );
    fireEvent.click(retry);
    await screen.findByText("Ali Hassan");
    expect(
      screen.queryByRole("button", { name: "Retry" }),
    ).not.toBeInTheDocument();
  });

  // FIX B — once results exist, no full-loader flicker even when a search narrows
  // to zero: the EmptyState stays and a later keystroke never mounts LoadingState.
  it("keeps the EmptyState (never the full loader) for a zero-result search after a first load", async () => {
    vi.mocked(listGuestDirectory).mockImplementation((params) =>
      params?.search
        ? Promise.resolve(page([]))
        : Promise.resolve(page([makeDirectoryRow({ full_name: "Ali Hassan" })])),
    );
    renderWithProviders(<GuestsPanel />);
    await screen.findByText("Ali Hassan");

    // A search that returns zero rows shows the EmptyState, NOT the full loader.
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "zzz" } });
    await screen.findByText("No guests yet");
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();

    // A subsequent keystroke triggers another refetch but STILL never mounts the
    // full-screen LoadingState — the EmptyState remains.
    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "zzzq" },
    });
    await waitFor(() =>
      expect(
        vi
          .mocked(listGuestDirectory)
          .mock.calls.some(([p]) => p?.search === "zzzq"),
      ).toBe(true),
    );
    expect(screen.queryByText("Loading…")).not.toBeInTheDocument();
    expect(screen.getByText("No guests yet")).toBeInTheDocument();
  });

  // FIX C — a STABLE polite live region announces the settled result state.
  it("exposes a stable results live region that announces the count / no-results on settle", async () => {
    vi.mocked(listGuestDirectory).mockImplementation((params) => {
      if (params?.search === "none") return Promise.resolve(page([], 0));
      return Promise.resolve(
        page(
          [
            makeDirectoryRow({ id: 1, full_name: "Ali Hassan" }),
            makeDirectoryRow({ id: 2, full_name: "Bob Stone" }),
          ],
          2,
        ),
      );
    });
    renderWithProviders(<GuestsPanel />);

    // The live region exists from the FIRST render (stable, before any search) and
    // is blank while the initial load is still in flight (no mount-with-content).
    const region = screen.getByTestId("guest-results-announce");
    expect(region).toBeInTheDocument();
    expect(region).toHaveTextContent("");

    // After the initial load settles it announces the count.
    await screen.findByText("Ali Hassan");
    await waitFor(() => expect(region).toHaveTextContent("2 results"));

    // A zero-result search updates the SAME region to the no-results message.
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "none" } });
    await waitFor(() => expect(region).toHaveTextContent("No results"));
    // It is the same element throughout (never remounted).
    expect(screen.getByTestId("guest-results-announce")).toBe(region);
  });

  // FIX D — the "searching…" cue lives in an always-present reserved row so it
  // never reflows the grid; role=status stays stable.
  it("keeps the searching-cue row reserved and stable (no reflow of the grid)", async () => {
    const resolvers: Array<(v: unknown) => void> = [];
    vi.mocked(listGuestDirectory).mockImplementation(
      () => new Promise((resolve) => resolvers.push(resolve)),
    );
    const { container } = renderWithProviders(<GuestsPanel />);
    await waitFor(() => expect(resolvers.length).toBe(1));
    await act(async () => {
      resolvers[0](page([makeDirectoryRow({ full_name: "Ali Hassan" })]));
    });
    await screen.findByText("Ali Hassan");

    // The reserved status row is ALWAYS present (even idle, before any search) and
    // empty when nothing is refetching.
    const statusRow = container.querySelector(".guest-results__status");
    expect(statusRow).not.toBeNull();
    expect(statusRow?.textContent).toBe("");

    // A background refetch fills the SAME reserved row with the cue — no new row
    // is inserted above the grid (so the grid never shifts down).
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "x" } });
    await waitFor(() => expect(resolvers.length).toBe(2));
    expect(container.querySelectorAll(".guest-results__status")).toHaveLength(1);
    expect(screen.getByText("Searching…")).toBeInTheDocument();
    expect(statusRow?.textContent).toContain("Searching…");
    // The card is still mounted below the (unchanged) reserved row.
    expect(screen.getByText("Ali Hassan")).toBeInTheDocument();
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
