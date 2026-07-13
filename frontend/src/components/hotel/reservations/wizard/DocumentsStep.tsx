"use client";

import { useRef, useState } from "react";
import { Camera, FileText, Plus, Trash2, Upload } from "lucide-react";

import {
  Alert,
  Button,
  FormField,
  Input,
  SectionCard,
  Select,
} from "@/components/ui";
import type { ReservationDocumentType } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { composeFullName } from "./useReservationDraft";
import type {
  PendingDocument,
  ReservationDraftActions,
  ReservationDraft,
} from "./useReservationDraft";

/** Identity documents attached per person; family/marriage proofs are separate.
 * Narrowed (no empty member) so the i18n `types` map indexes cleanly. */
type PersonalDocType = "national_id" | "passport" | "residence" | "visa" | "other";
type FamilyDocType = "marriage_contract" | "family_book" | "family_statement";

const PERSONAL_TYPES: PersonalDocType[] = [
  "national_id",
  "passport",
  "residence",
  "visa",
  "other",
];
/** Proof documents that only make sense with companions in the room. */
const FAMILY_TYPES: FamilyDocType[] = [
  "marriage_contract",
  "family_book",
  "family_statement",
];

const ACCEPT_ATTR =
  ".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf";
const ACCEPTED_MIME = ["image/jpeg", "image/png", "image/webp", "application/pdf"];
const ACCEPTED_EXT = ["jpg", "jpeg", "png", "webp", "pdf"];
const MAX_BYTES = 10 * 1024 * 1024;

