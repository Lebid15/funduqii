"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  BedDouble,
  CalendarRange,
  ClipboardList,
  DoorOpen,
  Eye,
  FileText,
  History,
  RefreshCw,
  StickyNote,
  Upload,
  UserRound,
  Users,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  FormField,
  Icon,
  Input,
  Modal,
  SectionCard,
  Select,
  useToast,
} from "@/components/ui";
import {
  getReservationLogs,
  listReservationDocuments,
  replaceReservationDocument,
  uploadReservationDocument,
} from "@/lib/api/reservations";
import { messageForError } from "@/lib/api/errors";
import type {
  Reservation,
  ReservationDocument,
  ReservationDocumentType,
  ReservationOccupant,
  ReservationStatusLogEntry,
} from "@/lib/api/types";
import {
  formatDate,
  formatDateTime,
  reservationStatusLabel,
  reservationStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { DocumentViewer } from "./DocumentViewer";
import {
  documentTypeLabel,
  isMaskedValue,
  occupantDisplayName,
  relationshipLabel,
  sourceIcon,
  sourceTone,
} from "./reservationShared";

/** Full reservation detail as a wide Modal drawer (reservations rework):
 * clear SECTIONS instead of tabs, each hidden when it has no data. Shows only
 * what the bookings backend actually stores — no amounts/folio, no uploads,
 * documents are the snapshot type + number only. */
export function ReservationDetailsModal({
  open,
  reservation,
  onClose,
  onEdit,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  reservation?: Reservation;
  onClose: () => void;
  onEdit: (r: Reservation) => void;
  onConfirm: (r: Reservation) => void;
  onCancel: (r: Reservation) => void;
}) {
  const { t, locale } = useI18n();
  const access = useHotelAccess();
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
  const [logs, setLogs] = useState<ReservationStatusLogEntry[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState(false);

  // Uploaded guest documents (metadata only) — gated by permission; the raw
  // bytes are never listed here, only `has_front`/`has_back`.
  const canViewDocs = can("reservation_documents.view");
  const canUploadDocs = can("reservation_documents.upload");
  const canReplaceDocs = can("reservation_documents.replace");
  const [docs, setDocs] = useState<ReservationDocument[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docsError, setDocsError] = useState(false);
  const [viewerDoc, setViewerDoc] = useState<ReservationDocument | null>(null);

  // Re-fetch the (view-gated) document list after an upload/replace succeeds.
  const reservationId = reservation?.id ?? null;
  const refreshDocs = useCallback(() => {
    if (reservationId === null || !canViewDocs) return;
    setDocsLoading(true);
    setDocsError(false);
    listReservationDocuments(reservationId)
      .then(setDocs)
      .catch(() => setDocsError(true))
      .finally(() => setDocsLoading(false));
  }, [reservationId, canViewDocs]);

  useEffect(() => {
    if (!open || !reservation) return;
    setLogsLoading(true);
    setLogsError(false);
    getReservationLogs(reservation.id)
      .then(setLogs)
      .catch(() => setLogsError(true))
      .finally(() => setLogsLoading(false));
  }, [open, reservation]);

  useEffect(() => {
    if (!open || reservationId === null || !canViewDocs) {
      setDocs([]);
      return;
    }
    refreshDocs();
  }, [open, reservationId, canViewDocs, refreshDocs]);

  if (!reservation) return null;
  const r = reservation;
  const d = t.reservations.details;
  const editable = r.status === "held" || r.status === "confirmed";
  const inHouse = r.has_in_house_stay;
  const docLabel = (v: string) =>
    (t.guests.documentTypes as Record<string, string>)[v] ?? v;
  const creator = r.created_by_name ?? r.created_by;
  const g = t.reservations.wizard.guest;
  const companions = r.occupants ?? [];
  const hasSnapshotDoc =
    r.primary_guest_document_type || r.primary_guest_document_number;
  // The documents section appears when there is a frozen snapshot OR the viewer
  // is available (which may surface uploaded files even without a snapshot) OR
  // the staff member can upload new documents.
  const showDocsSection = Boolean(hasSnapshotDoc) || canViewDocs || canUploadDocs;
  const hasNotes = r.notes || r.special_requests;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${d.title} ${r.reservation_number}`}
      closeLabel={t.common.close}
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t.common.close}
          </Button>
          {r.status === "confirmed" && can("stays.view") ? (
            <Link href="/hotel/front-desk?tab=arrivals" className="btn btn--ghost btn--sm">
              <Icon icon={DoorOpen} size="sm" />
              {t.reservations.views.frontDeskLink}
            </Link>
          ) : null}
          {editable && !inHouse && can("reservations.update") ? (
            <Button variant="ghost" onClick={() => onEdit(r)}>
              {d.edit}
            </Button>
          ) : null}
          {r.status === "held" && can("reservations.confirm") ? (
            <Button onClick={() => onConfirm(r)}>{d.confirm}</Button>
          ) : null}
          {editable && !inHouse && can("reservations.cancel") ? (
            <Button variant="danger" onClick={() => onCancel(r)}>
              {d.cancel}
            </Button>
          ) : null}
        </>
      }
    >
      <div className="stack">
        {inHouse ? <Alert tone="info">{t.reservations.views.inHouseNoCancel}</Alert> : null}
        {r.public_cancel_requested_at &&
        (r.status === "held" || r.status === "confirmed") ? (
          <Alert tone="warning">
            {d.publicCancelRequested} ({formatDate(r.public_cancel_requested_at, locale)})
            {r.public_cancel_reason ? ` — ${r.public_cancel_reason}` : ""}
          </Alert>
        ) : null}

        {/* Overview */}
        <SectionCard title={d.sectionOverview} icon={ClipboardList}>
          <div className="cluster">
            <Badge tone={reservationStatusTone(r.status)}>
              {reservationStatusLabel(r.status, t)}
            </Badge>
            <Badge tone={r.booking_kind === "instant" ? "success" : "info"}>
              {t.reservations.kind[r.booking_kind]}
            </Badge>
            <Badge tone={sourceTone(r.source)}>
              <Icon icon={sourceIcon(r.source)} size="sm" />
              {t.reservations.source[r.source]}
            </Badge>
          </div>
          <dl className="room-op-details">
            {creator ? (
              <div className="room-op-details__row">
                <dt>{d.createdBy}</dt>
                <dd>{creator}</dd>
              </div>
            ) : null}
            <div className="room-op-details__row">
              <dt>{t.common.createdAt}</dt>
              <dd>{formatDateTime(r.created_at, locale)}</dd>
            </div>
            <div className="room-op-details__row">
              <dt>{t.common.updatedAt}</dt>
              <dd>{formatDateTime(r.updated_at, locale)}</dd>
            </div>
          </dl>
        </SectionCard>

        {/* Stay */}
        <SectionCard title={d.sectionStay} icon={CalendarRange}>
          <dl className="room-op-details">
            <div className="room-op-details__row">
              <dt>{d.dates}</dt>
              <dd>
                {formatDate(r.check_in_date, locale)} → {formatDate(r.check_out_date, locale)}
              </dd>
            </div>
            {r.expected_arrival_time ? (
              <div className="room-op-details__row">
                <dt>{t.reservations.form.arrivalTime}</dt>
                <dd>{r.expected_arrival_time}</dd>
              </div>
            ) : null}
            <div className="room-op-details__row">
              <dt>{d.nights}</dt>
              <dd>{r.nights}</dd>
            </div>
            <div className="room-op-details__row">
              <dt>{d.guests}</dt>
              <dd>{r.total_guests}</dd>
            </div>
            {r.expected_payment_method ? (
              <div className="room-op-details__row">
                <dt>{t.reservations.form.expectedPayment}</dt>
                <dd>{t.reservations.expectedPayment[r.expected_payment_method]}</dd>
              </div>
            ) : null}
            {r.hold_expires_at ? (
              <div className="room-op-details__row">
                <dt>{d.holdExpires}</dt>
                <dd>{formatDateTime(r.hold_expires_at, locale)}</dd>
              </div>
            ) : null}
            {r.status === "cancelled" && r.cancellation_reason ? (
              <div className="room-op-details__row">
                <dt>{d.cancellationReason}</dt>
                <dd>{r.cancellation_reason}</dd>
              </div>
            ) : null}
          </dl>
          <div>
            <span className="res-detail__subhead">
              <Icon icon={BedDouble} size="sm" /> {d.rooms}
            </span>
            <ul className="mini-list">
              {r.lines.map((l) => (
                <li key={l.id} className="mini-list__row">
                  <span>
                    {l.room_type_name} <span className="muted">({l.room_type_code})</span>
                    {l.floor_name ? <span className="muted"> · {l.floor_name}</span> : null}
                  </span>
                  <span>
                    {l.room_number ? (
                      <Badge tone="info">
                        {d.room} {l.room_number}
                      </Badge>
                    ) : (
                      `× ${l.quantity}`
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </SectionCard>

        {/* Guest — structured snapshot (national_id is masked server-side). */}
        <SectionCard title={d.sectionGuest} icon={UserRound}>
          <dl className="room-op-details">
            <div className="room-op-details__row">
              <dt>{d.guest}</dt>
              <dd>{r.primary_guest_name}</dd>
            </div>
            {r.primary_guest_first_name ? (
              <div className="room-op-details__row">
                <dt>{g.firstName}</dt>
                <dd>{r.primary_guest_first_name}</dd>
              </div>
            ) : null}
            {r.primary_guest_last_name ? (
              <div className="room-op-details__row">
                <dt>{g.lastName}</dt>
                <dd>{r.primary_guest_last_name}</dd>
              </div>
            ) : null}
            {r.primary_guest_father_name ? (
              <div className="room-op-details__row">
                <dt>{g.fatherName}</dt>
                <dd>{r.primary_guest_father_name}</dd>
              </div>
            ) : null}
            {r.primary_guest_mother_name ? (
              <div className="room-op-details__row">
                <dt>{g.motherName}</dt>
                <dd>{r.primary_guest_mother_name}</dd>
              </div>
            ) : null}
            {r.primary_guest_national_id ? (
              <div className="room-op-details__row">
                <dt>{g.nationalId}</dt>
                <dd className={isMaskedValue(r.primary_guest_national_id) ? "muted" : undefined}>
                  {r.primary_guest_national_id}
                </dd>
              </div>
            ) : null}
            {r.primary_guest_date_of_birth ? (
              <div className="room-op-details__row">
                <dt>{g.dateOfBirth}</dt>
                <dd>{formatDate(r.primary_guest_date_of_birth, locale)}</dd>
              </div>
            ) : null}
            {r.primary_guest_nationality ? (
              <div className="room-op-details__row">
                <dt>{t.reservations.form.nationality}</dt>
                <dd>{r.primary_guest_nationality}</dd>
              </div>
            ) : null}
            {r.primary_guest_phone ? (
              <div className="room-op-details__row">
                <dt>{d.phone}</dt>
                <dd>{r.primary_guest_phone}</dd>
              </div>
            ) : null}
            {r.primary_guest_email ? (
              <div className="room-op-details__row">
                <dt>{d.email}</dt>
                <dd>{r.primary_guest_email}</dd>
              </div>
            ) : null}
          </dl>
        </SectionCard>

        {/* Companions — named adult occupants from the reservation snapshot. */}
        {companions.length > 0 ? (
          <SectionCard title={d.sectionCompanions} icon={Users}>
            <ul className="mini-list">
              {companions.map((occ) => (
                <li key={occ.id} className="mini-list__row">
                  <span>
                    {occupantDisplayName(occ, t)}
                    <span className="muted">
                      {" "}
                      · {relationshipLabel(occ.relationship, t)}
                    </span>
                  </span>
                  {occ.national_id ? (
                    <span
                      className={isMaskedValue(occ.national_id) ? "muted" : undefined}
                    >
                      {occ.national_id}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </SectionCard>
        ) : null}

        {/* Documents — the frozen snapshot (type + number) PLUS the uploaded
            files, listed by metadata only and opened in the secure viewer. */}
        {showDocsSection ? (
          <SectionCard title={d.sectionDocuments} icon={FileText}>
            {hasSnapshotDoc ? (
              <dl className="room-op-details">
                {r.primary_guest_document_type ? (
                  <div className="room-op-details__row">
                    <dt>{t.reservations.form.documentType}</dt>
                    <dd>{docLabel(r.primary_guest_document_type)}</dd>
                  </div>
                ) : null}
                {r.primary_guest_document_number ? (
                  <div className="room-op-details__row">
                    <dt>{t.reservations.form.documentNumber}</dt>
                    <dd
                      className={
                        isMaskedValue(r.primary_guest_document_number)
                          ? "muted"
                          : undefined
                      }
                    >
                      {r.primary_guest_document_number}
                    </dd>
                  </div>
                ) : null}
              </dl>
            ) : null}

            {canViewDocs ? (
              docsLoading ? (
                <p className="muted">{t.common.loading}</p>
              ) : docsError ? (
                <p className="muted">{d.documentsError}</p>
              ) : docs.length === 0 ? (
                <p className="muted">{d.documentsEmpty}</p>
              ) : (
                <ul className="mini-list">
                  {docs.map((doc) => {
                    const owner =
                      doc.occupant === null
                        ? t.reservations.wizard.documents.primaryHeading
                        : (() => {
                            const occ = companions.find(
                              (c) => c.id === doc.occupant,
                            );
                            return occ
                              ? occupantDisplayName(occ, t)
                              : t.reservations.wizard.documents.companionHeading;
                          })();
                    const canOpen = doc.has_front || doc.has_back;
                    return (
                      <li key={doc.id} className="mini-list__row">
                        <span>
                          {documentTypeLabel(doc.doc_type, t)}
                          <span className="muted"> · {owner}</span>
                          {doc.number ? (
                            <span
                              className={
                                isMaskedValue(doc.number) ? "muted" : undefined
                              }
                            >
                              {" "}
                              · {doc.number}
                            </span>
                          ) : null}
                        </span>
                        <span className="cluster">
                          {doc.has_front ? (
                            <Badge tone="neutral">
                              {t.reservations.wizard.documents.front}
                            </Badge>
                          ) : null}
                          {doc.has_back ? (
                            <Badge tone="neutral">
                              {t.reservations.wizard.documents.back}
                            </Badge>
                          ) : null}
                          {canOpen ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              icon={Eye}
                              onClick={() => setViewerDoc(doc)}
                            >
                              {d.documentsView}
                            </Button>
                          ) : null}
                          {canReplaceDocs ? (
                            <DocReplaceControl docId={doc.id} onReplaced={refreshDocs} />
                          ) : null}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )
            ) : null}

            {canUploadDocs && reservationId !== null ? (
              <DocumentUploadPanel
                reservationId={reservationId}
                companions={companions}
                onUploaded={refreshDocs}
              />
            ) : null}
          </SectionCard>
        ) : null}

        {/* Notes */}
        {hasNotes ? (
          <SectionCard title={d.sectionNotes} icon={StickyNote}>
            {r.notes ? (
              <div>
                <span className="res-detail__subhead">{d.notes}</span>
                <p>{r.notes}</p>
              </div>
            ) : null}
            {r.special_requests ? (
              <div>
                <span className="res-detail__subhead">{d.specialRequests}</span>
                <p>{r.special_requests}</p>
              </div>
            ) : null}
          </SectionCard>
        ) : null}

        {/* Status log */}
        <SectionCard title={d.sectionStatusLog} icon={History}>
          {logsLoading ? (
            <p className="muted">{t.common.loading}</p>
          ) : logsError ? (
            <p className="muted">{d.logsError}</p>
          ) : logs.length === 0 ? (
            <p className="muted">{d.noHistory}</p>
          ) : (
            <ul className="mini-list">
              {logs.map((log, i) => (
                <li key={i} className="mini-list__row">
                  <span>
                    {log.previous_status ? `${log.previous_status} → ` : ""}
                    {log.new_status}
                    {log.note ? ` · ${log.note}` : ""}
                  </span>
                  <span className="muted">{formatDateTime(log.created_at, locale)}</span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      {/* Secure blob viewer — a portal Modal; opens above these details. */}
      <DocumentViewer
        open={viewerDoc !== null}
        document={viewerDoc ?? undefined}
        onClose={() => setViewerDoc(null)}
      />
    </Modal>
  );
}

/** Accepted document formats — mirrors the wizard's client-side hint; the backend
 * stays the authoritative validator on every upload/replace. */
const DOC_ACCEPT =
  ".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf";

/** A keyboard-accessible file trigger: a real focusable `<button>` drives a
 * hidden `<input type="file">` via a ref (Tab reaches it, Enter/Space opens the
 * native dialog) — the same a11y pattern the wizard's DocumentsStep uses. */
function FilePickerButton({
  label,
  icon,
  variant = "secondary",
  loading,
  onPick,
}: {
  label: string;
  icon: LucideIcon;
  variant?: "secondary" | "ghost";
  loading?: boolean;
  onPick: (file: File) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <Button
        type="button"
        variant={variant}
        size="sm"
        icon={icon}
        loading={loading}
        onClick={() => ref.current?.click()}
      >
        {label}
      </Button>
      <input
        ref={ref}
        type="file"
        accept={DOC_ACCEPT}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onPick(file);
          e.target.value = "";
        }}
      />
    </>
  );
}

/** Per-document replace controls (front / back). Behind
 * `reservation_documents.replace`; refreshes the list and toasts on error. */
function DocReplaceControl({
  docId,
  onReplaced,
}: {
  docId: number;
  onReplaced: () => void;
}) {
  const { t } = useI18n();
  const { notify } = useToast();
  const d = t.reservations.details;
  const [busy, setBusy] = useState(false);

  async function replace(side: "front_file" | "back_file", file: File) {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append(side, file);
      await replaceReservationDocument(docId, fd);
      notify(d.documentReplaced);
      onReplaced();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <FilePickerButton
        label={d.documentReplaceFront}
        icon={RefreshCw}
        variant="ghost"
        loading={busy}
        onPick={(file) => replace("front_file", file)}
      />
      <FilePickerButton
        label={d.documentReplaceBack}
        icon={RefreshCw}
        variant="ghost"
        loading={busy}
        onPick={(file) => replace("back_file", file)}
      />
    </>
  );
}

/** Upload a new document from the reservation details — makes the partial-upload
 * toast's "retry from the reservation details" promise real. Behind
 * `reservation_documents.upload`; refreshes the list and toasts on error. */
function DocumentUploadPanel({
  reservationId,
  companions,
  onUploaded,
}: {
  reservationId: number;
  companions: ReservationOccupant[];
  onUploaded: () => void;
}) {
  const { t } = useI18n();
  const { notify } = useToast();
  const d = t.reservations.details;
  const wd = t.reservations.wizard.documents;

  const [docType, setDocType] = useState<ReservationDocumentType | "">("");
  const [number, setNumber] = useState("");
  const [person, setPerson] = useState(""); // "" = primary guest, else occupant id
  const [frontFile, setFrontFile] = useState<File | null>(null);
  const [backFile, setBackFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  const typeOptions = (
    Object.keys(wd.types) as Exclude<ReservationDocumentType, "">[]
  ).map((value) => ({ value, label: wd.types[value] }));
  const personOptions = [
    { value: "", label: wd.primaryHeading },
    ...companions.map((occ) => ({
      value: String(occ.id),
      label: occupantDisplayName(occ, t),
    })),
  ];

  const canSubmit =
    docType !== "" && (frontFile !== null || backFile !== null) && !busy;

  async function submit() {
    if (!canSubmit) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("doc_type", docType);
      if (number.trim()) fd.append("number", number.trim());
      if (person) fd.append("occupant", person);
      if (frontFile) fd.append("front_file", frontFile);
      if (backFile) fd.append("back_file", backFile);
      await uploadReservationDocument(reservationId, fd);
      notify(d.documentUploaded);
      setDocType("");
      setNumber("");
      setPerson("");
      setFrontFile(null);
      setBackFile(null);
      onUploaded();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack-tight">
      <span className="res-detail__subhead">
        <Icon icon={Upload} size="sm" /> {d.documentsAdd}
      </span>
      <div className="line-row line-row--assign">
        <FormField label={wd.docType} htmlFor="res-doc-up-type">
          <Select
            id="res-doc-up-type"
            value={docType}
            placeholder={wd.docTypePlaceholder}
            options={typeOptions}
            onChange={(e) => setDocType(e.target.value as ReservationDocumentType)}
          />
        </FormField>
        <FormField label={wd.docNumber} htmlFor="res-doc-up-num">
          <Input
            id="res-doc-up-num"
            value={number}
            autoComplete="off"
            disabled={docType === ""}
            onChange={(e) => setNumber(e.target.value)}
          />
        </FormField>
        {companions.length > 0 ? (
          <FormField label={d.documentPerson} htmlFor="res-doc-up-person">
            <Select
              id="res-doc-up-person"
              value={person}
              options={personOptions}
              onChange={(e) => setPerson(e.target.value)}
            />
          </FormField>
        ) : null}
      </div>
      <div className="cluster">
        <FilePickerButton
          label={frontFile ? frontFile.name : `${wd.front} · ${wd.chooseFile}`}
          icon={Upload}
          onPick={setFrontFile}
        />
        <FilePickerButton
          label={backFile ? backFile.name : `${wd.back} · ${wd.chooseFile}`}
          icon={Upload}
          onPick={setBackFile}
        />
      </div>
      <span className="field__hint">{wd.accepted}</span>
      <div>
        <Button
          type="button"
          variant="primary"
          size="sm"
          icon={Upload}
          loading={busy}
          disabled={!canSubmit}
          onClick={submit}
        >
          {d.documentUploadCta}
        </Button>
      </div>
    </div>
  );
}
