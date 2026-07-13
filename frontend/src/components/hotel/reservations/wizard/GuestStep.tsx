"use client";

import { CheckCircle2, Link2Off, ShieldAlert, UserRound } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  FormField,
  Icon,
  Input,
  SectionCard,
  Switch,
} from "@/components/ui";
import type { Guest } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { useGuestLookup } from "./useGuestLookup";
import type { ReservationDraftActions, GuestDraft } from "./useReservationDraft";

/** Step 1 — the primary guest. Structured identity fields, a "no email"
 * toggle, a composed (editable) full name, and the debounced smart lookup that
 * offers to link an existing guest. Blocking + masking are backend-driven and
 * only surfaced here. */
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

  function apply(match: Guest) {
    actions.applyGuestMatch(match);
  }

  return (
    <SectionCard title={g.title} icon={UserRound} description={g.description}>
      {/* Linked / blocked banners --------------------------------------- */}
      {linked ? (
        <Alert tone={guest.is_blocked ? "error" : "success"}>
          <span className="cluster">
            {guest.is_blocked ? (
              <Icon icon={ShieldAlert} size="sm" />
            ) : (
              <Icon icon={CheckCircle2} size="sm" />
            )}
            {guest.is_blocked ? g.blockedBody : g.lookupLinked}
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

      {/* Lookup feedback ------------------------------------------------- */}
      <GuestLookupFeedback state={lookup} linked={linked} onApply={apply} />

      <div className="form-grid">
        <FormField label={g.firstName} htmlFor="wiz-guest-first">
          <Input
            id="wiz-guest-first"
            value={guest.first_name}
            onChange={(e) => actions.setGuestField("first_name", e.target.value)}
          />
        </FormField>
        <FormField label={g.fatherName} htmlFor="wiz-guest-father">
          <Input
            id="wiz-guest-father"
            value={guest.father_name}
            onChange={(e) => actions.setGuestField("father_name", e.target.value)}
          />
        </FormField>
        <FormField label={g.lastName} htmlFor="wiz-guest-last">
          <Input
            id="wiz-guest-last"
            value={guest.last_name}
            onChange={(e) => actions.setGuestField("last_name", e.target.value)}
          />
        </FormField>
        <FormField label={g.motherName} htmlFor="wiz-guest-mother">
          <Input
            id="wiz-guest-mother"
            value={guest.mother_name}
            onChange={(e) => actions.setGuestField("mother_name", e.target.value)}
          />
        </FormField>
      </div>

      <FormField label={g.fullName} htmlFor="wiz-guest-full" hint={g.fullNameHint}>
        <Input
          id="wiz-guest-full"
          value={guest.full_name}
          onChange={(e) => actions.setFullName(e.target.value)}
        />
      </FormField>

      <div className="form-grid">
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
        <FormField label={g.email} htmlFor="wiz-guest-email">
          <Input
            id="wiz-guest-email"
            type="email"
            value={guest.email}
            disabled={guest.no_email}
            autoComplete="off"
            onChange={(e) => actions.setGuestField("email", e.target.value)}
          />
        </FormField>
      </div>

      <Switch
        id="wiz-guest-no-email"
        checked={guest.no_email}
        onChange={actions.setNoEmail}
        label={g.noEmail}
      />
    </SectionCard>
  );
}

/** The lookup outcome UI: single (offer autofill), multiple (pick list),
 * none (a discreet "new guest" hint) or searching. Blocked candidates are
 * flagged and their "use" action still links them (the wizard then gates
 * proceeding). */
function GuestLookupFeedback({
  state,
  linked,
  onApply,
}: {
  state: ReturnType<typeof useGuestLookup>;
  linked: boolean;
  onApply: (guest: Guest) => void;
}) {
  const { t } = useI18n();
  const g = t.reservations.wizard.guest;

  if (linked) return null;
  if (state.status === "idle") return null;
  if (state.status === "searching") {
    return <p className="muted small">{g.lookupSearching}</p>;
  }
  if (state.status === "error") {
    return <p className="muted small">{g.lookupError}</p>;
  }
  if (state.status === "none") {
    return <p className="muted small">{g.lookupNone}</p>;
  }

  const heading = state.status === "single" ? g.lookupSingleTitle : g.lookupMultipleTitle;
  return (
    <div className="stack-tight" role="group" aria-label={heading}>
      <p className="muted small">{heading}</p>
      {state.results.map((match) => (
        <div key={match.id} className="line-row">
          <span className="cluster">
            <strong>{match.full_name || "—"}</strong>
            {match.is_vip ? <Badge tone="info">{g.vip}</Badge> : null}
            {match.is_blocked ? <Badge tone="danger">{g.blockedBadge}</Badge> : null}
            {match.phone ? <span className="muted small">{match.phone}</span> : null}
          </span>
          <Button variant="secondary" size="sm" onClick={() => onApply(match)}>
            {g.lookupUse}
          </Button>
        </div>
      ))}
    </div>
  );
}
