"use client";

import { CheckCircle2, Link2Off, Plus, Trash2, Users } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  FormField,
  Icon,
  Input,
  SectionCard,
  Select,
  Switch,
} from "@/components/ui";
import type { Guest, OccupantRelationship } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { useGuestLookup } from "./useGuestLookup";
import type {
  CompanionsDraft,
  OccupantDraft,
  ReservationDraftActions,
} from "./useReservationDraft";

/** The exact write set — order matters only for the select, values are frozen. */
const RELATIONSHIPS: OccupantRelationship[] = [
  "spouse",
  "child_adult",
  "parent",
  "sibling",
  "relative",
  "other",
];

/** Step 2 — companions. A "has companions" toggle reveals editable adult rows
 * (name fields + relationship + optional per-row guest link) and a children
 * COUNT (no per-child fields). Total persons is shown live. */
export function CompanionsStep({
  companions,
  total,
  actions,
}: {
  companions: CompanionsDraft;
  total: number;
  actions: ReservationDraftActions;
}) {
  const { t } = useI18n();
  const w = t.reservations.wizard;
  const c = w.companions;

  return (
    <SectionCard title={c.title} icon={Users} description={c.description}>
      <Switch
        id="wiz-has-companions"
        checked={companions.has_companions}
        onChange={actions.setHasCompanions}
        label={c.hasCompanions}
      />

      {companions.has_companions ? (
        <>
          <div className="stack-tight" aria-label={c.adultsTitle}>
            <p className="field__label">{c.adultsTitle}</p>
            {companions.occupants.length === 0 ? (
              <p className="muted small">{c.emptyAdults}</p>
            ) : (
              companions.occupants.map((occupant, index) => (
                <OccupantRow
                  key={occupant.key}
                  occupant={occupant}
                  index={index}
                  actions={actions}
                />
              ))
            )}
            <Button
              variant="secondary"
              size="sm"
              icon={Plus}
              onClick={actions.addOccupant}
            >
              {c.addAdult}
            </Button>
          </div>

          <div className="form-grid">
            <FormField
              label={c.childrenCount}
              htmlFor="wiz-children"
              hint={c.childrenHint}
            >
              <Input
                id="wiz-children"
                type="number"
                min="0"
                value={String(companions.children)}
                onChange={(e) => actions.setChildren(Number(e.target.value))}
              />
            </FormField>
          </div>
        </>
      ) : null}

      <Alert tone="info">
        {c.totalPersons}: <strong>{total}</strong>
      </Alert>
    </SectionCard>
  );
}

/** One adult companion row: identity fields, a relationship select, and an
 * optional per-row national-id lookup that links a central guest. */
function OccupantRow({
  occupant,
  index,
  actions,
}: {
  occupant: OccupantDraft;
  index: number;
  actions: ReservationDraftActions;
}) {
  const { t } = useI18n();
  const c = t.reservations.wizard.companions;
  const g = t.reservations.wizard.guest;
  const rel = t.reservations.wizard.relationship;

  const linked = occupant.guest_id !== null;
  const lookup = useGuestLookup({
    national_id: occupant.national_id,
    enabled: !linked,
  });

  const relationshipOptions = RELATIONSHIPS.map((value) => ({
    value,
    label: rel[value],
  }));

  const rowLabel = `${c.adultRow} ${index + 1}`;

  function apply(match: Guest) {
    actions.applyOccupantMatch(occupant.key, match);
  }

  return (
    <div className="stack-tight" role="group" aria-label={rowLabel}>
      <div className="line-row line-row--assign">
        <FormField label={g.firstName} htmlFor={`wiz-occ-first-${occupant.key}`}>
          <Input
            id={`wiz-occ-first-${occupant.key}`}
            value={occupant.first_name}
            onChange={(e) =>
              actions.setOccupantField(occupant.key, "first_name", e.target.value)
            }
          />
        </FormField>
        <FormField label={g.fatherName} htmlFor={`wiz-occ-father-${occupant.key}`}>
          <Input
            id={`wiz-occ-father-${occupant.key}`}
            value={occupant.father_name}
            onChange={(e) =>
              actions.setOccupantField(occupant.key, "father_name", e.target.value)
            }
          />
        </FormField>
        <FormField label={g.lastName} htmlFor={`wiz-occ-last-${occupant.key}`}>
          <Input
            id={`wiz-occ-last-${occupant.key}`}
            value={occupant.last_name}
            onChange={(e) =>
              actions.setOccupantField(occupant.key, "last_name", e.target.value)
            }
          />
        </FormField>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          icon={Trash2}
          onClick={() => actions.removeOccupant(occupant.key)}
        >
          {c.removeAdult}
        </Button>
      </div>

      <div className="line-row line-row--assign">
        <FormField
          label={c.relationship}
          htmlFor={`wiz-occ-rel-${occupant.key}`}
        >
          <Select
            id={`wiz-occ-rel-${occupant.key}`}
            value={occupant.relationship}
            placeholder={c.relationshipPlaceholder}
            options={relationshipOptions}
            onChange={(e) =>
              actions.setOccupantRelationship(
                occupant.key,
                e.target.value as OccupantRelationship | "",
              )
            }
          />
        </FormField>
        <FormField
          label={g.nationalId}
          htmlFor={`wiz-occ-nid-${occupant.key}`}
          hint={occupant.national_id_masked ? g.lookupMasked : undefined}
        >
          <Input
            id={`wiz-occ-nid-${occupant.key}`}
            value={occupant.national_id}
            autoComplete="off"
            onChange={(e) =>
              actions.setOccupantField(occupant.key, "national_id", e.target.value)
            }
          />
        </FormField>
        <FormField
          label={g.dateOfBirth}
          htmlFor={`wiz-occ-dob-${occupant.key}`}
        >
          <Input
            id={`wiz-occ-dob-${occupant.key}`}
            type="date"
            value={occupant.date_of_birth}
            onChange={(e) =>
              actions.setOccupantField(occupant.key, "date_of_birth", e.target.value)
            }
          />
        </FormField>
      </div>

      {linked ? (
        <p className="cluster muted small">
          <Icon icon={CheckCircle2} size="sm" />
          {g.lookupLinked}
          <Button
            variant="ghost"
            size="sm"
            icon={Link2Off}
            onClick={() => actions.unlinkOccupant(occupant.key)}
          >
            {g.lookupUnlink}
          </Button>
        </p>
      ) : lookup.status === "single" || lookup.status === "multiple" ? (
        <div className="stack-tight">
          {lookup.results.map((match) => (
            <div key={match.id} className="line-row">
              <span className="cluster">
                <strong>{match.full_name || "—"}</strong>
                {match.is_blocked ? (
                  <Badge tone="danger">{g.blockedBadge}</Badge>
                ) : null}
              </span>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => apply(match)}
              >
                {g.lookupUse}
              </Button>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
