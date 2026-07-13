"use client";

import {
  ChevronLeft,
  ChevronRight,
  Maximize2,
  RotateCw,
  User,
  ZoomIn,
  ZoomOut,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  Button,
  ErrorState,
  Icon,
  IconButton,
  LoadingState,
  Modal,
} from "@/components/ui";
import { getReservationDocumentBlobUrl } from "@/lib/api/reservations";
import type { ReservationDocument, ReservationOccupant } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { documentTypeLabel, occupantDisplayName } from "./reservationShared";

type Side = "front" | "back";
type Kind = "image" | "pdf";

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.25;

/** Snap a zoom factor into the allowed range and round to 2 dp (no float drift
 * so equality checks like `zoom === 1` stay exact across steps). */
function clampZoom(value: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(value * 100) / 100));
}

/** One toolbar control: an `IconButton` (aria-label + title from `label`,
 * native `disabled` for keyboard/AT correctness) plus a dim style while
 * disabled — kept inline so the viewer needs no new global CSS. */
function ViewerControl({
  label,
  icon,
  disabled,
  onClick,
}: {
  label: string;
  icon: LucideIcon;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <IconButton
      label={label}
      icon={icon}
      size="sm"
      disabled={disabled}
      onClick={onClick}
      style={disabled ? { opacity: 0.4, cursor: "not-allowed" } : undefined}
    />
  );
}

/**
 * Secure in-app viewer for a reservation guest document (RESERVATIONS-FORM-REWORK,
 * Wave 3; controls extended in RESERVATIONS-FORM-UX-CORRECTION §18). It NEVER
 * renders a public/raw URL: the bytes are fetched through the authenticated BFF
 * via `getReservationDocumentBlobUrl(docId, side)`, wrapped in an in-memory
 * object URL and rendered as an `<img>` (images) or an `<iframe>` (PDFs). The
 * object URL is revoked on unmount and on every side/document change so no blob
 * leaks. The whole viewer is gated behind `reservation_documents.view` (the
 * backend re-checks server-side regardless).
 *
 * Viewer controls (§18) act purely on the rendered element via CSS transforms —
 * they never re-fetch or expose the bytes: zoom in/out + reset (`scale`), rotate
 * for images (`rotate`), and prev/next paging across the document's available
 * front/back sides (true multi-page PDFs page inside the browser's native PDF
 * viewer). Zoom + rotation reset whenever the side or document changes. The
 * header names the document type and its owner (primary guest, or the named
 * companion when the occupant snapshot is supplied).
 */
