import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * LostFoundTab (WP12 / owner §17: stored_location on the card, handover requiring
 * a recipient name + phone-OR-linked-guest, SENSITIVE proof fields required for
 * money / jewelry / documents, the phone + proof reference NEVER on the card, and
 * a 422 claim_proof_required surfaced as a translated error).
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

import { listLostFoundItems, returnLostFoundItem } from "@/lib/api/operations";
import { listRoomOptions } from "@/lib/api/rooms";
import { listGuests } from "@/lib/api/guests";
import type { PaginatedResponse } from "@/lib/api/types";
import { LostFoundTab } from "../LostFoundTab";
import { apiError, makeLfItem, renderWithProviders } from "@/test-utils";

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

function items(rows: ReturnType<typeof makeLfItem>[], count = rows.length) {
  vi.mocked(listLostFoundItems).mockResolvedValue(page(rows, count));
}

/** Open the return-handover dialog for the (single) stored item on screen. */
async function openReturn() {
  fireEvent.click(await screen.findByRole("button", { name: "Return" }));
  return screen.findByRole("dialog");
}

beforeEach(() => {
  vi.clearAllMocks();
  access.set(["lost_found.status_update", "lost_found.close", "lost_found.create"]);
  vi.mocked(listLostFoundItems).mockResolvedValue(page([]));
  vi.mocked(listRoomOptions).mockResolvedValue(page([]));
  vi.mocked(listGuests).mockResolvedValue(page([]));
});

describe("LostFoundTab — stored location on the card", () => {
  it("shows the item's storage location", async () => {
    items([makeLfItem({ stored_location: "Safe box A", status: "stored" })]);
    renderWithProviders(<LostFoundTab />);
    await screen.findByText("Black leather wallet");
    expect(screen.getByText("Safe box A")).toBeInTheDocument();
  });
});

