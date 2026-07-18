import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The four read-only guest record sub-modals (MANDATE W7, list item 3): REAL
 * server pagination, explicit loading / empty / error+retry states, the
 * documents no-access guard (endpoint never called without
 * reservation_documents.view), and masked values displayed exactly as received.
 */

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

vi.mock("@/lib/api/guests", () => ({
  listGuestStays: vi.fn(),
  listGuestReservations: vi.fn(),
  listGuestDocuments: vi.fn(),
  listGuestChangeLog: vi.fn(),
}));

import {
  listGuestDocuments,
  listGuestStays,
} from "@/lib/api/guests";
import type { PaginatedResponse } from "@/lib/api/types";
import {
  GuestDocumentsModal,
  GuestStaysHistoryModal,
} from "../GuestRecordModals";
import {
  apiError,
  makeDocumentRow,
  makeStayRow,
  renderWithProviders,
} from "@/test-utils";

function envelope<T>(results: T[], count: number): PaginatedResponse<T> {
  return { count, next: null, previous: null, results };
}

/** A manually-resolvable promise, to hold a fetch in flight. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.clearAllMocks();
  access.set(["reservations.view", "finance.view", "reservation_documents.view"]);
});

describe("GuestStaysHistoryModal — real pagination", () => {
  it("fetches page 1 with page_size, then page 2 on Next and shows its rows", async () => {
    const page1 = Array.from({ length: 10 }, (_, i) =>
      makeStayRow({ stay_id: i + 1, room_number: `R2${String(i).padStart(2, "0")}` }),
    );
    const page2 = Array.from({ length: 5 }, (_, i) =>
      makeStayRow({ stay_id: 100 + i, room_number: `R3${String(i).padStart(2, "0")}` }),
    );
    vi.mocked(listGuestStays).mockImplementation((_id, params) =>
      Promise.resolve(
        (params?.page ?? 1) === 1
          ? envelope(page1, 15)
          : envelope(page2, 15),
      ),
    );

    renderWithProviders(
      <GuestStaysHistoryModal
        open
        guestId={7}
        guestName="Ali Hassan"
        onClose={vi.fn()}
      />,
    );

    // Page 1 fetched with the explicit page size.
    await screen.findByText("R200");
    expect(listGuestStays).toHaveBeenCalledWith(7, { page: 1, page_size: 10 });

    // Advance to page 2.
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await screen.findByText("R300");
    await waitFor(() =>
      expect(
        vi.mocked(listGuestStays).mock.calls.some(([, p]) => p?.page === 2),
      ).toBe(true),
    );
    // Page-1 rows are gone once page 2 has loaded.
    expect(screen.queryByText("R200")).not.toBeInTheDocument();
  });
});

describe("GuestStaysHistoryModal — async states", () => {
  it("shows the loading state while the first page is in flight", async () => {
    const d = deferred<PaginatedResponse<ReturnType<typeof makeStayRow>>>();
    vi.mocked(listGuestStays).mockReturnValue(d.promise);

    renderWithProviders(
      <GuestStaysHistoryModal open guestId={7} guestName="Ali" onClose={vi.fn()} />,
    );

    expect(screen.getByRole("status")).toBeInTheDocument();

    d.resolve(envelope([], 0));
    await waitFor(() =>
      expect(screen.queryByRole("status")).not.toBeInTheDocument(),
    );
  });

  it("shows the empty state when there are no rows", async () => {
    vi.mocked(listGuestStays).mockResolvedValue(envelope([], 0));
    renderWithProviders(
      <GuestStaysHistoryModal open guestId={7} guestName="Ali" onClose={vi.fn()} />,
    );
    expect(await screen.findByText("No stays recorded.")).toBeInTheDocument();
  });

  it("shows an error state with a working Retry that refetches", async () => {
    vi.mocked(listGuestStays)
      .mockRejectedValueOnce(apiError("server_error", 500))
      .mockResolvedValueOnce(envelope([makeStayRow({ room_number: "R409" })], 1));

    renderWithProviders(
      <GuestStaysHistoryModal open guestId={7} guestName="Ali" onClose={vi.fn()} />,
    );

    const alert = await screen.findByRole("alert");
    const retry = within(alert).getByRole("button", { name: "Retry" });
    fireEvent.click(retry);

    expect(await screen.findByText("R409")).toBeInTheDocument();
    expect(listGuestStays).toHaveBeenCalledTimes(2);
  });
});

describe("GuestDocumentsModal — reservation_documents.view gate", () => {
  it("shows a no-access state and never calls the endpoint without the permission", async () => {
    access.set([]); // no reservation_documents.view
    renderWithProviders(
      <GuestDocumentsModal open guestId={7} guestName="Ali" onClose={vi.fn()} />,
    );

    expect(
      await screen.findByText("You do not have permission to view documents."),
    ).toBeInTheDocument();
    expect(listGuestDocuments).not.toHaveBeenCalled();
  });

  it("displays a masked document number exactly as received when permitted", async () => {
    access.set(["reservation_documents.view"]);
    vi.mocked(listGuestDocuments).mockResolvedValue(
      envelope([makeDocumentRow({ number: "••••5678" })], 1),
    );

    renderWithProviders(
      <GuestDocumentsModal open guestId={7} guestName="Ali" onClose={vi.fn()} />,
    );

    expect(await screen.findByText("••••5678")).toBeInTheDocument();
    expect(listGuestDocuments).toHaveBeenCalledWith(7, { page: 1, page_size: 10 });
  });
});
