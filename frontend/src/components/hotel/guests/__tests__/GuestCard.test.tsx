import type { ComponentProps } from "react";
import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GuestCard } from "../GuestCard";
import { makeCurrentUnit, makeDirectoryRow, renderWithProviders } from "@/test-utils";

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

describe("GuestCard — new / repeat guest status (top badge, not a stat)", () => {
  it("shows 'نزيل جديد' in the top status row for a first-time guest", () => {
    const { container } = renderCard(
      { guest: makeDirectoryRow({ stays_count: 1, is_resident: false }) },
      { locale: "ar" },
    );
    // Rendered exactly once, inside the TOP status row.
    expect(screen.getAllByText("نزيل جديد")).toHaveLength(1);
    expect(container.querySelector(".guest-card__status-row")).toHaveTextContent(
      "نزيل جديد",
    );
    expect(screen.queryByText("نزيل متكرر")).not.toBeInTheDocument();
  });

  it("shows 'نزيل متكرر' in the top status row for a repeat guest", () => {
    const { container } = renderCard(
      { guest: makeDirectoryRow({ stays_count: 3, is_resident: false }) },
      { locale: "ar" },
    );
    expect(screen.getAllByText("نزيل متكرر")).toHaveLength(1);
    expect(container.querySelector(".guest-card__status-row")).toHaveTextContent(
      "نزيل متكرر",
    );
    expect(screen.queryByText("نزيل جديد")).not.toBeInTheDocument();
  });

  it("derives repeat/new from stays_count > 1 (boundary: exactly one stay is new)", () => {
    renderCard({ guest: makeDirectoryRow({ stays_count: 1 }) });
    expect(screen.getByText("New guest")).toBeInTheDocument();
    expect(screen.queryByText("Repeat guest")).not.toBeInTheDocument();
  });

  it("does NOT render the new/repeat status inside the stats/numbers area", () => {
    // Every badge lives in the top status row; the fact lists (identity + stats)
    // carry NUMBERS only, never a status pill.
    const { container } = renderCard(
      { guest: makeDirectoryRow({ stays_count: 3 }) },
      { locale: "ar" },
    );
    const factBadges = container.querySelectorAll(".guest-card__facts .badge");
    expect(factBadges).toHaveLength(0);
    const stats = Array.from(container.querySelectorAll(".guest-card__facts"))
      .map((f) => f.textContent)
      .join(" ");
    expect(stats).not.toContain("نزيل متكرر");
    expect(stats).not.toContain("نزيل جديد");
  });

  it("renders each status badge exactly once — no duplication", () => {
    renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        is_vip: true,
        stays_count: 3,
        current_units_count: 1,
        current_unit: makeCurrentUnit(),
      }),
    });
    expect(screen.getAllByText("Repeat guest")).toHaveLength(1);
    expect(screen.getAllByText("In-house")).toHaveLength(1);
    expect(screen.getAllByText("VIP")).toHaveLength(1);
  });
});

