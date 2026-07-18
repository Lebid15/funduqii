import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Reservation-wizard GuestStep (MANDATE W7, list item 4). Drives the debounced
 * smart lookup through a mocked API and asserts the a11y contract: the lookup
 * OUTCOME is announced via a polite live region (none / single / multiple), an
 * id↔phone conflict is surfaced assertively and NOT double-announced, a ban is
 * surfaced, there is no standalone create-guest control, and identifiers render
 * left-to-right.
 */

vi.mock("@/lib/api/guests", () => ({
  lookupGuest: vi.fn(),
}));

import { lookupGuest } from "@/lib/api/guests";
import type {
  GuestDraft,
  ReservationDraftActions,
} from "../useReservationDraft";
import { createInitialDraft } from "../useReservationDraft";
import { GuestStep } from "../GuestStep";
import { makeGuest, renderWithProviders } from "@/test-utils";

const LONG_TIMEOUT = { timeout: 3000 };

function makeGuestDraft(overrides: Partial<GuestDraft> = {}): GuestDraft {
  return { ...createInitialDraft().guest, ...overrides };
}

function stubActions(): ReservationDraftActions {
  return {
    reset: vi.fn(),
    setGuestField: vi.fn(),
    setNoEmail: vi.fn(),
    applyGuestMatch: vi.fn(),
    unlinkGuest: vi.fn(),
    setHasCompanions: vi.fn(),
    setGroupType: vi.fn(),
    addOccupant: vi.fn(),
    removeOccupant: vi.fn(),
    setOccupantField: vi.fn(),
    setOccupantRelationship: vi.fn(),
    applyOccupantMatch: vi.fn(),
    unlinkOccupant: vi.fn(),
    setChildren: vi.fn(),
    patchBooking: vi.fn(),
    setRoomMode: vi.fn(),
    patchPayment: vi.fn(),
    setDocuments: vi.fn(),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("GuestStep — lookup announcements", () => {
  it("announces NONE via a polite live region", async () => {
    vi.mocked(lookupGuest).mockResolvedValue({ results: [] });
    renderWithProviders(
      <GuestStep guest={makeGuestDraft({ national_id: "12345" })} actions={stubActions()} />,
    );
    expect(
      await screen.findByText(
        "No matching guest found — a new guest will be created.",
        {},
        LONG_TIMEOUT,
      ),
    ).toBeInTheDocument();
    // The discreet visible "new guest" hint is also shown.
    expect(
      screen.getByText("No match — a new guest will be created."),
    ).toBeInTheDocument();
  });

  it("announces a SINGLE match and auto-imports it when nothing was typed", async () => {
    const actions = stubActions();
    vi.mocked(lookupGuest).mockResolvedValue({ results: [makeGuest({ id: 1 })] });
    renderWithProviders(
      <GuestStep guest={makeGuestDraft({ national_id: "12345" })} actions={actions} />,
    );
    expect(
      await screen.findByText("One matching guest found.", {}, LONG_TIMEOUT),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(actions.applyGuestMatch).toHaveBeenCalledWith(
        expect.objectContaining({ id: 1 }),
      ),
    );
  });

  it("announces MULTIPLE matches with the count and renders LTR identifiers", async () => {
    vi.mocked(lookupGuest).mockResolvedValue({
      results: [
        makeGuest({ id: 1, full_name: "Ali One", phone: "0555000011" }),
        makeGuest({ id: 2, full_name: "Ali Two", phone: "0555000022" }),
      ],
    });
    const { container } = renderWithProviders(
      <GuestStep guest={makeGuestDraft({ national_id: "12345" })} actions={stubActions()} />,
    );
    expect(
      await screen.findByText("2 matching guests found.", {}, LONG_TIMEOUT),
    ).toBeInTheDocument();
    // Two pickable matches.
    expect(
      screen.getAllByRole("button", { name: /Use this guest/ }),
    ).toHaveLength(2);
    // Identifiers render inside an LTR <bdi> so RTL never reorders their digits.
    const ltr = Array.from(container.querySelectorAll('bdi[dir="ltr"]')).map(
      (n) => n.textContent,
    );
    expect(ltr).toContain("0555000011");
  });
});

describe("GuestStep — conflict", () => {
  it("surfaces an id↔phone conflict assertively and does NOT double-announce it", async () => {
    // The id resolves to one guest, the phone to a DIFFERENT guest.
    vi.mocked(lookupGuest).mockImplementation((params) => {
      if (params.national_id) return Promise.resolve({ results: [makeGuest({ id: 1 })] });
      if (params.phone) return Promise.resolve({ results: [makeGuest({ id: 2 })] });
      return Promise.resolve({ results: [] });
    });

    const { container } = renderWithProviders(
      <GuestStep
        guest={makeGuestDraft({ national_id: "111", phone: "222" })}
        actions={stubActions()}
      />,
    );

    const conflict =
      "This ID and phone belong to two different guests — nothing was imported. Check the ID and phone before continuing.";

    // The conflict is spoken by an ASSERTIVE alert region.
    const alert = await screen.findByRole("alert", {}, LONG_TIMEOUT);
    expect(alert).toHaveTextContent(conflict);

    // The visible warning is aria-hidden, so its own polite status can never
    // re-announce the text the assertive region already spoke.
    const politeRegions = Array.from(
      container.querySelectorAll('p[aria-live="polite"]'),
    );
    expect(politeRegions.length).toBeGreaterThan(0);
    for (const region of politeRegions) {
      expect(region.textContent ?? "").not.toContain(conflict);
    }
  });
});

describe("GuestStep — ban + create-control absence", () => {
  it("surfaces a ban on a matched candidate", async () => {
    // Typed data present → the single match is NOT auto-imported; it is offered as
    // a pickable candidate that clearly carries the blocked badge.
    vi.mocked(lookupGuest).mockResolvedValue({
      results: [makeGuest({ id: 9, full_name: "Blocked Guest", is_blocked: true })],
    });
    renderWithProviders(
      <GuestStep
        guest={makeGuestDraft({ national_id: "12345", first_name: "Typed" })}
        actions={stubActions()}
      />,
    );
    const match = await screen.findByText("Blocked Guest", {}, LONG_TIMEOUT);
    const row = match.closest(".line-row") as HTMLElement;
    expect(within(row).getByText("Blocked")).toBeInTheDocument();
  });

  it("exposes NO standalone create-guest control", async () => {
    vi.mocked(lookupGuest).mockResolvedValue({ results: [] });
    renderWithProviders(
      <GuestStep guest={makeGuestDraft({ national_id: "12345" })} actions={stubActions()} />,
    );
    await screen.findByText(
      "No matching guest found — a new guest will be created.",
      {},
      LONG_TIMEOUT,
    );
    expect(
      screen.queryByRole("button", { name: /create guest|new guest|add guest/i }),
    ).not.toBeInTheDocument();
  });
});
