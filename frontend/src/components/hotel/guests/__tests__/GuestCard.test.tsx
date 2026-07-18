import type { ComponentProps } from "react";
import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GuestCard } from "../GuestCard";
import { makeDirectoryRow, makeReservationRow, renderWithProviders } from "@/test-utils";

/**
 * GuestCard (MANDATE W7, list item 1). The card is a guest IDENTITY card: it
 * renders masked identity facts + stats + permission-gated actions and carries
 * NO operational stay controls. `can` is a prop, so no context mock is needed.
 */

/** Allow every permission unless a test narrows it. */
const allow = () => true;

const noop = vi.fn();

function renderCard(
  props: Partial<ComponentProps<typeof GuestCard>> = {},
) {
  const guest = props.guest ?? makeDirectoryRow();
  return renderWithProviders(
    <GuestCard
      guest={guest}
      can={props.can ?? allow}
      onOpenProfile={props.onOpenProfile ?? noop}
      onEdit={props.onEdit ?? noop}
      onToggleVip={props.onToggleVip ?? noop}
      onBlock={props.onBlock ?? noop}
      onStays={props.onStays}
      onReservations={props.onReservations}
      onDocuments={props.onDocuments}
      onChangeLog={props.onChangeLog}
      upcoming={props.upcoming}
      busy={props.busy}
    />,
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

  it("shows the has-upcoming badge + next-arrival hint when a forthcoming reservation is supplied", () => {
    renderCard({
      upcoming: [makeReservationRow({ reservation_number: "R00042", check_in_date: "2026-09-01" })],
    });
    expect(screen.getByText("Upcoming")).toBeInTheDocument();
    expect(screen.getByText("R00042")).toBeInTheDocument();
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
        onOpenProfile={noop}
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

  it("gives every icon action an accessible name that includes the guest name", () => {
    renderCard({
      guest: makeDirectoryRow({ full_name: "Ali Hassan" }),
      onStays: vi.fn(),
    });
    // The primary name button + the icon actions all name the guest.
    expect(
      screen.getByRole("button", { name: "View profile — Ali Hassan" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Stay history — Ali Hassan" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Edit — Ali Hassan" }),
    ).toBeInTheDocument();
  });
});

describe("GuestCard — actions fire", () => {
  it("invokes onOpenProfile from the focal name button", async () => {
    const onOpenProfile = vi.fn();
    const guest = makeDirectoryRow({ full_name: "Ali Hassan" });
    renderCard({ guest, onOpenProfile });
    const btn = screen.getByRole("button", { name: "View profile — Ali Hassan" });
    within(btn).getByText("Ali Hassan");
    btn.click();
    expect(onOpenProfile).toHaveBeenCalledWith(guest);
  });
});
