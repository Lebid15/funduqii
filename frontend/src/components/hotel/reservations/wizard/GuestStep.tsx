"use client";

import { useEffect, useRef, useState } from "react";
import { Link2Off, UserRound } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  ConfirmDialog,
  FormField,
  Input,
  SectionCard,
  Switch,
} from "@/components/ui";
import type { Guest } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { useGuestLookup } from "./useGuestLookup";
import {
  composeFullName,
  type ReservationDraftActions,
  type GuestDraft,
} from "./useReservationDraft";

/** Step 1 — the primary guest. The national id + phone lead the form because
 * they drive the debounced smart lookup (§6/§7). The full name is NOT an input:
 * it is composed, display-only, from the structured parts. A "no email" toggle
 * disables the email field. On a single lookup match with no staff-entered data
 * the guest is imported automatically; when data was already typed, a confirm
 * guards the overwrite. An id↔phone conflict is surfaced, never merged. Blocking
 * + masking stay backend-driven and are only surfaced here. */
export function GuestStep({
  guest,
  actions,
}: {
  guest: GuestDraft;
  actions: ReservationDraftActions;
}) {
  const { t } = useI18n();
  const w = t.reservations.wizard;
  const g = w.guest;

  const linked = guest.primary_guest_id !== null;
  const lookup = useGuestLookup({
    national_id: guest.national_id,
    phone: guest.phone,
    enabled: !linked,
  });

  // Any identity data the staff has already entered, beyond the lookup drivers
  // (id/phone). Its presence flips a single match from "auto-import" to
  // "confirm before overwrite".
  const hasTypedData = Boolean(
    guest.first_name.trim() ||
      guest.last_name.trim() ||
      guest.father_name.trim() ||
      guest.mother_name.trim() ||
      guest.nationality.trim() ||
      guest.date_of_birth ||
      guest.email.trim(),
  );

  // Pending overwrite confirmation (single match / manual pick over typed data).
  const [confirmMatch, setConfirmMatch] = useState<Guest | null>(null);

  // Auto-import a single match when nothing was typed yet — once per guest id.
  const autoApplied = useRef<number | null>(null);
  useEffect(() => {
    if (linked) {
      autoApplied.current = null;
      return;
    }
    if (lookup.status !== "single") return;
    const match = lookup.results[0];
    if (!match || hasTypedData) return;
    if (autoApplied.current === match.id) return;
    autoApplied.current = match.id;
    actions.applyGuestMatch(match);
  }, [linked, lookup.status, lookup.results, hasTypedData, actions]);

  /** Route a chosen match: overwrite-typed-data goes through a confirm. */
  function pick(match: Guest) {
    if (hasTypedData) setConfirmMatch(match);
    else actions.applyGuestMatch(match);
  }

  const composedName = composeFullName(
    guest.first_name,
    guest.father_name,
    guest.last_name,
  );

  return (
    // §7.1 — the guest step opts INTO the central compact density (Round 1). It is
    // scoped to this container only, so the project-wide default density and the
    // other wizard steps are unaffected.
    <div data-density="compact">
    <SectionCard title={g.title} icon={UserRound} description={g.description}>
      {/* Linked / blocked banner. */}
      {linked ? (
        <Alert tone={guest.is_blocked ? "error" : "success"}>
          <span className="cluster">
            {guest.is_blocked ? g.blockedBody : g.lookupReturning}
            <Button
              variant="ghost"
              size="sm"
              icon={Link2Off}
              onClick={actions.unlinkGuest}
            >
              {g.lookupUnlink}
            </Button>
          </span>
        </Alert>
      ) : null}

      {/* Row A — id + phone FIRST (they drive the lookup). */}
      <div className="form-grid">
        <FormField
          label={g.nationalId}
          htmlFor="wiz-guest-nid"
          hint={guest.national_id_masked ? g.lookupMasked : g.lookupHint}
        >
          <Input
            id="wiz-guest-nid"
            value={guest.national_id}
            inputMode="text"
            autoComplete="off"
            onChange={(e) => actions.setGuestField("national_id", e.target.value)}
          />
        </FormField>
        <FormField label={g.phone} htmlFor="wiz-guest-phone">
          <Input
            id="wiz-guest-phone"
            value={guest.phone}
            type="tel"
            autoComplete="off"
            onChange={(e) => actions.setGuestField("phone", e.target.value)}
          />
        </FormField>
      </div>

      {/* Lookup feedback. */}
      <GuestLookupFeedback state={lookup} linked={linked} onPick={pick} />

      {/* Row 2 — structured names (3-up: first · last · father). Mother-name
          moves to the start of Row 3 (§7.1) — the DOM/tab order is unchanged. */}
      <div className="form-grid form-grid--3">
        <FormField label={g.firstName} htmlFor="wiz-guest-first">
          <Input
            id="wiz-guest-first"
            value={guest.first_name}
            onChange={(e) => actions.setGuestField("first_name", e.target.value)}
          />
        </FormField>
        <FormField label={g.lastName} htmlFor="wiz-guest-last">
          <Input
            id="wiz-guest-last"
            value={guest.last_name}
            onChange={(e) => actions.setGuestField("last_name", e.target.value)}
          />
        </FormField>
        <FormField label={g.fatherName} htmlFor="wiz-guest-father">
          <Input
            id="wiz-guest-father"
            value={guest.father_name}
            onChange={(e) => actions.setGuestField("father_name", e.target.value)}
          />
        </FormField>
      </div>

      {/* Display-only composed full name (never an input) — stays after Row 2. */}
      {composedName ? (
        <p className="muted small">
          {g.composedName}: <strong>{composedName}</strong>
        </p>
      ) : null}

      {/* Row 3 — mother · nationality · date of birth (3-up). */}
      <div className="form-grid form-grid--3">
        <FormField label={g.motherName} htmlFor="wiz-guest-mother">
          <Input
            id="wiz-guest-mother"
            value={guest.mother_name}
            onChange={(e) => actions.setGuestField("mother_name", e.target.value)}
          />
        </FormField>
        <FormField label={g.nationality} htmlFor="wiz-guest-nat">
          <Input
            id="wiz-guest-nat"
            value={guest.nationality}
            onChange={(e) => actions.setGuestField("nationality", e.target.value)}
          />
        </FormField>
        <FormField label={g.dateOfBirth} htmlFor="wiz-guest-dob">
          <Input
            id="wiz-guest-dob"
            type="date"
            value={guest.date_of_birth}
            onChange={(e) => actions.setGuestField("date_of_birth", e.target.value)}
          />
        </FormField>
      </div>

      {/* Row 4 — email + the "no email" toggle (2-up). The switch shares the row
          as its own cell, aligned to the email INPUT (not its label) via the
          scoped `.guest-email-switch` helper; the long Arabic label wraps in-cell. */}
      <div className="form-grid">
        <FormField label={g.email} htmlFor="wiz-guest-email">
          <Input
            id="wiz-guest-email"
            type="email"
            value={guest.no_email ? "" : guest.email}
            disabled={guest.no_email}
            placeholder={guest.no_email ? g.noEmailPlaceholder : undefined}
            autoComplete="off"
            onChange={(e) => actions.setGuestField("email", e.target.value)}
          />
        </FormField>
        <div className="guest-email-switch">
          <Switch
            id="wiz-guest-no-email"
            checked={guest.no_email}
            onChange={actions.setNoEmail}
            label={g.noEmail}
          />
        </div>
      </div>

      {/* Overwrite guard — importing a match would replace typed-in data. */}
      <ConfirmDialog
        open={confirmMatch !== null}
        title={g.lookupOverwriteTitle}
        body={g.lookupOverwriteBody}
        confirmLabel={g.lookupOverwriteConfirm}
        cancelLabel={w.cancel}
        closeLabel={w.cancel}
        onConfirm={() => {
          if (confirmMatch) actions.applyGuestMatch(confirmMatch);
          setConfirmMatch(null);
        }}
        onClose={() => setConfirmMatch(null)}
      />
    </SectionCard>
    </div>
  );
}

