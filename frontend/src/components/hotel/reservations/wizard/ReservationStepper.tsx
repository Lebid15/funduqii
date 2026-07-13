"use client";

import { Fragment } from "react";
import { AlertCircle, Check } from "lucide-react";

import { Icon } from "@/components/ui";

/** One step in the reservation stepper. `label` is already localized. */
export interface ReservationStep {
  key: string;
  label: string;
}

/** The visual state of a single step. Colour is NEVER the only signal — done
 * shows a check, error shows an alert icon, current keeps the digit. */
type StepStatus = "current" | "done" | "todo" | "error";

interface ReservationStepperProps {
  steps: ReservationStep[];
  /** The active step index. */
  current: number;
  /** The step index that failed a blocking validation, or null. */
  errorIndex: number | null;
  /** Backward navigation only — the shell ignores forward jumps. */
  onSelect: (index: number) => void;
  labels: {
    /** `nav` aria-label, e.g. "Step 2 of 4". */
    navLabel: string;
    /** Compact line, e.g. "Step 2 of 4 — Companions". */
    compact: string;
    /** Screen-reader status words per state. */
    state: Record<StepStatus, string>;
  };
}

function statusOf(
  index: number,
  current: number,
  errorIndex: number | null,
): StepStatus {
  if (index === errorIndex) return "error";
  if (index === current) return "current";
  if (index < current) return "done";
  return "todo";
}

/**
 * The reservation stepper (RESERVATIONS-FORM-UX-CORRECTION · F1). Four clear
 * steps — Guest · Companions · Documents · Booking — each with EXACTLY ONE
 * number (the digit lives only in `.resform-step__num`; the label carries none,
 * which fixes the old duplicated "1. 1" defect). States: current (brand),
 * done (check, backward-navigable), todo (disabled), error (alert). RTL/LTR via
 * inline flow + logical properties. A compact "step n of N — label" + dot rail
 * replaces the full rail on phones (toggled purely by CSS media query).
 */
export function ReservationStepper({
  steps,
  current,
  errorIndex,
  onSelect,
  labels,
}: ReservationStepperProps) {
  const last = steps.length - 1;

  return (
    <nav className="resform-stepper" aria-label={labels.navLabel}>
      {/* Full rail — hidden ≤560px. A flat flex row of step buttons and
          connector bars (no list marker → no chance of a duplicated number). */}
      <div className="resform-stepper__rail">
        {steps.map((step, index) => {
          const status = statusOf(index, current, errorIndex);
          const disabled = index > current;
          return (
            <Fragment key={step.key}>
              <button
                type="button"
                className={`resform-step resform-step--${status}`}
                aria-current={index === current ? "step" : undefined}
                disabled={disabled}
                onClick={() => onSelect(index)}
              >
                <span className="resform-step__num" aria-hidden="true">
                  {status === "done" ? (
                    <Icon icon={Check} size="sm" />
                  ) : status === "error" ? (
                    <Icon icon={AlertCircle} size="sm" />
                  ) : (
                    index + 1
                  )}
                </span>
                <span className="resform-step__label">{step.label}</span>
                <span className="sr-only">{labels.state[status]}</span>
              </button>
              {index < last ? (
                <span
                  aria-hidden="true"
                  className={`resform-step__bar${
                    index < current ? " resform-step__bar--done" : ""
                  }`}
                />
              ) : null}
            </Fragment>
          );
        })}
      </div>

      {/* Compact variant — shown ≤560px. */}
      <div className="resform-stepper__compact">
        <span className="resform-stepper__compact-line">{labels.compact}</span>
        <div className="resform-stepper__dots" aria-hidden="true">
          {steps.map((step, index) => {
            const status = statusOf(index, current, errorIndex);
            const tone =
              status === "current"
                ? " resform-step__dot--current"
                : status === "done"
                  ? " resform-step__dot--done"
                  : status === "error"
                    ? " resform-step__dot--error"
                    : "";
            return (
              <span key={step.key} className={`resform-step__dot${tone}`} />
            );
          })}
        </div>
      </div>
    </nav>
  );
}
