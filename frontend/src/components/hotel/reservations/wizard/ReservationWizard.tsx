"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Alert, Button, Modal, useToast } from "@/components/ui";
import { messageForError } from "@/lib/api/errors";
import type { ImmediateCheckInResult, Reservation } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { BookingStep } from "./BookingStep";
import { CompanionsStep } from "./CompanionsStep";
import { DocumentsStep } from "./DocumentsStep";
import { GuestStep } from "./GuestStep";
import { useReservationSubmit } from "./useReservationSubmit";
import {
  createInitialDraft,
  useReservationDraft,
  type ReservationDraft,
} from "./useReservationDraft";

type StepKey = "guest" | "companions" | "documents" | "booking";
const STEPS: StepKey[] = ["guest", "companions", "documents", "booking"];

/**
 * The reservation wizard SHELL (RESERVATIONS-FORM-REWORK, Wave 2a). A shared
 * modal + a 4-step flow (Guest → Companions → Documents → Booking) over one
 * draft (`useReservationDraft`). Wave 2a implements Guest + Companions and
 * wires create / immediate-check-in submit; Documents + Booking render typed
 * placeholders that Wave 2b replaces. Accessible: focus moves to each step,
 * every control is labelled, and the layout is RTL-logical (design-system
 * classes only).
 */
export function ReservationWizard({
  open,
  initialDraft,
  onClose,
  onSaved,
  onCheckedIn,
}: {
  open: boolean;
  initialDraft?: ReservationDraft;
  onClose: () => void;
  /** A plain reservation create succeeded. */
  onSaved?: (reservation: Reservation) => void;
  /** An immediate atomic check-in succeeded. */
  onCheckedIn?: (result: ImmediateCheckInResult) => void;
}) {
  const { t } = useI18n();
  const { notify } = useToast();
  const w = t.reservations.wizard;
  const runSubmit = useReservationSubmit();
  const { draft, actions, totalPersons } = useReservationDraft(initialDraft);

  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const stepBodyRef = useRef<HTMLDivElement | null>(null);
  const wasOpen = useRef(false);

  // Fresh draft + reset position each time the wizard opens.
  useEffect(() => {
    if (open && !wasOpen.current) {
      actions.reset(initialDraft ?? createInitialDraft());
      setStep(0);
      setError(null);
      setBusy(false);
    }
    wasOpen.current = open;
  }, [open, initialDraft, actions]);

  // Move focus to the active step region (screen-reader + keyboard friendly).
  useEffect(() => {
    if (open) stepBodyRef.current?.focus();
  }, [step, open]);

  /** Per-step client-side gate. The backend re-validates everything on submit;
   * these are lightweight hints only. Returns an error string or null. */
  const validateStep = useCallback(
    (index: number): string | null => {
      const key = STEPS[index];
      if (key === "guest") {
        const name =
          draft.guest.full_name.trim() ||
          `${draft.guest.first_name} ${draft.guest.last_name}`.trim();
        if (!name) return w.validation.guestNameRequired;
        if (draft.guest.is_blocked) return w.validation.guestBlocked;
      }
      if (key === "companions" && draft.companions.has_companions) {
        const invalid = draft.companions.occupants.some((occupant) => {
          const hasIdentity =
            occupant.guest_id !== null ||
            occupant.first_name.trim() !== "" ||
            occupant.last_name.trim() !== "";
          return !hasIdentity || occupant.relationship === "";
        });
        if (invalid) return w.validation.companionIncomplete;
      }
      return null;
    },
    [draft, w],
  );

  function goNext() {
    const problem = validateStep(step);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setStep((current) => Math.min(STEPS.length - 1, current + 1));
  }

  function goBack() {
    setError(null);
    setStep((current) => Math.max(0, current - 1));
  }

  function goToStep(index: number) {
    // Only backward navigation is free; forward must pass the gate via Next.
    if (index < step) {
      setError(null);
      setStep(index);
    }
  }

  async function submit() {
    // Validate the data-bearing steps before the network call.
    for (let index = 0; index < STEPS.length; index += 1) {
      const problem = validateStep(index);
      if (problem) {
        setStep(index);
        setError(problem);
        return;
      }
    }
    // Booking-step minimums (the backend re-validates dates, capacity,
    // availability, currency and permissions authoritatively).
    const { booking } = draft;
    const hasLines = booking.lines.some((line) => line.room_type);
    if (!booking.check_in_date || !booking.check_out_date) {
      setStep(STEPS.length - 1);
      setError(w.validation.datesRequired);
      return;
    }
    if (booking.check_out_date <= booking.check_in_date) {
      setStep(STEPS.length - 1);
      setError(w.validation.checkoutAfterCheckin);
      return;
    }
    if (!hasLines) {
      setStep(STEPS.length - 1);
      setError(w.validation.roomRequired);
      return;
    }

    setBusy(true);
    setError(null);
    try {
      // Create-or-check-in, THEN upload staged documents. Document failures are
      // reported without rolling the reservation back (retry from details).
      const outcome = await runSubmit(draft);
      if (outcome.documentsFailed > 0) {
        notify(
          w.documentUploadPartial
            .replace("{failed}", String(outcome.documentsFailed))
            .replace("{total}", String(outcome.documentsTotal)),
          "error",
        );
      }
      if (outcome.checkIn) {
        onCheckedIn?.(outcome.checkIn);
      } else {
        onSaved?.(outcome.reservation);
      }
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const isLast = step === STEPS.length - 1;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={w.createTitle}
      closeLabel={t.common.close}
      size="xl"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {w.cancel}
          </Button>
          {step > 0 ? (
            <Button variant="ghost" onClick={goBack} disabled={busy}>
              {w.back}
            </Button>
          ) : null}
          {isLast ? (
            <Button onClick={submit} loading={busy}>
              {draft.booking.immediate_check_in ? w.submitCheckIn : w.submit}
            </Button>
          ) : (
            <Button onClick={goNext} disabled={busy}>
              {w.next}
            </Button>
          )}
        </>
      }
    >
      <div className="stack">
        {/* Stepper — an ordered, backward-navigable indicator. */}
        <ol
          className="cluster"
          aria-label={w.stepProgress
            .replace("{current}", String(step + 1))
            .replace("{total}", String(STEPS.length))}
        >
          {STEPS.map((key, index) => (
            <li key={key}>
              <button
                type="button"
                className={index === step ? "chip" : "floor-chip"}
                aria-current={index === step ? "step" : undefined}
                disabled={index > step || busy}
                onClick={() => goToStep(index)}
              >
                {index + 1}. {w.steps[key]}
              </button>
            </li>
          ))}
        </ol>

        {error ? <Alert tone="error">{error}</Alert> : null}

        {/* Active step body — focusable region for step-change announcements. */}
        <div ref={stepBodyRef} tabIndex={-1} aria-label={w.steps[STEPS[step]]}>
          {STEPS[step] === "guest" ? (
            <GuestStep guest={draft.guest} actions={actions} />
          ) : null}
          {STEPS[step] === "companions" ? (
            <CompanionsStep
              companions={draft.companions}
              total={totalPersons}
              actions={actions}
            />
          ) : null}
          {STEPS[step] === "documents" ? (
            <DocumentsStep draft={draft} actions={actions} />
          ) : null}
          {STEPS[step] === "booking" ? (
            <BookingStep draft={draft} actions={actions} />
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
