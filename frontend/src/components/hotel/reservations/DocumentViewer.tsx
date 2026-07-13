"use client";

import { useEffect, useRef, useState } from "react";

import { Button, ErrorState, LoadingState, Modal } from "@/components/ui";
import { getReservationDocumentBlobUrl } from "@/lib/api/reservations";
import type { ReservationDocument } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { documentTypeLabel } from "./reservationShared";

type Side = "front" | "back";
type Kind = "image" | "pdf";

/**
 * Secure in-app viewer for a reservation guest document (RESERVATIONS-FORM-REWORK,
 * Wave 3). It NEVER renders a public/raw URL: the bytes are fetched through the
 * authenticated BFF via `getReservationDocumentBlobUrl(docId, side)`, wrapped in
 * an in-memory object URL and rendered as an `<img>` (images) or an `<iframe>`
 * (PDFs). The object URL is revoked on unmount and on every side/document change
 * so no blob leaks. The whole viewer is gated behind `reservation_documents.view`
 * (the backend re-checks server-side regardless).
 */
export function DocumentViewer({
  open,
  document: doc,
  onClose,
}: {
  open: boolean;
  document?: ReservationDocument;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const v = t.reservations.viewer;
  const access = useHotelAccess();
  const canView =
    access === null ||
    (!access.loading && access.can("reservation_documents.view"));

  const docId = doc?.id ?? null;
  const hasFront = doc?.has_front ?? false;
  const hasBack = doc?.has_back ?? false;

  const [side, setSide] = useState<Side>("front");
  const [url, setUrl] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>("image");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  // The single object URL currently held; tracked in a ref so cleanup never
  // races the async fetch or a stale render closure.
  const urlRef = useRef<string | null>(null);
  const revoke = () => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  };

  // A new document resets the visible side to whichever face actually exists.
  useEffect(() => {
    setSide(hasFront || !hasBack ? "front" : "back");
  }, [docId, hasFront, hasBack]);

  // Fetch + wrap the selected side's bytes; revoke the previous URL first and
  // whenever the viewer closes or the target changes.
  useEffect(() => {
    revoke();
    setUrl(null);
    setError(false);

    if (!open || docId === null || !canView) {
      setLoading(false);
      return;
    }
    const sideExists = side === "front" ? hasFront : hasBack;
    if (!sideExists) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const objectUrl = await getReservationDocumentBlobUrl(docId, side);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        // Re-read the in-memory blob to learn its MIME type (no network hit);
        // decides `<img>` vs `<iframe>` without exposing a raw URL anywhere.
        let detected: Kind = "image";
        try {
          const blob = await fetch(objectUrl).then((res) => res.blob());
          if (blob.type.includes("pdf")) detected = "pdf";
        } catch {
          detected = "image";
        }
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        urlRef.current = objectUrl;
        setKind(detected);
        setUrl(objectUrl);
        setLoading(false);
      } catch {
        if (!cancelled) {
          setError(true);
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, docId, side, canView, hasFront, hasBack]);

  // Final safety net: revoke any held URL when the component unmounts.
  useEffect(() => revoke, []);

  if (!canView || !doc) return null;

  const title = `${v.title} · ${documentTypeLabel(doc.doc_type, t)}`;
  const noSide = side === "front" ? !hasFront : !hasBack;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      closeLabel={t.common.close}
      size="lg"
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t.common.close}
        </Button>
      }
    >
      <div className="doc-viewer">
        {hasFront && hasBack ? (
          <div className="cluster" role="group" aria-label={v.title}>
            <Button
              variant={side === "front" ? "primary" : "secondary"}
              size="sm"
              aria-pressed={side === "front"}
              onClick={() => setSide("front")}
            >
              {v.front}
            </Button>
            <Button
              variant={side === "back" ? "primary" : "secondary"}
              size="sm"
              aria-pressed={side === "back"}
              onClick={() => setSide("back")}
            >
              {v.back}
            </Button>
          </div>
        ) : null}

        <div className="doc-viewer__stage">
          {loading ? (
            <LoadingState label={t.common.loading} />
          ) : error ? (
            <ErrorState title={v.error} />
          ) : noSide || !url ? (
            <p className="muted">{v.empty}</p>
          ) : kind === "pdf" ? (
            <iframe className="doc-viewer__frame" src={url} title={v.pdfTitle} />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              className="doc-viewer__image"
              src={url}
              alt={v.imageAlt}
              onError={() => setKind("pdf")}
            />
          )}
        </div>
      </div>
    </Modal>
  );
}
