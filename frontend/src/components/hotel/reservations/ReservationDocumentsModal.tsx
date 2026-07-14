"use client";

import { useEffect, useState } from "react";
import { Eye, FileText } from "lucide-react";

import { Badge, Button, Icon, Modal } from "@/components/ui";
import { listReservationDocuments } from "@/lib/api/reservations";
import type { Reservation, ReservationDocument } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { DocumentViewer } from "./DocumentViewer";
import {
  documentTypeLabel,
  isRelationshipProofDoc,
  occupantDisplayName,
} from "./reservationShared";

/**
 * DOCUMENTS-ONLY secure modal for a reservation (RESERVATION-CARD refinement §9).
 * This is deliberately separate from the general reservation details: the card's
 * "Documents" button opens THIS viewer, never the details drawer. It lists the
 * reservation's uploaded documents by METADATA only (type + owner + which faces
 * exist) — no public URLs/paths — and opens each in the authenticated
 * {@link DocumentViewer} (primary guest + companions + relationship proof, split
 * into groups so a family record is never shown as the guest's own ID).
 *
 * The whole modal is gated behind `reservation_documents.view`; the backend
 * re-checks server-side regardless. No upload/replace controls live here — those
 * stay in the full details drawer.
 */
export function ReservationDocumentsModal({
  open,
  reservation,
  onClose,
}: {
  open: boolean;
  reservation?: Reservation;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const access = useHotelAccess();
  const canViewDocs =
    access === null ||
    (!access.loading && access.can("reservation_documents.view"));

  const d = t.reservations.details;
  const wd = t.reservations.wizard.documents;

  const [docs, setDocs] = useState<ReservationDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [viewerDoc, setViewerDoc] = useState<ReservationDocument | null>(null);

  const reservationId = reservation?.id ?? null;
  const companions = reservation?.occupants ?? [];

  useEffect(() => {
    if (!open || reservationId === null || !canViewDocs) {
      setDocs([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(false);
    listReservationDocuments(reservationId)
      .then((rows) => {
        if (!cancelled) setDocs(rows);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, reservationId, canViewDocs]);

  if (!reservation) return null;

  // §16/§39 — identity documents and relationship/family proofs are grouped
  // apart so a marriage contract is never mistaken for the guest's own ID.
  const identityDocs = docs.filter((doc) => !isRelationshipProofDoc(doc.doc_type));
  const proofDocs = docs.filter((doc) => isRelationshipProofDoc(doc.doc_type));

  // One document row — type + owner + which faces exist + a secure "View" that
  // opens the authenticated blob viewer. Never renders a raw URL/path.
  const renderDoc = (doc: ReservationDocument) => {
    const owner =
      doc.occupant === null
        ? wd.primaryHeading
        : (() => {
            const occ = companions.find((c) => c.id === doc.occupant);
            return occ ? occupantDisplayName(occ, t) : wd.companionHeading;
          })();
    const canOpen = doc.has_front || doc.has_back;
    return (
      <li key={doc.id} className="mini-list__row">
        <span>
          {documentTypeLabel(doc.doc_type, t)}
          <span className="muted"> · {owner}</span>
        </span>
        <span className="cluster">
          {doc.has_front ? <Badge tone="neutral">{wd.front}</Badge> : null}
          {doc.has_back ? <Badge tone="neutral">{wd.back}</Badge> : null}
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
        </span>
      </li>
    );
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${t.reservations.card.documentsTitle} ${reservation.reservation_number}`}
      closeLabel={t.common.close}
      size="lg"
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t.common.close}
        </Button>
      }
    >
      <div className="stack">
        {!canViewDocs ? (
          <p className="muted">{d.documentsError}</p>
        ) : loading ? (
          <p className="muted">{t.common.loading}</p>
        ) : error ? (
          <p className="muted">{d.documentsError}</p>
        ) : docs.length === 0 ? (
          <p className="muted">{d.documentsEmpty}</p>
        ) : (
          <>
            {identityDocs.length > 0 ? (
              <ul className="mini-list">{identityDocs.map(renderDoc)}</ul>
            ) : null}
            {proofDocs.length > 0 ? (
              <div>
                <span className="res-detail__subhead">
                  <Icon icon={FileText} size="sm" /> {wd.familyHeading}
                </span>
                <ul className="mini-list">{proofDocs.map(renderDoc)}</ul>
              </div>
            ) : null}
          </>
        )}
      </div>

      {/* Secure blob viewer — a portal Modal; opens above this documents list. */}
      <DocumentViewer
        open={viewerDoc !== null}
        document={viewerDoc ?? undefined}
        occupants={companions}
        onClose={() => setViewerDoc(null)}
      />
    </Modal>
  );
}
