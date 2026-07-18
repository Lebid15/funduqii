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
  listGuestReservations,
  listGuestStays,
} from "@/lib/api/guests";
import type { PaginatedResponse } from "@/lib/api/types";
import {
  GuestDocumentsModal,
  GuestReservationsHistoryModal,
  GuestStaysHistoryModal,
} from "../GuestRecordModals";
import {
  apiError,
  makeDocumentRow,
  makeReservationRow,
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

describe("GuestDocumentsModal — image gating on URL presence", () => {
  it("hides the view-image action when front_url/back_url are absent", async () => {
    access.set(["reservation_documents.view"]);
    vi.mocked(listGuestDocuments).mockResolvedValue(
      envelope(
        [
          makeDocumentRow({
            number: "••••5678",
            has_front: true,
            front_url: null,
            back_url: null,
          }),
        ],
        1,
      ),
    );

    renderWithProviders(
      <GuestDocumentsModal open guestId={7} guestName="Ali" onClose={vi.fn()} />,
    );

    // Type + masked number render, but there is NO dead "view image" button.
    expect(await screen.findByText("••••5678")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "View" }),
    ).not.toBeInTheDocument();
  });

  it("shows the view-image action only when a signed URL is present", async () => {
    access.set(["reservation_documents.view"]);
    vi.mocked(listGuestDocuments).mockResolvedValue(
      envelope(
        [
          makeDocumentRow({
            number: "1234",
            has_front: true,
            front_url: "/api/hotel/reservations/documents/1/front",
          }),
        ],
        1,
      ),
    );

    renderWithProviders(
      <GuestDocumentsModal open guestId={7} guestName="Ali" onClose={vi.fn()} />,
    );

    expect(
      await screen.findByRole("button", { name: "View" }),
    ).toBeInTheDocument();
  });
});

describe("GuestReservationsHistoryModal — opens the existing reservation", () => {
  it("links each reservation to the existing reservations section (no duplicate detail view)", async () => {
    access.set(["reservations.view"]);
    vi.mocked(listGuestReservations).mockResolvedValue(
      envelope([makeReservationRow({ id: 3, reservation_number: "R00042" })], 1),
    );

    renderWithProviders(
      <GuestReservationsHistoryModal
        open
        guestId={7}
        guestName="Ali"
        onClose={vi.fn()}
      />,
    );

    // Navigation (not a duplicate view): a link into the reservations section
    // deep-linked to this exact reservation, reusing that route + its detail.
    const link = await screen.findByRole("link", {
      name: "Open reservation R00042",
    });
    expect(link).toHaveAttribute(
      "href",
      "/hotel/reservations?action=find&q=R00042",
    );
  });

  it("shows the number as plain text (no link) without reservations.view", async () => {
    access.set([]); // no reservations.view
    vi.mocked(listGuestReservations).mockResolvedValue(
      envelope([makeReservationRow({ reservation_number: "R00042" })], 1),
    );

    renderWithProviders(
      <GuestReservationsHistoryModal
        open
        guestId={7}
        guestName="Ali"
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByText("R00042")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /open reservation/i }),
    ).not.toBeInTheDocument();
  });
});

describe("GuestStaysHistoryModal — linked folio action", () => {
  it("shows 'View folio' with finance.view AND a linked folio, pointing at the folio route", async () => {
    access.set(["finance.view"]);
    vi.mocked(listGuestStays).mockResolvedValue(
      envelope(
        [
          makeStayRow({
            room_number: "R201",
            folio: { id: 5, folio_number: "F00007", status: "open" },
          }),
        ],
        1,
      ),
    );

    renderWithProviders(
      <GuestStaysHistoryModal open guestId={7} guestName="Ali" onClose={vi.fn()} />,
    );

    const link = await screen.findByRole("link", { name: "View folio F00007" });
    expect(link).toHaveAttribute("href", "/hotel/finance?tab=folios");
    expect(within(link).getByText("View folio")).toBeInTheDocument();
  });

  it("hides 'View folio' without finance.view", async () => {
    access.set([]); // no finance.view
    vi.mocked(listGuestStays).mockResolvedValue(
      envelope(
        [
          makeStayRow({
            room_number: "R201",
            folio: { id: 5, folio_number: "F00007", status: "open" },
          }),
        ],
        1,
      ),
    );

    renderWithProviders(
      <GuestStaysHistoryModal open guestId={7} guestName="Ali" onClose={vi.fn()} />,
    );

    await screen.findByText("R201");
    expect(
      screen.queryByRole("link", { name: /view folio/i }),
    ).not.toBeInTheDocument();
  });

  it("renders no folio action when the stay has no linked folio", async () => {
    access.set(["finance.view"]);
    vi.mocked(listGuestStays).mockResolvedValue(
      envelope([makeStayRow({ room_number: "R201", folio: null })], 1),
    );

    renderWithProviders(
      <GuestStaysHistoryModal open guestId={7} guestName="Ali" onClose={vi.fn()} />,
    );

    await screen.findByText("R201");
    expect(
      screen.queryByRole("link", { name: /view folio/i }),
    ).not.toBeInTheDocument();
  });
});
