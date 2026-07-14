"use client";

import { useEffect, useRef, useState } from "react";
import {
  Camera,
  Eye,
  FileText,
  Image as ImageIcon,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";

import {
  Button,
  DocumentPreviewCard,
  FormField,
  Icon,
  Input,
  Modal,
  SectionCard,
  Select,
} from "@/components/ui";
import type { ReservationDocument, ReservationDocumentType } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { DocumentViewer } from "../DocumentViewer";
import { composeFullName } from "./useReservationDraft";
import type {
  DocumentTarget,
  PendingDocument,
  ReservationDraftActions,
  ReservationDraft,
} from "./useReservationDraft";

/** Identity documents attached per person. Narrowed (no empty member) so the
 * i18n `types` map indexes cleanly. */
type PersonalDocType = "national_id" | "passport" | "residence" | "visa" | "other";
/** Relationship / family proof documents (attached at the reservation level). */
type RelationshipDocType =
  | "marriage_contract"
  | "family_book"
  | "family_statement"
  | "other";

const PERSONAL_TYPES: PersonalDocType[] = [
  "national_id",
  "passport",
  "residence",
  "visa",
  "other",
];
const RELATIONSHIP_TYPES: RelationshipDocType[] = [
  "marriage_contract",
  "family_book",
  "family_statement",
  "other",
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

/** Structural equality on the discriminated target — the occupant variant is
 * compared by its STABLE key so linkage survives add/remove/reorder. */
function sameTarget(a: DocumentTarget, b: DocumentTarget): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "occupant" && b.kind === "occupant") {
    return a.occupantKey === b.occupantKey;
  }
  return true;
}

function isPdfFile(file: File): boolean {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
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

/** A local object URL for a staged File, kept alive for the file's lifetime (the
 * thumbnail and the "View" overlay both read it) and REVOKED when the file
 * changes or the step unmounts — so cancelling the form or replacing a file never
 * leaks blob URLs. These are LOCAL previews of not-yet-uploaded files; the secure
 * server-side viewer is a separate concern. */
function useObjectUrl(file: File | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file) {
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);
  return url;
}

