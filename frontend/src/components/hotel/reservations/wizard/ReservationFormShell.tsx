"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { CheckCircle2, Eye, Plus, Printer, X } from "lucide-react";

import { Alert, Badge, Button, IconButton, useToast } from "@/components/ui";
import { messageForError } from "@/lib/api/errors";
import type { Reservation, ReservationFinancialSummary } from "@/lib/api/types";
import {
  formatDate,
  formatMoney,
  reservationStatusLabel,
  reservationStatusTone,
  stayStatusLabel,
  stayStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { ReservationPrintPreview } from "../ReservationPrintPreview";
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

/** Which flow produced the saved record — drives the success title (§8). */
type SuccessKind = "create" | "immediate" | "edit";

/** The confirmed, backend-owned result rendered by the post-save success screen
 * (§8–§12). Always the FINAL reservation returned by the save (auto-assigned room,
 * status, stay status, derived financials) — never the pre-save draft. */
interface SubmitSuccess {
  reservation: Reservation;
  kind: SuccessKind;
}

/**
 * The reservation form SHELL (RESERVATIONS-FORM-UX-CORRECTION · F1). The 4-step
 * flow (Guest → Companions → Documents → Booking) renders as a CENTERED,
 * content-sized MODAL over the reservations list (owner correction): an overlay
 * dims the list and centres a dialog of header + `ReservationStepper` + one
 * `min-height:0` scroll band + footer. Body scroll is locked, Escape / backdrop
 * click close, and focus returns to the trigger on unmount — the same approach as
 * `Modal.tsx`. `onClose`/`onSaved` let the list host swap-and-refresh in place;
 * the standalone deep-link routes fall back to navigating to the list.
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
  onClose,
  onSaved,
  onViewReservation,
}: {
  mode: ReservationFormMode;
  /** Edit mode only — header number, field locking and the edit-save target. */
  reservation?: Reservation;
  /** Create seed (e.g. a room pinned from the board) or full edit prefill. */
  initialDraft?: ReservationDraft;
  /** Edit mode only — DISPLAY-only record of payments already taken (§31). */
  financialSummary?: ReservationFinancialSummary | null;
  /** Dismiss without saving. Defaults to navigating back to the list route
   * (deep-link fallback); the list host passes a state-clearing closer instead. */
  onClose?: () => void;
  /** Called RIGHT AFTER a successful save (§11): refresh the rows + summary +
   * availability IN PLACE, WITHOUT closing — the modal stays open on the success
   * screen (§8) until the user chooses Close / View / New. The list host passes a
   * refresh-only callback; on a standalone deep-link route it is simply absent. */
  onSaved?: () => void;
  /** Success-screen "View reservation" (§10): the list host closes this modal and
   * opens the reservation details for the freshly saved record. Absent on the
   * standalone routes, where the button is hidden. */
  onViewReservation?: (reservation: Reservation) => void;
}) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const router = useRouter();
  const access = useHotelAccess();
  const w = t.reservations.wizard;
  const sc = w.success;
  const runSubmit = useReservationSubmit();
  const runEditSubmit = useReservationEditSubmit();
  const { draft, actions, totalPersons } = useReservationDraft(initialDraft);

  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [errorStep, setErrorStep] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const stepBodyRef = useRef<HTMLDivElement | null>(null);

  // Post-save success screen (§8–§12). Set on a successful save INSTEAD of closing;
  // `printOpen` layers the idempotent FE-C print preview above the screen and
  // `pendingNew` gates the "start a fresh reservation" confirm.
  const [success, setSuccess] = useState<SubmitSuccess | null>(null);
  const [printOpen, setPrintOpen] = useState(false);
  const [pendingNew, setPendingNew] = useState(false);
  const successRef = useRef<HTMLDivElement | null>(null);

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
          reservationNumber: reservation.reservation_number,
          stayLocked: Boolean(stayLocked),
          allowNewDeposit: !stayLocked && can("finance.payment_create"),
          financialSummary: financialSummary ?? null,
          lockedRoomLabel,
        }
      : null;

  // Lock body scroll for the modal's lifetime and return focus to the trigger on
  // unmount — exactly the pattern `Modal.tsx` uses — so the list underneath cannot
  // scroll and keyboard focus is restored when the dialog closes.
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, []);

  // Move focus to the active step region on step change (SR + keyboard).
  useEffect(() => {
    stepBodyRef.current?.focus();
  }, [step]);

  // Announce + focus the success screen when it appears (SR + keyboard).
  useEffect(() => {
    if (success) successRef.current?.focus();
  }, [success]);

  const close = useCallback(() => {
    if (onClose) onClose();
    else router.push(LIST_ROUTE);
  }, [onClose, router]);

  // Success-screen "View reservation" (§10): hand the confirmed record to the host
  // to open its details; with no host (standalone route) just close.
  const viewReservation = useCallback(() => {
    if (!success) return;
    if (onViewReservation) onViewReservation(success.reservation);
    else close();
  }, [success, onViewReservation, close]);

  // Success-screen "New reservation" (§10): reset to a FRESH empty create draft —
  // never carrying the just-saved reservation's data — and dismiss the screen.
  const startNew = useCallback(() => {
    actions.reset();
    setStep(0);
    setError(null);
    setErrorStep(null);
    setPendingNew(false);
    setPrintOpen(false);
    setSuccess(null);
  }, [actions]);

  // Escape closes the dialog unless a submit is in flight (mirrors `Modal.tsx`) or
  // the print preview is open (Escape then belongs to the preview); backdrop click
  // is handled on the overlay below.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy && !printOpen) close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [busy, printOpen, close]);

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
    // Belt-and-braces re-entry guard: the Save button is already disabled while
    // busy, but never allow a second concurrent submit.
    if (busy) return;
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
        // §11 — refresh the list in place, then show the success screen (§8): the
        // modal stays open on the confirmed record until the user leaves it.
        onSaved?.();
        setSuccess({ reservation: outcome.reservation, kind: "edit" });
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
      const savedNumber = outcome.reservation.reservation_number;
      if (outcome.checkIn) {
        notify(w.booking.checkInSuccessNumber.replace("{number}", savedNumber));
      } else {
        notify(t.reservations.savedWithNumber.replace("{number}", savedNumber));
      }
      // §11 — refresh the list in place, then show the success screen (§8) with the
      // confirmed backend record (final auto-assigned room, status, financials).
      onSaved?.();
      setSuccess({
        reservation: outcome.reservation,
        kind: outcome.checkIn ? "immediate" : "create",
      });
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const isLast = step === STEPS.length - 1;
  const title = isEdit ? w.editTitle : w.createTitle;
  // Save is the single final action (§32): the SAME label whether or not an
  // immediate check-in is toggled — the existing submit runs the right atomic
  // backend call (the immediate group already explains the one-step behaviour).
  const saveLabel = isEdit ? w.submitEdit : w.submit;

  // Success-screen derivations (§8/§9) — all from the CONFIRMED backend record.
  const successTitle = success
    ? success.kind === "immediate"
      ? sc.immediateTitle
      : success.kind === "edit"
        ? sc.editedTitle
        : sc.createdTitle
    : null;
  const successHint = success
    ? success.kind === "immediate"
      ? sc.immediateHint
      : success.kind === "edit"
        ? sc.editedHint
        : sc.createdHint
    : null;
  const headerTitle = successTitle ?? title;
  // The FINAL room line (auto-assign resolved) — the room with a number, else the
  // first line; drives the room / floor / type cells on the success screen (§9).
  const successLine = success
    ? success.reservation.lines.find((line) => line.room_number) ??
      success.reservation.lines[0] ??
      null
    : null;
  const successShowMoney =
    success !== null &&
    can("finance.view") &&
    success.reservation.reservation_total !== null;

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className="resform-overlay"
      role="presentation"
      onMouseDown={(event) => {
        // Backdrop click closes — but never mid-submit, never while the print
        // preview is open, and never a click that started inside and dragged out.
        if (event.target === event.currentTarget && !busy && !printOpen) close();
      }}
    >
      <section
        className="resform-shell"
        role="dialog"
        aria-modal="true"
        aria-label={headerTitle}
      >
        {/* Band 1 — header: close + (success check) + title + number slot. */}
        <header className="resform-header">
          <IconButton
            label={t.common.close}
            icon={X}
            onClick={close}
            disabled={busy}
          />
          {success ? (
            <CheckCircle2
              className="resform-header__check"
              size={20}
              aria-hidden
            />
          ) : null}
          <div className="resform-header__titles">
            <span className="resform-header__title">{headerTitle}</span>
          </div>
          <div className="resform-header__slot">
            {success ? (
              <Badge tone="success">
                {success.reservation.reservation_number}
              </Badge>
            ) : isEdit && reservation ? (
              <span className="resform-header__number">
                {reservation.reservation_number}
              </span>
            ) : (
              <Badge tone="neutral">{w.booking.autoAssigned}</Badge>
            )}
          </div>
        </header>

        {success ? (
          /* Post-save SUCCESS SCREEN (§8–§12): no auto-close. The confirmed,
             backend-owned record is the source of truth, with Print / View /
             Close / New. It reuses the ONE scroll band so tall records scroll. */
          <div className="resform-main">
            <div className="resform-content">
              <div
                ref={successRef}
                tabIndex={-1}
                role="status"
                aria-live="polite"
                className="resform-success"
              >
                <span className="resform-success__mark" aria-hidden>
                  <CheckCircle2 size={32} />
                </span>
                <div className="resform-success__head">
                  <span className="resform-success__title">{successTitle}</span>
                  {successHint ? (
                    <span className="resform-success__hint">{successHint}</span>
                  ) : null}
                </div>

                {pendingNew ? (
                  <div
                    className="resform-success__confirm"
                    role="alertdialog"
                    aria-label={sc.newConfirmTitle}
                  >
                    <strong>{sc.newConfirmTitle}</strong>
                    <span className="muted">{sc.newConfirmBody}</span>
                    <div className="resform-success__confirm-actions">
                      <Button size="sm" onClick={startNew}>
                        {sc.newConfirm}
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setPendingNew(false)}
                      >
                        {w.cancel}
                      </Button>
                    </div>
                  </div>
                ) : null}

                {/* §9 — confirmed values, NEVER the pre-save draft. */}
                <dl
                  className="resform-success__grid"
                  aria-label={sc.detailsHeading}
                >
                  <div className="resform-success__item">
                    <dt>{sc.reservationNumber}</dt>
                    <dd>{success.reservation.reservation_number}</dd>
                  </div>
                  <div className="resform-success__item">
                    <dt>{sc.guest}</dt>
                    <dd>{success.reservation.primary_guest_name || "—"}</dd>
                  </div>
                  <div className="resform-success__item">
                    <dt>{sc.room}</dt>
                    <dd>{successLine?.room_number || "—"}</dd>
                  </div>
                  <div className="resform-success__item">
                    <dt>{sc.floor}</dt>
                    <dd>
                      {successLine?.floor_number ??
                        successLine?.floor_name ??
                        "—"}
                    </dd>
                  </div>
                  <div className="resform-success__item">
                    <dt>{sc.roomType}</dt>
                    <dd>{successLine?.room_type_name || "—"}</dd>
                  </div>
                  <div className="resform-success__item">
                    <dt>{sc.checkIn}</dt>
                    <dd>{formatDate(success.reservation.check_in_date, locale)}</dd>
                  </div>
                  <div className="resform-success__item">
                    <dt>{sc.checkOut}</dt>
                    <dd>
                      {formatDate(success.reservation.check_out_date, locale)}
                    </dd>
                  </div>
                  <div className="resform-success__item">
                    <dt>{sc.nights}</dt>
                    <dd>{success.reservation.nights}</dd>
                  </div>
                  <div className="resform-success__item">
                    <dt>{sc.persons}</dt>
                    <dd>{success.reservation.total_guests}</dd>
                  </div>
                  <div className="resform-success__item">
                    <dt>{sc.status}</dt>
                    <dd>
                      <Badge
                        tone={reservationStatusTone(success.reservation.status)}
                      >
                        {reservationStatusLabel(success.reservation.status, t)}
                      </Badge>
                    </dd>
                  </div>
                  {success.reservation.stay_status ? (
                    <div className="resform-success__item">
                      <dt>{sc.stayStatus}</dt>
                      <dd>
                        <Badge
                          tone={stayStatusTone(success.reservation.stay_status)}
                        >
                          {stayStatusLabel(success.reservation.stay_status, t)}
                        </Badge>
                      </dd>
                    </div>
                  ) : null}
                  {successShowMoney ? (
                    <>
                      <div className="resform-success__item">
                        <dt>{sc.total}</dt>
                        <dd>
                          {formatMoney(
                            success.reservation.reservation_total,
                            success.reservation.currency,
                            locale,
                          )}
                        </dd>
                      </div>
                      <div className="resform-success__item">
                        <dt>{sc.paid}</dt>
                        <dd>
                          {formatMoney(
                            success.reservation.paid,
                            success.reservation.currency,
                            locale,
                          )}
                        </dd>
                      </div>
                      <div className="resform-success__item">
                        <dt>{sc.remaining}</dt>
                        <dd>
                          {formatMoney(
                            success.reservation.remaining,
                            success.reservation.currency,
                            locale,
                          )}
                        </dd>
                      </div>
                    </>
                  ) : null}
                </dl>
              </div>
            </div>
          </div>
        ) : (
          <>
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
                {editReadOnly ? (
                  <Alert tone="info">{w.editReadOnly}</Alert>
                ) : null}
                {error ? <Alert tone="error">{error}</Alert> : null}

                {/* Active step body — focusable region for step announcements. */}
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
                    <DocumentsStep draft={draft} actions={actions} />
                  ) : null}
                  {STEPS[step] === "booking" ? (
                    <BookingStep
                      draft={draft}
                      actions={actions}
                      editContext={editContext}
                    />
                  ) : null}
                </div>
              </div>
            </div>
          </>
        )}

        {/* Band 4 — fixed footer. Success: Close / View / New + Print (primary).
            Wizard: Cancel / Back on the start, primary on the end. */}
        <footer className="resform-footer">
          {success ? (
            <>
              <Button variant="secondary" onClick={close}>
                {t.common.close}
              </Button>
              {onViewReservation ? (
                <Button variant="ghost" icon={Eye} onClick={viewReservation}>
                  {sc.view}
                </Button>
              ) : null}
              {!isEdit ? (
                <Button
                  variant="ghost"
                  icon={Plus}
                  onClick={() => setPendingNew(true)}
                >
                  {sc.newReservation}
                </Button>
              ) : null}
              <Button
                className="resform-footer__primary"
                icon={Printer}
                onClick={() => setPrintOpen(true)}
              >
                {sc.print}
              </Button>
            </>
          ) : (
            <>
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
            </>
          )}
        </footer>
      </section>

      {/* FE-C print preview — opened from the success screen. It READS the SAVED
          reservation by id (idempotent, §12): closing it or a failed print never
          touches the saved record, and it offers its own retry. */}
      <ReservationPrintPreview
        open={printOpen}
        reservation={success?.reservation}
        onClose={() => setPrintOpen(false)}
      />
    </div>,
    document.body,
  );
}
