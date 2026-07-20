/**
 * Regression coverage for the Toast auto-dismiss timer lifecycle.
 *
 * WHY THIS FILE EXISTS. `notify()` schedules a 4000ms `setTimeout` to remove the
 * toast. That timer used to be created and never cleared. When a test fired a
 * toast and its file finished within four seconds, the timer stayed pending,
 * fired after jsdom had been torn down, and called setState on an unmounted
 * provider — surfacing as `ReferenceError: window is not defined` inside
 * react-dom. Vitest recorded it as an unhandled error and exited NON-ZERO even
 * though every test had passed.
 *
 * That is the worst shape a failure can take: the textual summary reads
 * "N passed" while the exit code is 1, so any pipeline that pipes the run
 * through `tail`/`head` — which masks the exit code — reports a FALSE GREEN.
 * An independent review measured it at roughly 1 run in 33 and it was one of the
 * two reasons a FINAL CLOSURE GATE rejected this branch.
 *
 * The first test below fails if the cleanup is removed; the second proves the
 * visible auto-dismiss behaviour was NOT changed by adding it.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "../Toast";

function Trigger() {
  const { notify } = useToast();
  return (
    <button type="button" onClick={() => notify("Saved")}>
      fire
    </button>
  );
}

afterEach(() => {
  vi.useRealTimers();
});

describe("ToastProvider — auto-dismiss timer lifecycle", () => {
  it("clears a pending auto-dismiss timer on unmount", () => {
    vi.useFakeTimers();
    const { unmount } = render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "fire" }));
    expect(screen.getByText("Saved")).toBeInTheDocument();
    // The 4000ms dismissal is genuinely scheduled and still in flight.
    expect(vi.getTimerCount()).toBe(1);

    unmount();

    // THE REGRESSION ASSERTION: nothing may outlive the provider. Without the
    // cleanup this is 1, the timer later fires against a torn-down environment,
    // and the runner exits non-zero with every test still "passing".
    expect(vi.getTimerCount()).toBe(0);

    // Belt and braces: advancing past the deadline must now be inert. If a timer
    // survived, this is where it would fire and blow up.
    expect(() => {
      act(() => {
        vi.advanceTimersByTime(10_000);
      });
    }).not.toThrow();
  });

  it("still auto-dismisses after 4000ms while mounted (behaviour unchanged)", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "fire" }));
    expect(screen.getByText("Saved")).toBeInTheDocument();

    // Just short of the deadline the toast is still up...
    act(() => {
      vi.advanceTimersByTime(3999);
    });
    expect(screen.getByText("Saved")).toBeInTheDocument();

    // ...and exactly at it, it goes. The duration was NOT changed by the fix.
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.queryByText("Saved")).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("clears every pending timer when several toasts are in flight", () => {
    vi.useFakeTimers();
    const { unmount } = render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );

    const button = screen.getByRole("button", { name: "fire" });
    fireEvent.click(button);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    fireEvent.click(button);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    fireEvent.click(button);

    // Three staggered toasts, three independent deadlines still pending.
    expect(vi.getTimerCount()).toBe(3);

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});