/**
 * Step 3 — Documents. Each subject (the primary guest and every ADULT companion)
 * gets ONE document card: a type, an optional number, one required "document
 * file" and one OPTIONAL "additional file" — never a forced front/back (§12).
 * Files can be uploaded from the device OR captured from the camera, previewed
 * locally (image thumbnail / PDF icon), viewed in an overlay, replaced or removed
 * before saving. A reservation-level relationship-proof section appears when the
 * group is "my family" or a companion is a spouse (§16). Documents stage in
 * `draft.pendingDocuments` and upload as PART of Save — there is no "upload after
 * creating" message (§13); the graceful partial-failure toast stays in the shell.
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

  // EDIT prefill (§33) — the saved document currently open in the secure viewer.
  const [viewerDoc, setViewerDoc] = useState<ReservationDocument | null>(null);

  function findByTarget(target: DocumentTarget): PendingDocument | undefined {
    return docs.find((doc) => sameTarget(doc.target, target));
  }

  /** Insert or patch the single document bound to a subject target. */
  function upsertByTarget(target: DocumentTarget, patch: Partial<PendingDocument>) {
    const index = docs.findIndex((doc) => sameTarget(doc.target, target));
    if (index >= 0) {
      actions.setDocuments(
        docs.map((doc, i) => (i === index ? { ...doc, ...patch } : doc)),
      );
    } else {
      actions.setDocuments([
        ...docs,
        {
          key: docKey("doc"),
          target,
          doc_type: "",
          number: "",
          file: null,
          additionalFile: null,
          ...patch,
        },
      ]);
    }
  }

  const proofDocs = docs.filter((doc) => doc.target.kind === "relationship_proof");
  function addProofDoc() {
    actions.setDocuments([
      ...docs,
      {
        key: docKey("proof"),
        target: { kind: "relationship_proof" },
        doc_type: "marriage_contract",
        number: "",
        file: null,
        additionalFile: null,
      },
    ]);
  }
  function updateProofDoc(key: string, patch: Partial<PendingDocument>) {
    actions.setDocuments(docs.map((doc) => (doc.key === key ? { ...doc, ...patch } : doc)));
  }
  function removeProofDoc(key: string) {
    actions.setDocuments(docs.filter((doc) => doc.key !== key));
  }

  const personalOptions = PERSONAL_TYPES.map((value) => ({ value, label: d.types[value] }));
  const relationshipOptions = RELATIONSHIP_TYPES.map((value) => ({
    value,
    label: d.types[value],
  }));

  const companions = draft.companions.has_companions
    ? draft.companions.occupants
    : [];

  const primaryName =
    draft.guest.full_name.trim() ||
    composeFullName(
      draft.guest.first_name,
      draft.guest.father_name,
      draft.guest.last_name,
    );

  // §16 — relationship proof when the group is a family OR any companion is a
  // spouse. Attached to the whole reservation (never per child).
  const showRelationshipProof =
    draft.companions.has_companions &&
    (draft.companions.group_type === "my_family" ||
      draft.companions.occupants.some((o) => o.relationship === "spouse"));

  return (
    <>
    <SectionCard title={d.title} icon={FileText} description={d.description}>
      {/* Primary guest. */}
      <PersonDocumentCard
        idPrefix="wiz-doc-primary"
        heading={primaryName ? `${d.primaryHeading} — ${primaryName}` : d.primaryHeading}
        doc={findByTarget({ kind: "primary" })}
        options={personalOptions}
        onSet={(patch) => upsertByTarget({ kind: "primary" }, patch)}
        onViewExisting={setViewerDoc}
      />

      {/* Adult companions — one card each, bound by the STABLE occupant key. */}
      {companions.map((occupant, index) => {
        const name =
          composeFullName(
            occupant.first_name,
            occupant.father_name,
            occupant.last_name,
          ) || `${d.companionHeading} ${index + 1}`;
        const target: DocumentTarget = {
          kind: "occupant",
          occupantKey: occupant.key,
        };
        return (
          <PersonDocumentCard
            key={occupant.key}
            idPrefix={`wiz-doc-occ-${occupant.key}`}
            heading={`${d.companionHeading} ${index + 1} — ${name}`}
            doc={findByTarget(target)}
            options={personalOptions}
            onSet={(patch) => upsertByTarget(target, patch)}
            onViewExisting={setViewerDoc}
          />
        );
      })}

      {/* Relationship / family proof — reservation level (§16). */}
      {showRelationshipProof ? (
        <div className="stack" aria-label={d.familyHeading}>
          <p className="field__label">{d.familyHeading}</p>
          <p className="muted small">{d.familyDescription}</p>
          {proofDocs.map((doc, index) => (
            <div
              className="section-card"
              key={doc.key}
              role="group"
              aria-label={`${d.familyHeading} ${index + 1}`}
            >
              <div className="section-card__head">
                <span className="section-card__icon">
                  <Icon icon={FileText} size="sm" />
                </span>
                <h4 className="section-card__title">
                  {`${d.familyHeading} ${index + 1}`}
                </h4>
                <Button
                  type="button"
                  variant="dangerSoft"
                  size="sm"
                  icon={Trash2}
                  onClick={() => removeProofDoc(doc.key)}
                  style={{ marginInlineStart: "auto" }}
                >
                  {d.removeDoc}
                </Button>
              </div>
              <div className="section-card__body">
                <DocumentFields
                  idPrefix={`wiz-proof-${doc.key}`}
                  doc={doc}
                  options={relationshipOptions}
                  onSet={(patch) => updateProofDoc(doc.key, patch)}
                  onViewExisting={setViewerDoc}
                />
              </div>
            </div>
          ))}
          <div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              icon={Plus}
              onClick={addProofDoc}
            >
              {d.addFamilyDoc}
            </Button>
          </div>
        </div>
      ) : null}
    </SectionCard>

    {/* Secure in-app viewer for an already-saved document (edit prefill, §18/§33).
        Fetches bytes through the authenticated BFF — never a raw URL. */}
    <DocumentViewer
      open={viewerDoc !== null}
      document={viewerDoc ?? undefined}
      onClose={() => setViewerDoc(null)}
    />
    </>
  );
}