/** The lookup outcome UI: searching (spinner), none (a discreet "new guest"
 * hint), conflict (a clear warning — never merged), or single/multiple (a small
 * pick list). Blocked candidates are flagged; picking still links them and the
 * shell then gates proceeding. */
function GuestLookupFeedback({
  state,
  linked,
  onPick,
}: {
  state: ReturnType<typeof useGuestLookup>;
  linked: boolean;
  onPick: (guest: Guest) => void;
}) {
  const { t } = useI18n();
  const g = t.reservations.wizard.guest;

  if (linked) return null;
  if (state.status === "idle") return null;
  if (state.status === "searching") {
    return (
      <p className="cluster muted small" aria-live="polite">
        <span className="spinner" aria-hidden="true" />
        {g.lookupSearching}
      </p>
    );
  }
  if (state.status === "error") {
    return <p className="muted small">{g.lookupError}</p>;
  }
  if (state.status === "none") {
    return <p className="muted small">{g.lookupNone}</p>;
  }
  if (state.status === "conflict") {
    return <Alert tone="warning">{g.lookupConflict}</Alert>;
  }

  const heading =
    state.status === "single" ? g.lookupSingleTitle : g.lookupMultipleTitle;
  return (
    <div className="stack-tight" role="group" aria-label={heading}>
      <p className="muted small">{heading}</p>
      {state.results.map((match) => (
        <div key={match.id} className="line-row">
          <span className="cluster">
            <strong>{match.full_name || "—"}</strong>
            {match.is_vip ? <Badge tone="vip">{g.vip}</Badge> : null}
            {match.is_blocked ? (
              <Badge tone="danger">{g.blockedBadge}</Badge>
            ) : null}
            {match.phone ? (
              <span className="muted small">{match.phone}</span>
            ) : null}
          </span>
          <Button variant="secondary" size="sm" onClick={() => onPick(match)}>
            {g.lookupUse}
          </Button>
        </div>
      ))}
    </div>
  );
}
