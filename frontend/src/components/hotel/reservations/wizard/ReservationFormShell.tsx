"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { Alert, Badge, Button, IconButton, useToast } from "@/components/ui";
import { messageForError } from "@/lib/api/errors";
import type { Reservation, ReservationFinancialSummary } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { BookingStep, type BookingEditContext } from "./BookingStep";
import { CompanionsStep } from "./CompanionsStep";
import { DocumentsStep } from "./DocumentsStep";
import { GuestStep } from "./GuestStep";
import { ReservationStepper } from "./ReservationStepper";
import {
  useReservationSubmit,
  useReservationEditSubmit,
} from "./useReservationSubmit";
import {
  useReservationDraft,
  type ReservationDraft,
} from "./useReservationDraft";

type StepKey = "guest" | "companions" | "documents" | "booking";
const STEPS: StepKey[] = ["guest", "companions", "documents", "booking"];

const LIST_ROUTE = "/hotel/reservations";

export type ReservationFormMode = "create" | "edit";

/**
 * The reservation form SHELL (RESERVATIONS-FORM-UX-CORRECTION · F1). The 4-step
 * flow (Guest → Companions → Documents → Booking) is now a full-screen PAGE, not
 * a modal: a fixed header + `ReservationStepper` + one `min-height:0` scroll band
 * + a fixed footer. Body scroll is locked (same approach as `Modal.tsx`) so the
 * app shell underneath never double-scrolls.
 *
 * The SAME shell drives both flows (§33). CREATE runs `useReservationSubmit`
 * (create-or-immediate-check-in + staged document upload). EDIT (`mode="edit"`)
 * hydrates the full draft via `reservationToDraft` and saves through
 * `useReservationEditSubmit`: `updateReservation` for the reservation fields +
 * occupants, a NEW pre-arrival deposit only when one was entered AND allowed, and
 * document replace/upload — never an immediate check-in and never re-submitting an
 * existing payment. A started stay locks dates/room (changed only via the stay
 * service); a cancelled/expired reservation is read-only (Save hidden — the
 * backend stays authoritative regardless).
 */