/** One subject's document CARD: a header (icon + who it belongs to) and the
 * document fields. The heading names the exact person so companion documents can
 * never be confused (§14/§15). */
function PersonDocumentCard({
  idPrefix,
  heading,
  doc,
  options,
  onSet,
  onViewExisting,
}: {
  idPrefix: string;
  heading: string;
  doc: PendingDocument | undefined;
  options: { value: string; label: string }[];
  onSet: (patch: Partial<PendingDocument>) => void;
  onViewExisting: (doc: ReservationDocument) => void;
}) {
  return (
    <div className="section-card" role="group" aria-label={heading}>
      <div className="section-card__head">
        <span className="section-card__icon">
          <Icon icon={FileText} size="sm" />
        </span>
        <h4 className="section-card__title">{heading}</h4>
      </div>
      <div className="section-card__body">
        <DocumentFields
          idPrefix={idPrefix}
          doc={doc}
          options={options}
          onSet={onSet}
          onViewExisting={onViewExisting}
        />
      </div>
    </div>
  );
}

/** The document body shared by personal and relationship-proof cards: a type
 * Select, an optional number, the required document file, and an OPTIONAL
 * additional file revealed on demand (never a forced back side). Number and files
 * gate on a chosen type so nothing stages that the upload would silently drop. */
function DocumentFields({
  idPrefix,
  doc,
  options,
  onSet,
  onViewExisting,
}: {
  idPrefix: string;
  doc: PendingDocument | undefined;
  options: { value: string; label: string }[];
  onSet: (patch: Partial<PendingDocument>) => void;
  onViewExisting: (doc: ReservationDocument) => void;
}) {
  const { t } = useI18n();
  const d = t.reservations.wizard.documents;
  const type = doc?.doc_type ?? "";
  const hasType = type !== "";
  const existing = doc?.existing ?? null;

  // A local reveal for the optional attachment; if a file already exists (e.g.
  // an edit prefill) it stays visible regardless.
  const [showAdditional, setShowAdditional] = useState(false);
  const additionalVisible = showAdditional || (doc?.additionalFile ?? null) !== null;

  return (
    <>
      <div className="form-grid">
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
        <div className="stack-tight">
          <StagedFileField
            id={`${idPrefix}-file`}
            label={d.documentFile}
            file={doc?.file ?? null}
            saved={existing !== null}
            onView={existing ? () => onViewExisting(existing) : undefined}
            onPick={(file) => onSet({ file })}
            onClear={() => onSet({ file: null })}
          />
          {additionalVisible ? (
            <StagedFileField
              id={`${idPrefix}-extra`}
              label={d.additionalFile}
              file={doc?.additionalFile ?? null}
              onPick={(file) => onSet({ additionalFile: file })}
              onClear={() => {
                onSet({ additionalFile: null });
                setShowAdditional(false);
              }}
            />
          ) : (
            <div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                icon={Plus}
                onClick={() => setShowAdditional(true)}
              >
                {d.addAdditionalFile}
              </Button>
            </div>
          )}
        </div>
      ) : null}
    </>
  );
}

/** A single neutral file slot: empty state offers device upload + native camera
 * capture (drag-drop too); filled state shows a local preview tile (image
 * thumbnail / PDF icon) with View, Replace and Remove. Real focusable buttons
 * drive hidden inputs via a ref click so keyboard users reach every control. The
 * backend stays the authoritative validator; the inline hint is client-side only. */
