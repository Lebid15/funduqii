import type { ComponentProps } from "react";
import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GuestCard } from "../GuestCard";
import { makeDirectoryRow, renderWithProviders } from "@/test-utils";

/**
 * GuestCard (R2-FE). The comprehensive profile modal was removed: the CARD is the
 * guest interface, so it renders masked identity facts + stats + short
 * backend-derived indicators + permission-gated icon actions that open each
 * record sub-modal DIRECTLY. It carries NO "view profile" control and NO
 * operational stay controls (incl. no folio icon). `can` is a prop, so no context
 * mock is needed.
 */

/** Allow every permission unless a test narrows it. */
const allow = () => true;

const noop = vi.fn();

function renderCard(
  props: Partial<ComponentProps<typeof GuestCard>> = {},
  options?: { locale?: "en" | "ar" | "tr" },
) {
  const guest = props.guest ?? makeDirectoryRow();
  return renderWithProviders(
    <GuestCard
      guest={guest}
      can={props.can ?? allow}
      onEdit={props.onEdit ?? noop}
      onToggleVip={props.onToggleVip ?? noop}
      onBlock={props.onBlock ?? noop}
      onStays={props.onStays}
      onReservations={props.onReservations}
      onDocuments={props.onDocuments}
      onChangeLog={props.onChangeLog}
      busy={props.busy}
    />,
    options,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("GuestCard — identity facts", () => {
  it("renders name, partially-masked phone, nationality, masked document, stays, nights and last stay", () => {
    renderCard({
      guest: makeDirectoryRow({
        full_name: "Ali Hassan",
        phone: "0555••••56",
        nationality: "Saudi",
        document_number: "••••1234",
        stays_count: 3,
        nights_total: 12,
        last_stay_date: "2026-07-10",
      }),
    });

    expect(screen.getByText("Ali Hassan")).toBeInTheDocument();
    expect(screen.getByText("0555••••56")).toBeInTheDocument();
    expect(screen.getByText("Saudi")).toBeInTheDocument();
    // The masked document number is shown EXACTLY as received (never unmasked).
    expect(screen.getByText("••••1234")).toBeInTheDocument();
    // Localised quantities.
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    // The date renders (no UTC day-shift) — the year is a stable anchor.
    expect(screen.getByText(/2026/)).toBeInTheDocument();
  });

  it("wraps identifier values in an LTR <bdi> so RTL never reorders their digits", () => {
    const { container } = renderCard({
      guest: makeDirectoryRow({ phone: "0555••••56", document_number: "••••1234" }),
    });
    const ltr = Array.from(container.querySelectorAll('bdi[dir="ltr"]')).map(
      (n) => n.textContent,
    );
    expect(ltr).toContain("0555••••56");
    expect(ltr).toContain("••••1234");
  });
});

describe("GuestCard — status badges", () => {
  it("shows the VIP badge for a VIP guest", () => {
    renderCard({ guest: makeDirectoryRow({ is_vip: true }) });
    expect(screen.getByText("VIP")).toBeInTheDocument();
  });

  it("shows the banned badge for a blocked guest", () => {
    renderCard({ guest: makeDirectoryRow({ is_blocked: true }) });
    expect(screen.getByText("Blocked")).toBeInTheDocument();
  });

  it("shows the in-house badge with the room number for a resident", () => {
    renderCard({
      guest: makeDirectoryRow({ is_resident: true, current_room_number: "204" }),
    });
    expect(screen.getByText(/In house/)).toBeInTheDocument();
    expect(screen.getByText(/204/)).toBeInTheDocument();
  });

  it("shows the has-upcoming badge from the directory row flag (short info only)", () => {
    renderCard({ guest: makeDirectoryRow({ has_upcoming: true }) });
    expect(screen.getByText("Upcoming")).toBeInTheDocument();
  });

  it("shows the needs-review badge from the directory row flag", () => {
    renderCard({ guest: makeDirectoryRow({ needs_review: true }) });
    expect(screen.getByText("Needs review")).toBeInTheDocument();
  });

  it("hides the upcoming + needs-review indicators when the row flags are false", () => {
    renderCard({
      guest: makeDirectoryRow({ has_upcoming: false, needs_review: false }),
    });
    expect(screen.queryByText("Upcoming")).not.toBeInTheDocument();
    expect(screen.queryByText("Needs review")).not.toBeInTheDocument();
  });

  it("shows the past-guest badge for a non-resident with stay history", () => {
    renderCard({ guest: makeDirectoryRow({ is_resident: false, stays_count: 2 }) });
    expect(screen.getByText("Past guest")).toBeInTheDocument();
  });
});

describe("GuestCard — permission gating", () => {
  it("renders edit / VIP / block actions only with their permission", () => {
    renderCard({
      guest: makeDirectoryRow({ full_name: "Ali Hassan" }),
      can: (...codes: string[]) => codes.includes("guests.update"),
    });
    // Edit is granted…
    expect(
      screen.getByRole("button", { name: "Edit — Ali Hassan" }),
    ).toBeInTheDocument();
    // …VIP + block are not.
    expect(
      screen.queryByRole("button", { name: /Mark VIP — Ali Hassan/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Block — Ali Hassan/ }),
    ).not.toBeInTheDocument();
  });

  it("renders the documents seam only with reservation_documents.view AND its callback", () => {
    const onDocuments = vi.fn();
    const { rerender } = renderCard({
      guest: makeDirectoryRow({ full_name: "Ali Hassan" }),
      can: () => false,
      onDocuments,
    });
    expect(
      screen.queryByRole("button", { name: /Documents — Ali Hassan/ }),
    ).not.toBeInTheDocument();

    rerender(
      <GuestCard
        guest={makeDirectoryRow({ full_name: "Ali Hassan" })}
        can={(...codes: string[]) => codes.includes("reservation_documents.view")}
        onDocuments={onDocuments}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Documents — Ali Hassan" }),
    ).toBeInTheDocument();
  });
});

describe("GuestCard — scope guard", () => {
  it("does NOT render any operational stay control (check-in / check-out / payment / folio / extend / room-move)", () => {
    renderCard({
      guest: makeDirectoryRow({ is_resident: true, current_room_number: "204" }),
      onStays: vi.fn(),
      onReservations: vi.fn(),
      onDocuments: vi.fn(),
      onChangeLog: vi.fn(),
    });
    expect(
      screen.queryByRole("button", {
        name: /check.?in|check.?out|payment|folio|extend|room.?move|move room|depart|assign/i,
      }),
    ).not.toBeInTheDocument();
  });

  it("has NO general folio icon on the card", () => {
    renderCard({
      guest: makeDirectoryRow({ is_resident: true, current_room_number: "204" }),
      onStays: vi.fn(),
      onReservations: vi.fn(),
      onDocuments: vi.fn(),
      onChangeLog: vi.fn(),
    });
    expect(
      screen.queryByRole("button", { name: /folio|invoice/i }),
    ).not.toBeInTheDocument();
  });

  it("exposes NO 'view profile' control even when the record seams are present", () => {
    renderCard({
      guest: makeDirectoryRow({ full_name: "Ali Hassan" }),
      onStays: vi.fn(),
      onReservations: vi.fn(),
      onDocuments: vi.fn(),
      onChangeLog: vi.fn(),
    });
    expect(
      screen.queryByRole("button", { name: /view profile|open profile/i }),
    ).not.toBeInTheDocument();
  });

  it("renders the guest name as a plain heading, never an actionable control", () => {
    // With every permission denied and no record seams supplied, the card has no
    // buttons at all — proving the name itself no longer opens anything.
    renderCard({
      guest: makeDirectoryRow({ full_name: "Ali Hassan" }),
      can: () => false,
    });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("Ali Hassan")).toBeInTheDocument();
  });

  it("gives every icon action a translated tooltip + an aria-label naming the guest", () => {
    renderCard({
      guest: makeDirectoryRow({ full_name: "Ali Hassan" }),
      onStays: vi.fn(),
    });
    const stays = screen.getByRole("button", { name: "Stay history — Ali Hassan" });
    // A native <button> (keyboard-focusable) with a visible tooltip (title).
    expect(stays.tagName).toBe("BUTTON");
    expect(stays).toHaveAttribute("title", "View stays");
    expect(
      screen.getByRole("button", { name: "Edit — Ali Hassan" }),
    ).toHaveAttribute("title", "Edit");
  });

  it("keeps identifiers LTR even under an RTL locale", () => {
    const { container } = renderCard(
      { guest: makeDirectoryRow({ phone: "0555••••56" }) },
      { locale: "ar" },
    );
    const ltr = Array.from(container.querySelectorAll('bdi[dir="ltr"]')).map(
      (n) => n.textContent,
    );
    expect(ltr).toContain("0555••••56");
  });
});

describe("GuestCard — actions fire", () => {
  it("invokes onEdit from the pencil icon (opens the edit modal directly)", () => {
    const onEdit = vi.fn();
    const guest = makeDirectoryRow({ full_name: "Ali Hassan" });
    renderCard({ guest, onEdit });
    screen.getByRole("button", { name: "Edit — Ali Hassan" }).click();
    expect(onEdit).toHaveBeenCalledWith(guest);
  });

  it("invokes onStays / onReservations from their icons", () => {
    const onStays = vi.fn();
    const onReservations = vi.fn();
    const guest = makeDirectoryRow({ full_name: "Ali Hassan" });
    renderCard({ guest, onStays, onReservations });
    screen.getByRole("button", { name: "Stay history — Ali Hassan" }).click();
    screen
      .getByRole("button", { name: "Reservation history — Ali Hassan" })
      .click();
    expect(onStays).toHaveBeenCalledWith(guest);
    expect(onReservations).toHaveBeenCalledWith(guest);
  });
});