let docKeyCounter = 0;
function docKey(prefix: string): string {
  docKeyCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${docKeyCounter.toString(36)}`;
}

function isFamilyType(type: ReservationDocumentType): boolean {
  return (FAMILY_TYPES as string[]).includes(type);
}

/** Client-side hint only — the backend re-validates every upload. */
function validateFile(file: File): "type" | "size" | null {
  const name = file.name.toLowerCase();
  const okType =
    ACCEPTED_MIME.includes(file.type) ||
    ACCEPTED_EXT.some((ext) => name.endsWith(`.${ext}`));
  if (!okType) return "type";
  if (file.size > MAX_BYTES) return "size";
  return null;
}

/**
 * Step 3 — Documents. Per the primary guest and each adult companion: a document
 * type, an optional number, and front/back files (drag-drop + file picker +
 * native camera capture — no fake hardware-scanner control). Marriage/family
 * proof documents appear only when companions share the room. Files stage in
 * `draft.pendingDocuments`; they upload AFTER the reservation is created (the
 * upload needs the reservation id).
 */
export function DocumentsStep({
  draft,
  actions,
}: {
  draft: ReservationDraft;
  actions: ReservationDraftActions;
}) {
  const { t } = useI18n();
  const d = t.reservations.wizard.documents;

  const docs = draft.pendingDocuments;

  function personalDoc(occupantKey: string | null): PendingDocument | undefined {
    return docs.find(
      (doc) => doc.occupantKey === occupantKey && !isFamilyType(doc.doc_type),
    );
  }

  function upsertPersonal(occupantKey: string | null, patch: Partial<PendingDocument>) {
    const index = docs.findIndex(
      (doc) => doc.occupantKey === occupantKey && !isFamilyType(doc.doc_type),
    );
    if (index >= 0) {
      actions.setDocuments(docs.map((doc, i) => (i === index ? { ...doc, ...patch } : doc)));
    } else {
      actions.setDocuments([
        ...docs,
        {
          key: docKey("doc"),
          doc_type: "",
          number: "",
          occupantKey,
          front_file: null,
          back_file: null,
          ...patch,
        },
      ]);
    }
  }

  const familyDocs = docs.filter((doc) => isFamilyType(doc.doc_type));
  function addFamilyDoc() {
    actions.setDocuments([
      ...docs,
      {
        key: docKey("fam"),
        doc_type: "marriage_contract",
        number: "",
        occupantKey: null,
        front_file: null,
        back_file: null,
      },
    ]);
  }
  function updateFamilyDoc(key: string, patch: Partial<PendingDocument>) {
    actions.setDocuments(docs.map((doc) => (doc.key === key ? { ...doc, ...patch } : doc)));
  }
  function removeFamilyDoc(key: string) {
    actions.setDocuments(docs.filter((doc) => doc.key !== key));
  }

  const personalOptions = PERSONAL_TYPES.map((value) => ({
    value,
    label: d.types[value],
  }));
  const familyOptions = FAMILY_TYPES.map((value) => ({
    value,
    label: d.types[value],
  }));

  const companions = draft.companions.has_companions
    ? draft.companions.occupants
    : [];

  const primaryName =
    draft.guest.full_name.trim() ||
    composeFullName(draft.guest.first_name, draft.guest.father_name, draft.guest.last_name);

  return (
    <SectionCard title={d.title} icon={FileText} description={d.description}>
      <Alert tone="info">{d.uploadNote}</Alert>

      {/* Primary guest */}
      <PersonDocument
        idPrefix="wiz-doc-primary"
        heading={primaryName ? `${d.primaryHeading} — ${primaryName}` : d.primaryHeading}
        doc={personalDoc(null)}
        options={personalOptions}
        onSet={(patch) => upsertPersonal(null, patch)}
      />

      {/* Adult companions */}
      {companions.map((occupant, index) => {
        const name =
          composeFullName(occupant.first_name, occupant.father_name, occupant.last_name) ||
          `${d.companionHeading} ${index + 1}`;
        return (
          <PersonDocument
            key={occupant.key}
            idPrefix={`wiz-doc-occ-${occupant.key}`}
            heading={name}
            doc={personalDoc(occupant.key)}
            options={personalOptions}
            onSet={(patch) => upsertPersonal(occupant.key, patch)}
          />
        );
      })}

      {/* Family / marriage proof — only with companions */}
      {draft.companions.has_companions ? (
        <div className="stack-tight" aria-label={d.familyHeading}>
          <p className="field__label">{d.familyHeading}</p>
          <p className="muted small">{d.familyDescription}</p>
          {familyDocs.map((doc) => (
            <div className="stack-tight" key={doc.key}>
              <div className="line-row line-row--assign">
                <FormField label={d.docType} htmlFor={`wiz-fam-type-${doc.key}`}>
                  <Select
                    id={`wiz-fam-type-${doc.key}`}
                    value={doc.doc_type}
                    options={familyOptions}
                    onChange={(e) =>
                      updateFamilyDoc(doc.key, {
                        doc_type: e.target.value as ReservationDocumentType,
                      })
                    }
                  />
                </FormField>
                <FormField label={d.docNumber} htmlFor={`wiz-fam-num-${doc.key}`}>
                  <Input
                    id={`wiz-fam-num-${doc.key}`}
                    value={doc.number}
                    autoComplete="off"
                    onChange={(e) => updateFamilyDoc(doc.key, { number: e.target.value })}
                  />
                </FormField>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  icon={Trash2}
                  onClick={() => removeFamilyDoc(doc.key)}
                >
                  {d.removeDoc}
                </Button>
              </div>
              <div className="form-grid">
                <DocFileField
                  id={`wiz-fam-front-${doc.key}`}
                  label={d.front}
                  file={doc.front_file}
                  onPick={(file) => updateFamilyDoc(doc.key, { front_file: file })}
                  onClear={() => updateFamilyDoc(doc.key, { front_file: null })}
                />
                <DocFileField
                  id={`wiz-fam-back-${doc.key}`}
                  label={d.back}
                  file={doc.back_file}
                  onPick={(file) => updateFamilyDoc(doc.key, { back_file: file })}
                  onClear={() => updateFamilyDoc(doc.key, { back_file: null })}
                />
              </div>
            </div>
          ))}
          <Button
            type="button"
            variant="secondary"
            size="sm"
            icon={Plus}
            onClick={addFamilyDoc}
          >
            {d.addFamilyDoc}
          </Button>
        </div>
      ) : null}
    </SectionCard>
  );
}

/** One person's identity document: a type, an optional number and front/back
 * files. Number and files are gated on a chosen type so nothing stages that the
 * upload would silently drop. */
function PersonDocument({
  idPrefix,
  heading,
  doc,
  options,
  onSet,
}: {
  idPrefix: string;
  heading: string;
  doc: PendingDocument | undefined;
  options: { value: string; label: string }[];
  onSet: (patch: Partial<PendingDocument>) => void;
}) {
  const { t } = useI18n();
  const d = t.reservations.wizard.documents;
  const type = doc?.doc_type ?? "";
  const hasType = type !== "";

  return (
    <div className="stack-tight" aria-label={heading}>
      <p className="field__label">{heading}</p>
      <div className="line-row line-row--assign">
        <FormField label={d.docType} htmlFor={`${idPrefix}-type`}>
          <Select
            id={`${idPrefix}-type`}
            value={type}
            placeholder={d.docTypePlaceholder}
            options={options}
            onChange={(e) => onSet({ doc_type: e.target.value as ReservationDocumentType })}
          />
        </FormField>
        <FormField label={d.docNumber} htmlFor={`${idPrefix}-num`}>
          <Input
            id={`${idPrefix}-num`}
            value={doc?.number ?? ""}
            autoComplete="off"
            disabled={!hasType}
            onChange={(e) => onSet({ number: e.target.value })}
          />
        </FormField>
      </div>
      {hasType ? (
        <div className="form-grid">
          <DocFileField
            id={`${idPrefix}-front`}
            label={d.front}
            file={doc?.front_file ?? null}
            onPick={(file) => onSet({ front_file: file })}
            onClear={() => onSet({ front_file: null })}
          />
          <DocFileField
            id={`${idPrefix}-back`}
            label={d.back}
            file={doc?.back_file ?? null}
            onPick={(file) => onSet({ back_file: file })}
            onClear={() => onSet({ back_file: null })}
          />
        </div>
      ) : null}
    </div>
  );
}

/** A single file slot: a drag-drop target plus a file picker and a native camera
 * capture input (mobile). Rejects clearly-invalid files client-side with an
 * inline hint; the backend stays the authoritative validator. */
function DocFileField({
  id,
  label,
  file,
  onPick,
  onClear,
}: {
  id: string;
  label: string;
  file: File | null;
  onPick: (file: File) => void;
  onClear: () => void;
}) {
  const { t } = useI18n();
  const d = t.reservations.wizard.documents;
  const [error, setError] = useState<string | null>(null);
  // Real focusable triggers drive HIDDEN inputs via a ref click, so keyboard
  // users reach the file/camera controls (Tab to the button, Enter/Space opens
  // the native dialog) instead of a label that swallows focus.
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  function handle(selected: File | undefined | null) {
    if (!selected) return;
    const problem = validateFile(selected);
    if (problem === "type") {
      setError(d.invalidType);
      return;
    }
    if (problem === "size") {
      setError(d.invalidSize);
      return;
    }
    setError(null);
    onPick(selected);
  }

  return (
    <div className="field">
      <span className="field__label" id={`${id}-label`}>
        {label}
      </span>
      <div
        className="document-preview"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          handle(e.dataTransfer.files?.[0]);
        }}
      >
        <div className="document-preview__body">
          <p className="muted small">{file ? file.name : d.noFile}</p>
          <div className="cluster">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              icon={Upload}
              aria-describedby={`${id}-label`}
              onClick={() => fileInputRef.current?.click()}
            >
              {d.chooseFile}
            </Button>
            <input
              ref={fileInputRef}
              id={id}
              type="file"
              accept={ACCEPT_ATTR}
              hidden
              onChange={(e) => {
                handle(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              icon={Camera}
              aria-describedby={`${id}-label`}
              onClick={() => cameraInputRef.current?.click()}
            >
              {d.camera}
            </Button>
            <input
              ref={cameraInputRef}
              type="file"
              accept="image/*,application/pdf"
              capture="environment"
              hidden
              onChange={(e) => {
                handle(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            {file ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                icon={Trash2}
                onClick={() => {
                  setError(null);
                  onClear();
                }}
              >
                {d.removeFile}
              </Button>
            ) : null}
          </div>
        </div>
      </div>
      <span className="field__hint">
        {d.dropHint} · {d.accepted}
      </span>
      {error ? <span className="field__error">{error}</span> : null}
    </div>
  );
}