function StagedFileField({
  id,
  label,
  file,
  saved = false,
  onView,
  onPick,
  onClear,
}: {
  id: string;
  label: string;
  file: File | null;
  /** EDIT prefill (§33) — a document is already saved server-side. When true and
   * nothing new is staged, the slot shows an "on file" tile (View + Replace)
   * instead of the empty upload tile; staging a file switches to the replace flow. */
  saved?: boolean;
  onView?: () => void;
  onPick: (file: File) => void;
  onClear: () => void;
}) {
  const { t } = useI18n();
  const d = t.reservations.wizard.documents;
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const objectUrl = useObjectUrl(file);

  const isImage = file?.type.startsWith("image/") ?? false;
  const isPdf = file ? isPdfFile(file) : false;
  const labelId = `${id}-label`;

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
      <span className="field__label" id={labelId}>
        {label}
      </span>

      {/* Hidden inputs stay mounted in both states so Replace re-opens them. */}
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
        <DocumentPreviewCard
          icon={isPdf ? FileText : ImageIcon}
          title={file.name}
        >
          <div className="stack-tight">
            {isImage && objectUrl ? (
              // Local blob preview — next/image can't optimize an object URL.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={objectUrl}
                alt={d.previewImageAlt}
                style={{
                  maxBlockSize: "var(--space-16)",
                  maxInlineSize: "100%",
                  borderRadius: "var(--radius-md)",
                }}
              />
            ) : null}
            <div className="cluster">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                icon={Eye}
                onClick={() => setViewing(true)}
              >
                {d.view}
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                icon={RefreshCw}
                onClick={() => fileInputRef.current?.click()}
              >
                {d.replace}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                icon={Trash2}
                onClick={() => {
                  setError(null);
                  setViewing(false);
                  onClear();
                }}
              >
                {d.removeFile}
              </Button>
            </div>
          </div>
        </DocumentPreviewCard>
      ) : saved ? (
        // EDIT prefill — the document is already on file. View it in the secure
        // viewer, or Replace to stage a new file (uploaded via the replace endpoint).
        <DocumentPreviewCard icon={FileText} title={d.savedDocument}>
          <div className="stack-tight">
            <p className="muted small">{d.savedDocumentHint}</p>
            <div className="cluster">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                icon={Eye}
                onClick={onView}
                disabled={!onView}
              >
                {d.view}
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                icon={RefreshCw}
                onClick={() => fileInputRef.current?.click()}
              >
                {d.replace}
              </Button>
            </div>
          </div>
        </DocumentPreviewCard>
      ) : (
        <div
          className="document-preview"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            handle(e.dataTransfer.files?.[0]);
          }}
        >
          <div className="document-preview__body">
            <p className="muted small">{d.noFile}</p>
            <div className="cluster">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                icon={Upload}
                aria-describedby={labelId}
                onClick={() => fileInputRef.current?.click()}
              >
                {d.chooseFile}
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                icon={Camera}
                aria-describedby={labelId}
                onClick={() => cameraInputRef.current?.click()}
              >
                {d.camera}
              </Button>
            </div>
          </div>
        </div>
      )}

      <span className="field__hint">
        {d.dropHint} · {d.accepted}
      </span>
      {error ? <span className="field__error">{error}</span> : null}

      {/* Local preview overlay — reads the same object URL, closed with Escape or
          the X. The URL is revoked by `useObjectUrl` on change/unmount. */}
      <Modal
        open={viewing && objectUrl !== null}
        onClose={() => setViewing(false)}
        title={file?.name ?? label}
        closeLabel={d.close}
        size="lg"
      >
        {objectUrl && isImage ? (
          // Local blob preview — next/image can't optimize an object URL.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={objectUrl}
            alt={d.previewImageAlt}
            style={{ maxInlineSize: "100%", blockSize: "auto" }}
          />
        ) : objectUrl ? (
          <iframe
            src={objectUrl}
            title={file?.name ?? label}
            style={{ inlineSize: "100%", blockSize: "70vh", border: "none" }}
          />
        ) : null}
      </Modal>
    </div>
  );
}
