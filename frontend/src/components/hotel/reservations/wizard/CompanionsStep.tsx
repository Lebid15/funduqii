"use client";

import { useState } from "react";
import { CheckCircle2, Link2Off, Plus, Trash2, UserRound, Users } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  ConfirmDialog,
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

/** Step 2 — companions. A lead toggle reveals a group-type control (companions
 * vs. my family), the adult-companion CARDS (each with a visible title, a
 * confirm-guarded delete, and the full identity fields incl. mother name +
 * nationality), and a children COUNT (no per-child fields). Total persons is
 * shown live and can never be typed. The occupant `key` is preserved across
 * add/remove so the later document↔companion linkage stays stable (§8–§11). */
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

  const adults = companions.has_companions ? companions.occupants.length : 0;
  const children = companions.has_companions ? companions.children : 0;

  // Delete is confirm-guarded; hold the occupant awaiting confirmation.
  const [pendingDelete, setPendingDelete] = useState<OccupantDraft | null>(null);

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
          {/* Group type — a two-option segmented control (not a tiny select). */}
          <div className="stack-tight" role="group" aria-label={c.groupTypeLabel}>
            <p className="field__label">{c.groupTypeLabel}</p>
            <div className="cluster">
              <Button
                variant={
                  companions.group_type === "companions" ? "primary" : "secondary"
                }
                size="sm"
                aria-pressed={companions.group_type === "companions"}
                onClick={() => actions.setGroupType("companions")}
              >
                {c.groupTypeCompanions}
              </Button>
              <Button
                variant={
                  companions.group_type === "my_family" ? "primary" : "secondary"
                }
                size="sm"
                aria-pressed={companions.group_type === "my_family"}
                onClick={() => actions.setGroupType("my_family")}
              >
                {c.groupTypeFamily}
              </Button>
            </div>
            <p className="field__hint">{c.groupTypeHint}</p>
          </div>

          {/* Adult companion cards. */}
          <div className="stack" aria-label={c.adultsTitle}>
            <p className="field__label">{c.adultsTitle}</p>
            {companions.occupants.length === 0 ? (
              <p className="muted small">{c.emptyAdults}</p>
            ) : (
              companions.occupants.map((occupant, index) => (
                <OccupantCard
                  key={occupant.key}
                  occupant={occupant}
                  index={index}
                  actions={actions}
                  onRequestDelete={() => setPendingDelete(occupant)}
                />
              ))
            )}
            <div>
              <Button
                variant="secondary"
                size="sm"
                icon={Plus}
                onClick={actions.addOccupant}
              >
                {c.addAdult}
              </Button>
            </div>
          </div>

          {/* Children — a COUNT only. */}
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

      {/* Live total — read-only (guest + adult companions + children). */}
      <Alert tone="info">
        <span className="cluster">
          <span>
            {c.totalPersons}: <strong>{total}</strong>
          </span>
          {companions.has_companions ? (
            <span className="muted small">
              {c.adultsShort}: {adults} · {c.childrenShort}: {children}
            </span>
          ) : null}
        </span>
      </Alert>

      {/* Delete confirmation (no companion is removed without it). */}
      <ConfirmDialog
        open={pendingDelete !== null}
        title={c.removeAdultConfirmTitle}
        body={c.removeAdultConfirmBody}
        confirmLabel={c.removeAdult}
        cancelLabel={w.cancel}
        closeLabel={w.cancel}
        tone="danger"
        onConfirm={() => {
          if (pendingDelete) actions.removeOccupant(pendingDelete.key);
          setPendingDelete(null);
        }}
        onClose={() => setPendingDelete(null)}
      />
    </SectionCard>
  );
}

/** One adult companion CARD: a visible title, a header delete button (never
 * among the fields), the full identity fields (incl. mother name + nationality)
 * in a 3-up grid, a relationship select, and an optional per-row national-id
 * lookup that links a central guest without disturbing the occupant key. */
function OccupantCard({
  occupant,
  index,
  actions,
  onRequestDelete,
}: {
  occupant: OccupantDraft;
  index: number;
  actions: ReservationDraftActions;
  onRequestDelete: () => void;
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

  const cardTitle = `${c.adultRow} ${index + 1}`;
  const fieldId = (name: string) => `wiz-occ-${name}-${occupant.key}`;

  function apply(match: Guest) {
    actions.applyOccupantMatch(occupant.key, match);
  }

  return (
    <div className="section-card" role="group" aria-label={cardTitle}>
      <div className="section-card__head">
        <span className="section-card__icon">
          <Icon icon={UserRound} size="sm" />
        </span>
        <h4 className="section-card__title">{cardTitle}</h4>
        <Button
          type="button"
          variant="dangerSoft"
          size="sm"
          icon={Trash2}
          onClick={onRequestDelete}
          style={{ marginInlineStart: "auto" }}
        >
          {c.removeAdult}
        </Button>
      </div>

      <div className="section-card__body">
        <div className="form-grid form-grid--3">
          <FormField label={g.firstName} htmlFor={fieldId("first")}>
            <Input
              id={fieldId("first")}
              value={occupant.first_name}
              onChange={(e) =>
                actions.setOccupantField(occupant.key, "first_name", e.target.value)
              }
            />
          </FormField>
          <FormField label={g.lastName} htmlFor={fieldId("last")}>
            <Input
              id={fieldId("last")}
              value={occupant.last_name}
              onChange={(e) =>
                actions.setOccupantField(occupant.key, "last_name", e.target.value)
              }
            />
          </FormField>
          <FormField label={g.fatherName} htmlFor={fieldId("father")}>
            <Input
              id={fieldId("father")}
              value={occupant.father_name}
              onChange={(e) =>
                actions.setOccupantField(occupant.key, "father_name", e.target.value)
              }
            />
          </FormField>
          <FormField label={g.motherName} htmlFor={fieldId("mother")}>
            <Input
              id={fieldId("mother")}
              value={occupant.mother_name}
              onChange={(e) =>
                actions.setOccupantField(occupant.key, "mother_name", e.target.value)
              }
            />
          </FormField>
          <FormField
            label={g.nationalId}
            htmlFor={fieldId("nid")}
            hint={occupant.national_id_masked ? g.lookupMasked : undefined}
          >
            <Input
              id={fieldId("nid")}
              value={occupant.national_id}
              autoComplete="off"
              onChange={(e) =>
                actions.setOccupantField(occupant.key, "national_id", e.target.value)
              }
            />
          </FormField>
          <FormField label={g.dateOfBirth} htmlFor={fieldId("dob")}>
            <Input
              id={fieldId("dob")}
              type="date"
              value={occupant.date_of_birth}
              onChange={(e) =>
                actions.setOccupantField(occupant.key, "date_of_birth", e.target.value)
              }
            />
          </FormField>
          <FormField label={g.nationality} htmlFor={fieldId("nat")}>
            <Input
              id={fieldId("nat")}
              value={occupant.nationality}
              onChange={(e) =>
                actions.setOccupantField(occupant.key, "nationality", e.target.value)
              }
            />
          </FormField>
          <FormField label={c.relationship} htmlFor={fieldId("rel")}>
            <Select
              id={fieldId("rel")}
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
                <Button variant="secondary" size="sm" onClick={() => apply(match)}>
                  {g.lookupUse}
                </Button>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