export function ReservationFormShell({
  mode,
  reservation,
  initialDraft,
  financialSummary,
}: {
  mode: ReservationFormMode;
  /** Edit mode only — header number, field locking and the edit-save target. */
  reservation?: Reservation;
  /** Create seed (e.g. a room pinned from the board) or full edit prefill. */
  initialDraft?: ReservationDraft;
  /** Edit mode only — DISPLAY-only record of payments already taken (§31). */
  financialSummary?: ReservationFinancialSummary | null;
}) {
  const { t } = useI18n();
  const { notify } = useToast();
  const router = useRouter();
  const access = useHotelAccess();
  const w = t.reservations.wizard;
  const runSubmit = useReservationSubmit();
  const runEditSubmit = useReservationEditSubmit();
  const { draft, actions, totalPersons } = useReservationDraft(initialDraft);

  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [errorStep, setErrorStep] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const stepBodyRef = useRef<HTMLDivElement | null>(null);

  const isEdit = mode === "edit";

  // Cosmetic gating only — every endpoint re-enforces the same permissions.
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));

  // §25/§33 (Finance-F1) — ANY stay (in-house OR already checked-out) makes the
  // STAY the source of truth: it freezes the dates + room (changed only through
  // the stay service, never a reservation edit) AND blocks a NEW pre-arrival
  // deposit, exactly as the backend now rejects both once a stay exists. A
  // cancelled/expired reservation is closed: the form is read-only and Save hides.
  const stayLocked = isEdit && Boolean(reservation?.stay_status);
  const editReadOnly =
    isEdit &&
    (reservation?.status === "cancelled" || reservation?.status === "expired");
  const primaryLine =
    reservation?.lines.find((line) => line.room_number) ??
    reservation?.lines[0] ??
    null;
  const lockedRoomLabel = primaryLine
    ? [primaryLine.room_number, primaryLine.room_type_name]
        .filter(Boolean)
        .join(" · ")
    : "";

  // The EDIT context handed to the booking step: it locks dates/room per stay
  // status, exposes the read-only payments record, and gates a NEW deposit behind
  // a stayless reservation + `finance.payment_create` (the backend re-checks it).
  const editContext: BookingEditContext | null =
    isEdit && reservation
      ? {
          stayLocked: Boolean(stayLocked),
          allowNewDeposit: !stayLocked && can("finance.payment_create"),
          financialSummary: financialSummary ?? null,
          lockedRoomLabel,
        }
      : null;

  // Lock body scroll for the lifetime of the full-screen shell — exactly the
  // pattern `Modal.tsx` uses — so the sidebar/topbar underneath cannot scroll.
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  // Move focus to the active step region on step change (SR + keyboard).
  useEffect(() => {
    stepBodyRef.current?.focus();
  }, [step]);

  const close = useCallback(() => {
    router.push(LIST_ROUTE);
  }, [router]);

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
      setErrorStep(step);
      return;
    }
    setError(null);
    setErrorStep(null);
    setStep((current) => Math.min(STEPS.length - 1, current + 1));
  }

  function goBack() {
    setError(null);
    setErrorStep(null);
    setStep((current) => Math.max(0, current - 1));
  }

  function goToStep(index: number) {
    // Only backward navigation is free; forward must pass the gate via Next.
    if (index < step) {
      setError(null);
      setErrorStep(null);
      setStep(index);
    }
  }

  async function submit() {
    // A closed reservation can't be saved (Save is hidden too); guard anyway.
    if (isEdit && editReadOnly) return;

    // Validate the data-bearing steps before the network call (both flows).
    for (let index = 0; index < STEPS.length; index += 1) {
      const problem = validateStep(index);
      if (problem) {
        setStep(index);
        setError(problem);
        setErrorStep(index);
        return;
      }
    }
    // Booking-step minimums (the backend re-validates dates, capacity,
    // availability, currency and permissions authoritatively). When a started
    // stay locks the dates/room they are server-owned and omitted from the PATCH,
    // so they are never gated here.
    const { booking } = draft;
    if (!stayLocked) {
      const hasLines = booking.lines.some((line) => line.room_type);
      if (!booking.check_in_date || !booking.check_out_date) {
        setStep(STEPS.length - 1);
        setError(w.validation.datesRequired);
        setErrorStep(STEPS.length - 1);
        return;
      }
      if (booking.check_out_date <= booking.check_in_date) {
        setStep(STEPS.length - 1);
        setError(w.validation.checkoutAfterCheckin);
        setErrorStep(STEPS.length - 1);
        return;
      }
      if (!hasLines) {
        setStep(STEPS.length - 1);
        setError(w.validation.roomRequired);
        setErrorStep(STEPS.length - 1);
        return;
      }
    }

    setBusy(true);
    setError(null);
    setErrorStep(null);
    try {
      if (isEdit && reservation) {
        // §33 — PATCH the reservation fields/occupants, record a NEW deposit only
        // when allowed + entered (never an immediate check-in, never re-submitting
        // an existing payment), then replace/upload documents. Money/document
        // failures are surfaced without rolling the saved edit back.
        const outcome = await runEditSubmit(reservation.id, draft, {
          lockStayFields: Boolean(stayLocked),
          allowNewDeposit: editContext?.allowNewDeposit ?? false,
        });
        if (outcome.depositFailed) {
          notify(w.editDepositFailed, "error");
        }
        if (outcome.documentsFailed > 0) {
          notify(
            w.editDocumentPartial
              .replace("{failed}", String(outcome.documentsFailed))
              .replace("{total}", String(outcome.documentsTotal)),
            "error",
          );
        }
        notify(w.editSaved);
        router.push(LIST_ROUTE);
        return;
      }

      // Create-or-check-in, THEN upload staged documents. Document failures are
      // reported without rolling the reservation back (retry from details).
      const outcome = await runSubmit(draft);
      if (outcome.depositFailed) {
        notify(w.depositFailed, "error");
      }
      if (outcome.documentsFailed > 0) {
        notify(
          w.documentUploadPartial
            .replace("{failed}", String(outcome.documentsFailed))
            .replace("{total}", String(outcome.documentsTotal)),
          "error",
        );
      }
      if (outcome.checkIn) {
        notify(w.booking.checkInSuccess);
      } else {
        notify(t.reservations.saved);
      }
      router.push(LIST_ROUTE);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const isLast = step === STEPS.length - 1;
  const title = isEdit ? w.editTitle : w.createTitle;
  const saveLabel = isEdit
    ? w.submitEdit
    : draft.booking.immediate_check_in
      ? w.submitCheckIn
      : w.submit;

  return (
    <section className="resform-shell" aria-label={title}>
      {/* Band 1 — fixed header: back-to-list + title + reservation-number slot. */}
      <header className="resform-header">
        <IconButton
          label={w.backToList}
          icon={ArrowLeft}
          onClick={close}
          disabled={busy}
        />
        <div className="resform-header__titles">
          <span className="resform-header__title">{title}</span>
        </div>
        <div className="resform-header__slot">
          {isEdit && reservation ? (
            <span className="resform-header__number">
              {reservation.reservation_number}
            </span>
          ) : (
            <Badge tone="neutral">{w.booking.autoAssigned}</Badge>
          )}
        </div>
      </header>

      {/* Band 2 — fixed stepper. */}
      <ReservationStepper
        steps={STEPS.map((key) => ({ key, label: w.steps[key] }))}
        current={step}
        errorIndex={errorStep}
        onSelect={goToStep}
        labels={{
          navLabel: w.stepProgress
            .replace("{current}", String(step + 1))
            .replace("{total}", String(STEPS.length)),
          compact: w.stepCompact
            .replace("{current}", String(step + 1))
            .replace("{total}", String(STEPS.length))
            .replace("{label}", w.steps[STEPS[step]]),
          state: w.stepState,
        }}
      />

      {/* Band 3 — the ONLY scroller (min-height:0 kills scroll-in-scroll). */}
      <div className="resform-main">
        <div className="resform-content">
          {editReadOnly ? <Alert tone="info">{w.editReadOnly}</Alert> : null}
          {error ? <Alert tone="error">{error}</Alert> : null}

          {/* Active step body — focusable region for step-change announcements. */}
          <div
            ref={stepBodyRef}
            tabIndex={-1}
            aria-label={w.steps[STEPS[step]]}
          >
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
              <DocumentsStep
                draft={draft}
                actions={actions}
              />
            ) : null}
            {STEPS[step] === "booking" ? (
              <BookingStep
                draft={draft}
                actions={actions}
                onEditStep={goToStep}
                editContext={editContext}
              />
            ) : null}
          </div>
        </div>
      </div>

      {/* Band 4 — fixed footer: Cancel / Back on the start, primary on the end. */}
      <footer className="resform-footer">
        <Button variant="secondary" onClick={close} disabled={busy}>
          {w.cancel}
        </Button>
        {step > 0 ? (
          <Button variant="ghost" onClick={goBack} disabled={busy}>
            {w.back}
          </Button>
        ) : null}
        {isLast ? (
          editReadOnly ? null : (
            <Button
              className="resform-footer__primary"
              onClick={submit}
              loading={busy}
            >
              {saveLabel}
            </Button>
          )
        ) : (
          <Button
            className="resform-footer__primary"
            onClick={goNext}
            disabled={busy}
          >
            {w.next}
          </Button>
        )}
      </footer>
    </section>
  );
}