describe("GuestCard — current unit clarity", () => {
  it("shows the resident's unit as '<type> <number>' plus a translated floor (number fallback)", () => {
    const { container } = renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        current_room_number: "512",
        current_units_count: 1,
        current_unit: makeCurrentUnit({
          room_number: "512",
          room_type_name: "Deluxe Suite",
          // No hotel-given floor NAME → the translated "Floor {n}" fallback.
          floor_name: "",
          floor_number: "3",
        }),
      }),
    });
    // The in-house status + the registered type name (shown AS-IS) + the number.
    expect(screen.getByText("In-house")).toBeInTheDocument();
    expect(screen.getByText(/Deluxe Suite/)).toBeInTheDocument();
    expect(screen.getByText("512")).toBeInTheDocument();
    // A translated floor label whose numeric value is direction-isolated (LTR),
    // not a bare number and not a re-ordered one.
    const floorBadge = container.querySelector(".guest-card__floor");
    expect(floorBadge).not.toBeNull();
    expect(floorBadge).toHaveTextContent("Floor 3");
    expect(floorBadge?.querySelector('bdi[dir="ltr"]')?.textContent).toBe("3");
    // NEVER the old ambiguous "· 1" residency marker.
    expect(container.textContent ?? "").not.toContain("· 1");
  });

  it("renders the free-text unit type as-is and keeps the unit number LTR under RTL", () => {
    const { container } = renderCard(
      {
        guest: makeDirectoryRow({
          is_resident: true,
          current_units_count: 1,
          current_unit: makeCurrentUnit({
            room_number: "512",
            room_type_name: "سويت",
            // Number fallback → the translated "الطابق {n}" wrapper.
            floor_name: "",
            floor_number: "2",
          }),
        }),
      },
      { locale: "ar" },
    );
    // The hotel's registered Arabic type name is shown verbatim (DATA, not a key).
    expect(screen.getByText(/سويت/)).toBeInTheDocument();
    // Translated floor label in Arabic, its value LTR-isolated.
    const floorBadge = container.querySelector(".guest-card__floor");
    expect(floorBadge).toHaveTextContent("الطابق 2");
    // The unit number AND the floor value both stay LTR identifiers under RTL.
    const ltr = Array.from(container.querySelectorAll('bdi[dir="ltr"]')).map(
      (n) => n.textContent,
    );
    expect(ltr).toContain("512");
    expect(ltr).toContain("2");
  });

  it("bidi-isolates the free-text unit type in an auto-direction <bdi>", () => {
    const { container } = renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        current_units_count: 1,
        current_unit: makeCurrentUnit({ room_type_name: "سويت", room_number: "512" }),
      }),
    });
    const typeEl = container.querySelector(".guest-card__unit-type");
    expect(typeEl).not.toBeNull();
    // A <bdi> with NO explicit dir → the UA infers direction per content (auto),
    // so a mixed Arabic/Latin type name can never reorder around the number.
    expect(typeEl?.tagName.toLowerCase()).toBe("bdi");
    expect(typeEl?.getAttribute("dir")).toBeNull();
    expect(typeEl?.textContent).toBe("سويت");
  });

  it("gives the current-unit chip a tone/variant distinct from the status badges", () => {
    const { container } = renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        stays_count: 3, // repeat guest → a WHO/status badge
        current_units_count: 1,
        current_unit: makeCurrentUnit(),
      }),
    });
    // "Where they are" = a neutral OUTLINE chip.
    const unitBadge = container.querySelector(".guest-card__unit");
    expect(unitBadge?.className).toMatch(/badge--neutral/);
    expect(unitBadge?.className).toMatch(/badge--outline/);
    // "Who they are" = a soft-toned status pill, never the unit's neutral outline.
    const repeatBadge = screen.getByText("Repeat guest").closest(".badge");
    expect(repeatBadge?.className).not.toMatch(/badge--outline/);
    expect(repeatBadge?.className).not.toMatch(/badge--neutral/);
  });

  it("clamps a long unit type to a single-line titled span, number stays attached", () => {
    const longName = "Presidential Panoramic Corner Suite";
    const { container } = renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        current_units_count: 1,
        current_unit: makeCurrentUnit({ room_type_name: longName, room_number: "900" }),
      }),
    });
    const typeEl = container.querySelector(".guest-card__unit-type");
    // The full value is exposed via a native title tooltip; the text is only
    // visually clipped (CSS ellipsis), never truncated in the DOM.
    expect(typeEl).toHaveAttribute("title", longName);
    expect(typeEl?.textContent).toBe(longName);
    // The unit NUMBER stays attached to the same chip and is never clipped.
    const unitBadge = container.querySelector(".guest-card__unit");
    expect(unitBadge?.querySelector('bdi[dir="ltr"]')?.textContent).toBe("900");
  });

  it("shows a compact 'current units' summary (not a single unit) for 2+ units", () => {
    renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        current_units_count: 2,
        current_unit: null,
      }),
    });
    expect(screen.getByText("2 current units")).toBeInTheDocument();
    // The in-house status is still shown, but no single unit type/number or floor.
    expect(screen.getByText("In-house")).toBeInTheDocument();
    expect(screen.queryByText(/^Floor/)).not.toBeInTheDocument();
  });

  it("uses the '{n} current units' plural form for three-plus units", () => {
    renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        current_units_count: 3,
        current_unit: null,
      }),
    });
    expect(screen.getByText("3 current units")).toBeInTheDocument();
  });

  it("shows NO unit or floor for a non-resident", () => {
    renderCard({
      guest: makeDirectoryRow({
        is_resident: false,
        current_units_count: 0,
        current_unit: null,
      }),
    });
    expect(screen.queryByText("In-house")).not.toBeInTheDocument();
    expect(screen.queryByText(/^Floor/)).not.toBeInTheDocument();
    expect(screen.queryByText(/current units$/)).not.toBeInTheDocument();
  });
});

