import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Play, Trash2, UserCheck } from "lucide-react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OperationCard, type OperationMenuItem } from "../OperationCard";
import { renderWithProviders } from "@/test-utils";

/**
 * OperationCard (WP12 / owner §17 "CARDS"). The presentational record card:
 * status/priority badges + a compact fact row, EXACTLY one primary action button
 * rendered inline, and every secondary action folded into an accessible "More"
 * menu (menu-button APG pattern: role=menu / role=menuitem, roving focus,
 * Escape-to-close with focus return). All state/permission logic lives in the
 * calling tab — here we prove the calm one-primary + menu contract holds.
 */

const facts = [
  { key: "type", label: "Task type", value: "Check-out cleaning" },
  { key: "assignee", label: "Assignee", value: "Unassigned" },
];

function renderCard(props: Partial<React.ComponentProps<typeof OperationCard>> = {}) {
  return renderWithProviders(
    <OperationCard
      accent={props.accent ?? "warning"}
      number={props.number ?? "HK00001"}
      title={props.title ?? "101"}
      badges={props.badges ?? <span className="badge">Pending</span>}
      facts={props.facts ?? facts}
      note={props.note}
      primary={props.primary}
      menu={props.menu}
      moreLabel={props.moreLabel ?? "More"}
      ariaLabel={props.ariaLabel ?? "Housekeeping task HK00001"}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("OperationCard — identity, badges and facts", () => {
  it("renders the record number (LTR-isolated), title, badges and each fact", () => {
    const { container } = renderCard();
    // The identifier is bidi-isolated so RTL never reorders it.
    const numberBdi = container.querySelector(".op-card__number bdi[dir='ltr']");
    expect(numberBdi?.textContent).toBe("HK00001");
    expect(screen.getByText("101")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    // Facts render as a labelled dt/dd pair.
    expect(screen.getByText("Task type")).toBeInTheDocument();
    expect(screen.getByText("Check-out cleaning")).toBeInTheDocument();
    expect(screen.getByText("Assignee")).toBeInTheDocument();
  });

  it("exposes the card as an article with the record's accessible name", () => {
    renderCard({ ariaLabel: "Housekeeping task HK00042" });
    expect(
      screen.getByRole("article", { name: "Housekeeping task HK00042" }),
    ).toBeInTheDocument();
  });
});

describe("OperationCard — exactly one primary action", () => {
  it("renders a single inline primary button and folds the rest into the menu", () => {
    const onPrimary = vi.fn();
    const menu: OperationMenuItem[] = [
      { key: "assign", label: "Assign", icon: UserCheck, onSelect: vi.fn() },
      { key: "cancel", label: "Cancel", icon: Trash2, danger: true, onSelect: vi.fn() },
    ];
    const { container } = renderCard({
      primary: { label: "Start", icon: Play, onClick: onPrimary },
      menu,
    });

    // EXACTLY one primary action button on the card.
    expect(container.querySelectorAll(".op-card__primary")).toHaveLength(1);
    const primary = screen.getByRole("button", { name: "Start" });
    fireEvent.click(primary);
    expect(onPrimary).toHaveBeenCalledTimes(1);

    // The secondary actions are NOT loose buttons — they live behind "More".
    expect(screen.queryByRole("button", { name: "Assign" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More" })).toBeInTheDocument();
  });

  it("renders NO actions region when there is neither a primary nor a menu", () => {
    const { container } = renderCard({ primary: null, menu: [] });
    expect(container.querySelector(".op-card__actions")).toBeNull();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("OperationCard — accessible More menu (APG menu-button)", () => {
  const menu: OperationMenuItem[] = [
    { key: "assign", label: "Assign", onSelect: vi.fn() },
    { key: "priority", label: "Edit priority", onSelect: vi.fn() },
    { key: "cancel", label: "Cancel", danger: true, onSelect: vi.fn() },
  ];

  it("marks the trigger with aria-haspopup=menu and toggles aria-expanded", () => {
    renderCard({ menu });
    const trigger = screen.getByRole("button", { name: "More" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("menu", { name: "More" })).toBeInTheDocument();
    expect(screen.getAllByRole("menuitem")).toHaveLength(3);
  });

  it("moves focus to the first item on open, then Down/Up cycles roving focus", async () => {
    renderCard({ menu });
    fireEvent.click(screen.getByRole("button", { name: "More" }));

    const items = screen.getAllByRole("menuitem");
    await waitFor(() => expect(items[0]).toHaveFocus());

    const menuEl = screen.getByRole("menu");
    fireEvent.keyDown(menuEl, { key: "ArrowDown" });
    expect(items[1]).toHaveFocus();
    fireEvent.keyDown(menuEl, { key: "ArrowUp" });
    expect(items[0]).toHaveFocus();
    // Home / End jump to the ends.
    fireEvent.keyDown(menuEl, { key: "End" });
    expect(items[2]).toHaveFocus();
    fireEvent.keyDown(menuEl, { key: "Home" });
    expect(items[0]).toHaveFocus();
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    renderCard({ menu });
    const trigger = screen.getByRole("button", { name: "More" });
    fireEvent.click(trigger);
    await waitFor(() => expect(screen.getByRole("menu")).toBeInTheDocument());

    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("invokes a menu item's onSelect and closes the menu", () => {
    const onAssign = vi.fn();
    renderCard({
      menu: [{ key: "assign", label: "Assign", onSelect: onAssign }],
    });
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Assign" }));
    expect(onAssign).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("gives a danger action its danger styling", () => {
    renderCard({ menu });
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    const cancel = screen.getByRole("menuitem", { name: "Cancel" });
    expect(cancel.className).toMatch(/op-menu__item--danger/);
    // A non-danger item does not carry the modifier.
    const assign = screen.getByRole("menuitem", { name: "Assign" });
    expect(assign.className).not.toMatch(/op-menu__item--danger/);
  });
});

describe("OperationCard — accent tone", () => {
  it("maps the accent tone onto the card's CSS accent variable", () => {
    const { container } = renderCard({ accent: "danger" });
    const article = container.querySelector(".op-card") as HTMLElement;
    // The danger accent flows through as the record's left-rail colour token.
    expect(article.style.getPropertyValue("--op-accent")).toBe("var(--color-danger)");
  });
});

describe("OperationCard — menu icon buttons still expose a label", () => {
  it("renders each menu item with its visible label text", () => {
    renderCard({
      menu: [
        { key: "assign", label: "Assign", icon: UserCheck, onSelect: vi.fn() },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    const menuEl = screen.getByRole("menu");
    expect(within(menuEl).getByText("Assign")).toBeInTheDocument();
  });
});