export function DocumentViewer({
  open,
  document: doc,
  occupants,
  onClose,
}: {
  open: boolean;
  document?: ReservationDocument;
  /**
   * Optional occupant snapshot so a companion document can name its exact owner
   * (resolved via `occupantDisplayName`). Purely additive: callers that don't
   * pass it still compile — a companion document then shows the generic
   * "companion" label, and the primary-guest case never needs it.
   */
  occupants?: ReservationOccupant[];
  onClose: () => void;
}) {
  const { t, dir } = useI18n();
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
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);

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

  // Zoom + rotation are per-view, never carried across a side/document switch.
  useEffect(() => {
    setZoom(1);
    setRotation(0);
  }, [docId, side]);

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

  // Available faces as an ordered pager (front before back); front/back are the
  // document's "pages" here — a PDF's own pages live inside the native viewer.
  const sides: Side[] = [];
  if (hasFront) sides.push("front");
  if (hasBack) sides.push("back");
  const sideIndex = sides.indexOf(side);
  const sideLabel = side === "front" ? v.front : v.back;

  const noSide = side === "front" ? !hasFront : !hasBack;
  const hasMedia = !loading && !error && !noSide && url !== null;

  // Who the document belongs to: the primary guest (no occupant) or, when the
  // occupant snapshot is available, the named companion; otherwise a generic
  // companion label so the header is never blank.
  const resolveOwner = (): string => {
    if (doc.occupant === null) return v.ownerPrimary;
    const occ = occupants?.find((o) => o.id === doc.occupant);
    return occ ? occupantDisplayName(occ, t) : v.ownerCompanion;
  };
  const ownerName = resolveOwner();

  const zoomPct = Math.round(zoom * 100);
  // Rotation is image-only; a PDF's native viewer owns its own rotate, and
  // rotating the iframe box would distort it — so we only scale the frame.
  const mediaTransform =
    kind === "pdf"
      ? `scale(${zoom})`
      : `scale(${zoom}) rotate(${rotation}deg)`;
  const mediaStyle = {
    transform: mediaTransform,
    transformOrigin: "center center",
  } as const;

  // Logical prev/next: the chevron points the reading-direction-correct way.
  const prevIcon = dir === "rtl" ? ChevronRight : ChevronLeft;
  const nextIcon = dir === "rtl" ? ChevronLeft : ChevronRight;
  const goToOffset = (offset: number) => {
    const next = sides[sideIndex + offset];
    if (next) setSide(next);
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={v.title}
      closeLabel={t.common.close}
      size="lg"
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t.common.close}
        </Button>
      }
    >
      <div className="doc-viewer">
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-1)",
          }}
        >
          <strong>{documentTypeLabel(doc.doc_type, t)}</strong>
          <span
            className="muted"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "var(--space-2)",
            }}
          >
            <Icon icon={User} size="sm" />
            <span className="sr-only">{v.ownerLabel}: </span>
            {ownerName}
          </span>
        </div>

        <div
          className="cluster"
          style={{ justifyContent: "space-between" }}
        >
          <div className="cluster" role="group" aria-label={v.controls}>
            <ViewerControl
              label={v.zoomOut}
              icon={ZoomOut}
              disabled={!hasMedia || zoom <= ZOOM_MIN}
              onClick={() => setZoom((z) => clampZoom(z - ZOOM_STEP))}
            />
            <span
              className="muted"
              aria-live="polite"
              style={{
                minWidth: "3rem",
                textAlign: "center",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              <span className="sr-only">{v.zoomLevel}: </span>
              {zoomPct}%
            </span>
            <ViewerControl
              label={v.zoomIn}
              icon={ZoomIn}
              disabled={!hasMedia || zoom >= ZOOM_MAX}
              onClick={() => setZoom((z) => clampZoom(z + ZOOM_STEP))}
            />
            <ViewerControl
              label={v.zoomReset}
              icon={Maximize2}
              disabled={!hasMedia || (zoom === 1 && rotation === 0)}
              onClick={() => {
                setZoom(1);
                setRotation(0);
              }}
            />
            <ViewerControl
              label={v.rotate}
              icon={RotateCw}
              disabled={!hasMedia || kind === "pdf"}
              onClick={() => setRotation((r) => (r + 90) % 360)}
            />
          </div>

          {sides.length > 1 ? (
            <div className="cluster" role="group" aria-label={v.sideNav}>
              <ViewerControl
                label={v.prev}
                icon={prevIcon}
                disabled={sideIndex <= 0}
                onClick={() => goToOffset(-1)}
              />
              <span aria-live="polite">
                {sideLabel}{" "}
                <span className="muted">
                  ({sideIndex + 1} / {sides.length})
                </span>
              </span>
              <ViewerControl
                label={v.next}
                icon={nextIcon}
                disabled={sideIndex >= sides.length - 1}
                onClick={() => goToOffset(1)}
              />
            </div>
          ) : null}
        </div>

        <div className="doc-viewer__stage">
          {loading ? (
            <LoadingState label={t.common.loading} />
          ) : error ? (
            <ErrorState title={v.error} />
          ) : noSide || !url ? (
            <p className="muted">{v.empty}</p>
          ) : kind === "pdf" ? (
            <iframe
              className="doc-viewer__frame"
              src={url}
              title={v.pdfTitle}
              style={mediaStyle}
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              className="doc-viewer__image"
              src={url}
              alt={v.imageAlt}
              onError={() => setKind("pdf")}
              style={mediaStyle}
            />
          )}
        </div>
      </div>
    </Modal>
  );
}