describe("LostFoundTab — handover (normal category) requires name + phone-or-guest", () => {
  it("rejects an empty handover, then a name-only handover, then accepts name + phone", async () => {
    items([makeLfItem({ status: "stored", category: "other", guest: null })]);
    renderWithProviders(<LostFoundTab />);
    const dialog = await openReturn();

    // Empty → claimant-required error, no API call.
    fireEvent.click(within(dialog).getByRole("button", { name: "Return" }));
    expect(
      await within(dialog).findByText("A claimant name (or linked guest) is required."),
    ).toBeInTheDocument();
    expect(returnLostFoundItem).not.toHaveBeenCalled();

    // Name only (no phone, no linked guest) → still blocked.
    fireEvent.change(within(dialog).getByLabelText("Recipient name"), {
      target: { value: "Ali Owner" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Return" }));
    expect(returnLostFoundItem).not.toHaveBeenCalled();

    // Name + phone → accepted (no proof fields for a non-sensitive item).
    fireEvent.change(within(dialog).getByLabelText("Recipient phone"), {
      target: { value: "0555123456" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Return" }));
    await waitFor(() =>
      expect(returnLostFoundItem).toHaveBeenCalledWith(1, {
        claimed_by_name: "Ali Owner",
        claimed_by_phone: "0555123456",
      }),
    );
  });

  it("accepts a name-only handover when the item has a linked guest (phone optional)", async () => {
    items([
      makeLfItem({ status: "stored", category: "other", guest: 5, guest_name: "Ali Guest" }),
    ]);
    renderWithProviders(<LostFoundTab />);
    const dialog = await openReturn();

    // The linked-guest hint is shown; a phone is not required.
    expect(within(dialog).getByText(/Linked guest/)).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Recipient name"), {
      target: { value: "Ali Guest" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Return" }));
    await waitFor(() => expect(returnLostFoundItem).toHaveBeenCalledTimes(1));
  });
});

describe("LostFoundTab — sensitive categories require ownership proof", () => {
  it("shows the proof fields and requires a reference for a money item", async () => {
    items([makeLfItem({ status: "stored", category: "money", guest: null })]);
    renderWithProviders(<LostFoundTab />);
    const dialog = await openReturn();

    // Proof-of-ownership fields appear ONLY for sensitive categories.
    expect(within(dialog).getByLabelText("Proof of ownership")).toBeInTheDocument();
    const proofRef = within(dialog).getByLabelText("Proof reference");
    expect(proofRef).toBeInTheDocument();

    // Name + phone but no proof reference → the proof-required error blocks it.
    fireEvent.change(within(dialog).getByLabelText("Recipient name"), {
      target: { value: "Ali Owner" },
    });
    fireEvent.change(within(dialog).getByLabelText("Recipient phone"), {
      target: { value: "0555123456" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Return" }));
    expect(
      await within(dialog).findByText("Choose a proof type and enter its reference."),
    ).toBeInTheDocument();
    expect(returnLostFoundItem).not.toHaveBeenCalled();

    // With the proof reference the handover posts the proof type + reference.
    fireEvent.change(proofRef, { target: { value: "ID-1234" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Return" }));
    await waitFor(() =>
      expect(returnLostFoundItem).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          claimed_by_name: "Ali Owner",
          claim_proof_type: "identity_last4",
          claim_proof_reference: "ID-1234",
        }),
      ),
    );
  });

  it("shows NO proof fields for a non-sensitive item", async () => {
    items([makeLfItem({ status: "stored", category: "clothing" })]);
    renderWithProviders(<LostFoundTab />);
    const dialog = await openReturn();
    expect(within(dialog).queryByLabelText("Proof reference")).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Proof of ownership")).not.toBeInTheDocument();
  });
});

describe("LostFoundTab — the card never leaks phone or proof reference", () => {
  it("renders no recipient phone and no proof reference on a sensitive card", async () => {
    items([
      makeLfItem({
        status: "returned",
        category: "money",
        stored_location: "Safe box A",
      }),
    ]);
    const { container } = renderWithProviders(<LostFoundTab />);
    await screen.findByText("Black leather wallet");

    // These are handover-time, authorized fields — they must never appear on the list.
    expect(screen.queryByText("Recipient phone")).not.toBeInTheDocument();
    expect(screen.queryByText("Proof reference")).not.toBeInTheDocument();
    expect(container.textContent ?? "").not.toMatch(/0555\d/);
  });
});

describe("LostFoundTab — 422 claim_proof_required is translated", () => {
  it("surfaces the backend proof-required rejection as a readable message", async () => {
    items([makeLfItem({ status: "stored", category: "jewelry", guest: null })]);
    vi.mocked(returnLostFoundItem).mockRejectedValue(
      apiError("claim_proof_required", 422),
    );
    renderWithProviders(<LostFoundTab />);
    const dialog = await openReturn();

    fireEvent.change(within(dialog).getByLabelText("Recipient name"), {
      target: { value: "Ali Owner" },
    });
    fireEvent.change(within(dialog).getByLabelText("Recipient phone"), {
      target: { value: "0555123456" },
    });
    fireEvent.change(within(dialog).getByLabelText("Proof reference"), {
      target: { value: "REF-9" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Return" }));

    expect(
      await within(dialog).findByText(/This sensitive item can only be handed over with proof of ownership/),
    ).toBeInTheDocument();
  });
});

describe("LostFoundTab — stat filter + states", () => {
  it("applies the found filter from its stat tile", async () => {
    items([makeLfItem()], 3);
    renderWithProviders(<LostFoundTab />);
    await screen.findByText("Black leather wallet");

    fireEvent.click(screen.getByRole("button", { name: /Found/ }));
    await waitFor(() =>
      expect(
        vi.mocked(listLostFoundItems).mock.calls.some(
          ([p]) => p?.status === "found" && "category" in (p ?? {}),
        ),
      ).toBe(true),
    );
  });

  it("shows the loading then empty state", async () => {
    const d = deferred<PaginatedResponse<ReturnType<typeof makeLfItem>>>();
    vi.mocked(listLostFoundItems).mockReturnValue(d.promise);
    renderWithProviders(<LostFoundTab />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    await act(async () => {
      d.resolve(page([]));
    });
    expect(await screen.findByText("No lost & found items")).toBeInTheDocument();
  });

  it("shows an error state with a Retry that recovers", async () => {
    vi.mocked(listLostFoundItems).mockRejectedValue(apiError("server_error", 500));
    renderWithProviders(<LostFoundTab />);
    const retry = await screen.findByRole("button", { name: "Retry" });
    vi.mocked(listLostFoundItems).mockResolvedValue(page([makeLfItem()]));
    fireEvent.click(retry);
    await screen.findByText("Black leather wallet");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});
