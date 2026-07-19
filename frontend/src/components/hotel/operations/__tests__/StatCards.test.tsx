import { fireEvent, screen } from "@testing-library/react";
import { Brush, PlaneLanding, Timer } from "lucide-react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StatCards, type OperationStat } from "../StatCards";
import { renderWithProviders } from "@/test-utils";

/**
 * StatCards (WP12 / owner §17 "STATCARDS"). The relocated Overview counters as a
 * filterable stat-card row atop each tab. A tile carrying `onFilter` is a filter
 * TOGGLE (a real <button> with aria-pressed); a display-only tile (no onFilter,
 * e.g. "Upcoming arrival") is a static <div>, never a button.
 */

beforeEach(() => {
  vi.clearAllMocks();
});

function stats(over: Partial<OperationStat>[] = []): OperationStat[] {
  const base: OperationStat[] = [
    {
      key: "needsCleaning",
      label: "Needs cleaning",
      value: 3,
      icon: Brush,
      tone: "warning",
      active: false,
      onFilter: vi.fn(),
    },
    {
      key: "inCleaning",
      label: "In cleaning",
      value: 1,
      icon: Timer,
      tone: "primary",
      active: false,
      onFilter: vi.fn(),
    },
    {
      // Display-only tile — no onFilter (an arrival count is not a list status).
      key: "upcomingArrival",
      label: "Upcoming arrival",
      value: 2,
      icon: PlaneLanding,
      tone: "danger",
    },
  ];
  return base.map((s, i) => ({ ...s, ...over[i] }));
}

describe("StatCards — row + filter toggles", () => {
  it("renders one tile per stat inside a labelled group", () => {
    renderWithProviders(<StatCards stats={stats()} ariaLabel="Housekeeping tasks" />);
    const group = screen.getByRole("group", { name: "Housekeeping tasks" });
    expect(group).toBeInTheDocument();
    expect(screen.getByText("Needs cleaning")).toBeInTheDocument();
    expect(screen.getByText("In cleaning")).toBeInTheDocument();
    expect(screen.getByText("Upcoming arrival")).toBeInTheDocument();
  });

  it("renders a filter tile as a button and fires onFilter on click", () => {
    const rows = stats();
    renderWithProviders(<StatCards stats={rows} ariaLabel="HK" />);
    const btn = screen.getByRole("button", { name: /Needs cleaning/ });
    fireEvent.click(btn);
    expect(rows[0].onFilter).toHaveBeenCalledTimes(1);
  });

  it("reflects the applied filter with aria-pressed on the active tile", () => {
    renderWithProviders(
      <StatCards stats={stats([{ active: true }])} ariaLabel="HK" />,
    );
    const active = screen.getByRole("button", { name: /Needs cleaning/ });
    expect(active).toHaveAttribute("aria-pressed", "true");
    // A non-active filter tile is pressed=false.
    const idle = screen.getByRole("button", { name: /In cleaning/ });
    expect(idle).toHaveAttribute("aria-pressed", "false");
  });

  it("renders a display-only tile (no onFilter) as a NON-button static tile", () => {
    renderWithProviders(<StatCards stats={stats()} ariaLabel="HK" />);
    // "Upcoming arrival" carries no onFilter → it must not be an actionable button.
    expect(
      screen.queryByRole("button", { name: /Upcoming arrival/ }),
    ).not.toBeInTheDocument();
    const label = screen.getByText("Upcoming arrival");
    expect(label.closest("button")).toBeNull();
  });
});

describe("StatCards — loading", () => {
  it("shows a skeleton (no value, aria-busy) only while a null value is loading", () => {
    const loading = stats([{ value: null }]);
    const { container } = renderWithProviders(
      <StatCards stats={loading} loading ariaLabel="HK" />,
    );
    // The still-loading tile is marked busy and shows no number yet.
    const busy = container.querySelector('[aria-busy="true"]');
    expect(busy).not.toBeNull();
    // The tiles whose value already arrived still show their number.
    expect(screen.getByText("1")).toBeInTheDocument();
  });
});