describe("GuestCard — floor label (no duplication)", () => {
  it("shows a hotel-given floor NAME verbatim, never doubling 'الطابق'", () => {
    // The stored floor_name ALREADY reads "الطابق 1"; the card must not prepend the
    // translated "الطابق {floor}" wrapper on top of it.
    const { container } = renderCard(
      {
        guest: makeDirectoryRow({
          is_resident: true,
          current_units_count: 1,
          current_unit: makeCurrentUnit({ floor_name: "الطابق 1", floor_number: "1" }),
        }),
      },
      { locale: "ar" },
    );
    const floorBadge = container.querySelector(".guest-card__floor");
    expect(floorBadge).not.toBeNull();
    // The name is rendered exactly ONCE, as-is.
    expect(screen.getAllByText("الطابق 1")).toHaveLength(1);
    // The duplicated form must NEVER appear anywhere in the card.
    expect(container.textContent ?? "").not.toContain("الطابق الطابق");
  });

  it("shows a non-numeric floor NAME (e.g. 'الأرضي') verbatim with no prefix", () => {
    const { container } = renderCard(
      {
        guest: makeDirectoryRow({
          is_resident: true,
          current_units_count: 1,
          current_unit: makeCurrentUnit({ floor_name: "الأرضي", floor_number: "0" }),
        }),
      },
      { locale: "ar" },
    );
    const floorBadge = container.querySelector(".guest-card__floor");
    expect(floorBadge).toHaveTextContent("الأرضي");
    // The floor_name wins over floor_number — the number is NOT shown alongside it.
    expect(floorBadge?.textContent ?? "").not.toContain("الطابق");
    expect(floorBadge?.textContent ?? "").not.toContain("0");
  });

  it("falls back to the translated 'Floor {n}' label when there is no floor NAME", () => {
    const { container } = renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        current_units_count: 1,
        current_unit: makeCurrentUnit({ floor_name: "", floor_number: "2" }),
      }),
    });
    const floorBadge = container.querySelector(".guest-card__floor");
    expect(floorBadge).toHaveTextContent("Floor 2");
    // The numeric fallback stays an LTR-isolated identifier.
    expect(floorBadge?.querySelector('bdi[dir="ltr"]')?.textContent).toBe("2");
  });

  it("renders NO floor chip when neither a name nor a number is present", () => {
    const { container } = renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        current_units_count: 1,
        current_unit: makeCurrentUnit({ floor_name: "", floor_number: null }),
      }),
    });
    expect(container.querySelector(".guest-card__floor")).toBeNull();
  });

  it("shows a floor ICON next to the floor text", () => {
    const { container } = renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        current_units_count: 1,
        current_unit: makeCurrentUnit({ floor_name: "Ground" }),
      }),
    });
    const floorBadge = container.querySelector(".guest-card__floor");
    // The lucide floor icon renders as an <svg> inside the chip.
    expect(floorBadge?.querySelector("svg")).not.toBeNull();
    expect(floorBadge).toHaveTextContent("Ground");
  });

  it("clamps a long floor name to a single-line titled span (card never breaks)", () => {
    const longFloor = "North Tower Executive Mezzanine Level";
    const { container } = renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        current_units_count: 1,
        current_unit: makeCurrentUnit({ floor_name: longFloor }),
      }),
    });
    const nameEl = container.querySelector(".guest-card__floor-name");
    // The full value is exposed via a native title tooltip; the text is only
    // visually clipped (CSS ellipsis), never truncated in the DOM.
    expect(nameEl).toHaveAttribute("title", longFloor);
    expect(nameEl?.textContent).toBe(longFloor);
  });

  it("keeps a numeric floor name as an auto-direction <bdi> (no forced dir)", () => {
    // A bare "3" floor name is shown verbatim — not wrapped in the translated
    // label — inside an auto-direction <bdi> so it can never be misordered.
    const { container } = renderCard({
      guest: makeDirectoryRow({
        is_resident: true,
        current_units_count: 1,
        current_unit: makeCurrentUnit({ floor_name: "3", floor_number: "9" }),
      }),
    });
    const nameEl = container.querySelector(".guest-card__floor-name");
    expect(nameEl?.tagName.toLowerCase()).toBe("bdi");
    expect(nameEl?.getAttribute("dir")).toBeNull();
    expect(nameEl?.textContent).toBe("3");
    // The unrelated floor_number is ignored while a name exists.
    expect(container.querySelector(".guest-card__floor")?.textContent).not.toContain(
      "Floor",
    );
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
