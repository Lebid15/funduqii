import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

/**
 * Toolchain smoke test (GUESTS-CLOSURE Decision 13): proves Vitest + jsdom +
 * React Testing Library + @testing-library/jest-dom are wired correctly. It
 * renders a trivial inline element (NOT an app component — those are exercised
 * by the W6 UI wave) and asserts through a jest-dom matcher.
 */
function Hello() {
  return <h1>Guests foundation</h1>;
}

describe("frontend test runner", () => {
  it("renders into jsdom and matches with jest-dom", () => {
    render(<Hello />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toBeInTheDocument();
    expect(heading).toHaveTextContent("Guests foundation");
  });
});
