"use client";

/**
 * GUESTS-CLOSURE central identity — the FOUR read-only guest sub-record modals
 * (Decision 11 / U-15). Each is built on the SHARED {@link Modal} (so it inherits
 * the focus trap / Escape / focus-restore / scroll-lock), fetches through the W5
 * paginated clients with REAL server pagination via the shared {@link Pagination},
 * and renders explicit loading / empty / error+retry states. Sensitive values are
 * shown EXACTLY as the backend sent them (a masked number stays masked — never
 * unmasked client-side) and identifiers render verbatim inside `<bdi dir="ltr">`
 * so an RTL layout can never reorder their digits.
 *
 * RBAC is cosmetic here — every endpoint re-checks server-side. The documents
 * modal additionally refuses to even call its endpoint without
 * `reservation_documents.view`, showing a clear no-access state instead.
 */
import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { Eye, FileText } from "lucide-react";

import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  Pagination,
} from "@/components/ui";
import {
  listGuestChangeLog,
  listGuestDocuments,
  listGuestReservations,
  listGuestStays,
  type GuestPageParams,
} from "@/lib/api/guests";
import { messageForError } from "@/lib/api/errors";
import type {
  GuestChangeLogRow,
  GuestDocumentRow,
  GuestReservationRow,
  GuestStayRow,
  PaginatedResponse,
} from "@/lib/api/types";
import {
  formatDateTime,
  reservationStatusLabel,
  reservationStatusTone,
  stayStatusLabel,
  stayStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { DocumentViewer } from "../reservations/DocumentViewer";
import { documentTypeLabel } from "../reservations/reservationShared";
import {
  IDENTIFIER_DIR,
  formatDateOnly,
  formatIdentifier,
  formatQuantity,
} from "./guestFormat";

/** Compact modal page size — sent explicitly so `totalPages` is deterministic
 * (the backend `DefaultPagination` honours `page_size` up to its own maximum). */
const PAGE_SIZE = 10;

export interface GuestRecordModalProps {
  open: boolean;
  guestId: number | null;
  guestName: string;
  onClose: () => void;
}

/** Cosmetic permission gate — every API re-checks server-side regardless. */
function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

type SubFetcher<T> = (
  id: number,
  params?: GuestPageParams,
) => Promise<PaginatedResponse<T>>;

interface SubListState<T> {
  page: number;
  setPage: (page: number) => void;
  rows: T[];
  count: number;
  totalPages: number;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Shared paginated fetch for a guest sub-resource. Resets to page 1 whenever the
 * modal (re)opens for a guest, guards against out-of-order/stale responses, and
 * never fetches while closed, without a guest, or while `enabled` is false (the
 * documents no-access case). `fetcher` MUST be a stable module-level reference.
 */
function useGuestSubList<T>(
  open: boolean,
  guestId: number | null,
  fetcher: SubFetcher<T>,
  enabled = true,
): SubListState<T> {
  const { t } = useI18n();
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<T[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // A fresh open (or a different guest) always starts on the first page.
  useEffect(() => {
    if (open) setPage(1);
  }, [open, guestId]);

  useEffect(() => {
    if (!open || guestId === null || !enabled) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetcher(guestId, { page, page_size: PAGE_SIZE })
      .then((data) => {
        if (cancelled) return;
        setRows(data.results);
        setCount(data.count);
      })
      .catch((err) => {
        if (!cancelled) setError(messageForError(err, t));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, guestId, enabled, page, reloadKey, fetcher, t]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  return {
    page,
    setPage,
    rows,
    count,
    totalPages,
    loading,
    error,
    reload: () => setReloadKey((k) => k + 1),
  };
}

/** The shared body frame: loading → error+retry → empty → children (+ pager). */
function SubListBody({
  loading,
  error,
  empty,
  emptyLabel,
  totalPages,
  page,
  onPageChange,
  onRetry,
  children,
}: {
  loading: boolean;
  error: string | null;
  empty: boolean;
  emptyLabel: string;
  totalPages: number;
  page: number;
  onPageChange: (page: number) => void;
  onRetry: () => void;
  children: ReactNode;
}) {
  const { t } = useI18n();
  if (loading) return <LoadingState label={t.common.loading} />;
  if (error) {
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={error}
        retryLabel={t.common.retry}
        onRetry={onRetry}
      />
    );
  }
  if (empty) return <EmptyState title={emptyLabel} />;
  return (
    <div className="stack">
      {children}
      <Pagination
        page={page}
        totalPages={totalPages}
        onPageChange={onPageChange}
        labels={{
          previous: t.pagination.previous,
          next: t.pagination.next,
          status: t.pagination.page
            .replace("{page}", String(page))
            .replace("{total}", String(totalPages)),
        }}
      />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// 1) Stays history                                                            //
// --------------------------------------------------------------------------- //

export function GuestStaysHistoryModal({
  open,
  guestId,
  guestName,
  onClose,
}: GuestRecordModalProps) {
  const { t, locale } = useI18n();
  const can = useCan();
  const s = t.guests.staysList;
  const list = useGuestSubList<GuestStayRow>(open, guestId, listGuestStays);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${s.title} · ${guestName}`}
      closeLabel={t.common.close}
      size="lg"
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t.common.close}
        </Button>
      }
    >
      <SubListBody
        loading={list.loading}
        error={list.error}
        empty={list.rows.length === 0}
        emptyLabel={s.empty}
        totalPages={list.totalPages}
        page={list.page}
        onPageChange={list.setPage}
        onRetry={list.reload}
      >
        <ul className="mini-list">
          {list.rows.map((row) => (
            <li key={row.stay_id} className="mini-list__row">
              <span className="stack-tight">
                <span>
                  <strong>{row.room_number}</strong>
                  <span className="muted"> · {row.room_type_name}</span>
                </span>
                <span className="muted small">
                  {formatDateOnly(row.check_in_date, locale)} →{" "}
                  {formatDateOnly(row.check_out_date, locale)} ·{" "}
                  {formatQuantity(row.nights, locale)} {s.nights}
                </span>
              </span>
              <span className="cluster" style={{ gap: "0.5rem" }}>
                <Badge tone={stayStatusTone(row.status)}>
                  {stayStatusLabel(row.status, t)}
                </Badge>
                {row.is_checked_out ? (
                  <Badge tone="neutral">{s.checkedOut}</Badge>
                ) : null}
                {row.reservation_number && can("reservations.view") ? (
                  <Link
                    className="inline-link"
                    href={`/hotel/reservations?action=find&q=${row.reservation_number}`}
                  >
                    <bdi dir={IDENTIFIER_DIR}>{row.reservation_number}</bdi>
                  </Link>
                ) : null}
                {row.folio && can("finance.view") ? (
                  <Link className="inline-link" href="/hotel/finance?tab=folios">
                    <bdi dir={IDENTIFIER_DIR}>{row.folio.folio_number}</bdi>
                  </Link>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      </SubListBody>
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// 2) Reservations history (grouped past / current / upcoming)                 //
// --------------------------------------------------------------------------- //

/** Local calendar day as `YYYY-MM-DD` (no UTC shift) — the reference used to
 * group each reservation. A DISPLAY grouping only, never a business decision. */
function todayLocalISO(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

type ReservationGroup = "upcoming" | "current" | "past";

function reservationGroup(
  row: GuestReservationRow,
  today: string,
): ReservationGroup {
  // A cancelled/expired booking is never "upcoming" — it belongs to the past.
  if (row.status === "cancelled" || row.status === "expired") return "past";
  if (row.check_in_date > today) return "upcoming";
  if (row.check_out_date < today) return "past";
  return "current";
}

export function GuestReservationsHistoryModal({
  open,
  guestId,
  guestName,
  onClose,
}: GuestRecordModalProps) {
  const { t, locale } = useI18n();
  const r = t.guests.reservationsList;
  const list = useGuestSubList<GuestReservationRow>(
    open,
    guestId,
    listGuestReservations,
  );

  const today = todayLocalISO();
  const groups: { key: ReservationGroup; label: string }[] = [
    { key: "upcoming", label: r.groupUpcoming },
    { key: "current", label: r.groupCurrent },
    { key: "past", label: r.groupPast },
  ];

  const renderRow = (row: GuestReservationRow) => (
    <li key={row.id} className="mini-list__row">
      <span className="stack-tight">
        <span>
          <strong>
            <bdi dir={IDENTIFIER_DIR}>
              {formatIdentifier(row.reservation_number)}
            </bdi>
          </strong>
        </span>
        <span className="muted small">
          {formatDateOnly(row.check_in_date, locale)} →{" "}
          {formatDateOnly(row.check_out_date, locale)}
        </span>
      </span>
      <span className="cluster" style={{ gap: "0.5rem" }}>
        <Badge tone={reservationStatusTone(row.status)}>
          {reservationStatusLabel(row.status, t)}
        </Badge>
        <Badge tone="neutral">{t.reservations.kind[row.booking_kind]}</Badge>
        <span className="muted small">{t.reservations.source[row.source]}</span>
      </span>
    </li>
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${r.title} · ${guestName}`}
      closeLabel={t.common.close}
      size="lg"
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t.common.close}
        </Button>
      }
    >
      <SubListBody
        loading={list.loading}
        error={list.error}
        empty={list.rows.length === 0}
        emptyLabel={r.empty}
        totalPages={list.totalPages}
        page={list.page}
        onPageChange={list.setPage}
        onRetry={list.reload}
      >
        {groups.map(({ key, label }) => {
          const rows = list.rows.filter(
            (row) => reservationGroup(row, today) === key,
          );
          if (rows.length === 0) return null;
          return (
            <section key={key} className="stack-tight">
              <h3 className="res-detail__subhead">{label}</h3>
              <ul className="mini-list">{rows.map(renderRow)}</ul>
            </section>
          );
        })}
      </SubListBody>
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// 3) Documents (behind reservation_documents.view)                            //
// --------------------------------------------------------------------------- //

export function GuestDocumentsModal({
  open,
  guestId,
  guestName,
  onClose,
}: GuestRecordModalProps) {
  const { t, locale } = useI18n();
  const can = useCan();
  const d = t.guests.documents;
  const canViewDocs = can("reservation_documents.view");
  const list = useGuestSubList<GuestDocumentRow>(
    open,
    guestId,
    listGuestDocuments,
    canViewDocs,
  );
  // The secure blob viewer reuses the reservation document viewer — a
  // GuestDocumentRow already carries every field it needs (id/doc_type/faces).
  const [viewerDoc, setViewerDoc] = useState<GuestDocumentRow | null>(null);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${d.title} · ${guestName}`}
      closeLabel={t.common.close}
      size="lg"
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t.common.close}
        </Button>
      }
    >
      {!canViewDocs ? (
        <EmptyState title={d.permissionHint} icon={FileText} />
      ) : (
        <SubListBody
          loading={list.loading}
          error={list.error}
          empty={list.rows.length === 0}
          emptyLabel={d.empty}
          totalPages={list.totalPages}
          page={list.page}
          onPageChange={list.setPage}
          onRetry={list.reload}
        >
          <ul className="mini-list">
            {list.rows.map((row) => {
              const canOpen = row.has_front || row.has_back;
              return (
                <li key={row.id} className="mini-list__row">
                  <span className="stack-tight">
                    <span>
                      <strong>{documentTypeLabel(row.doc_type, t)}</strong>{" "}
                      <bdi dir={IDENTIFIER_DIR}>
                        {formatIdentifier(row.number)}
                      </bdi>
                    </span>
                    <span className="muted small">
                      {d.expiry}: {formatDateOnly(row.expiry_date, locale)}
                    </span>
                  </span>
                  <span className="cluster" style={{ gap: "0.5rem" }}>
                    {row.has_front ? (
                      <Badge tone="neutral">{d.front}</Badge>
                    ) : null}
                    {row.has_back ? (
                      <Badge tone="neutral">{d.back}</Badge>
                    ) : null}
                    {canOpen ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={Eye}
                        onClick={() => setViewerDoc(row)}
                      >
                        {d.view}
                      </Button>
                    ) : null}
                  </span>
                </li>
              );
            })}
          </ul>
        </SubListBody>
      )}

      {/* Secure blob viewer (authenticated bytes, never a raw URL). A
          GuestDocumentRow is a structural superset of ReservationDocument (id +
          faces + doc_type + occupant), so it is passed straight through. */}
      <DocumentViewer
        open={viewerDoc !== null}
        document={viewerDoc ?? undefined}
        onClose={() => setViewerDoc(null)}
      />
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// 4) Change log (newest first; block reason gated server-side)                //
// --------------------------------------------------------------------------- //

/** Map a backend severity string to a badge tone + label; unknown severities
 * render no badge (never a fabricated one). */
function severityMeta(
  severity: string,
  t: ReturnType<typeof useI18n>["t"],
): { tone: "info" | "warning" | "danger"; label: string } | null {
  const c = t.guests.changeLog;
  switch (severity) {
    case "info":
      return { tone: "info", label: c.severityInfo };
    case "warning":
      return { tone: "warning", label: c.severityWarning };
    case "critical":
      return { tone: "danger", label: c.severityCritical };
    default:
      return null;
  }
}

export function GuestChangeLogModal({
  open,
  guestId,
  guestName,
  onClose,
}: GuestRecordModalProps) {
  const { t, locale } = useI18n();
  const c = t.guests.changeLog;
  const list = useGuestSubList<GuestChangeLogRow>(
    open,
    guestId,
    listGuestChangeLog,
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${c.title} · ${guestName}`}
      closeLabel={t.common.close}
      size="lg"
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t.common.close}
        </Button>
      }
    >
      <SubListBody
        loading={list.loading}
        error={list.error}
        empty={list.rows.length === 0}
        emptyLabel={c.empty}
        totalPages={list.totalPages}
        page={list.page}
        onPageChange={list.setPage}
        onRetry={list.reload}
      >
        <ul className="mini-list">
          {list.rows.map((row) => {
            const sev = severityMeta(row.severity, t);
            return (
              <li key={row.id} className="mini-list__row">
                <span className="stack-tight">
                  <span>
                    <strong>{row.title}</strong>
                  </span>
                  {row.message ? (
                    <span className="muted small">{row.message}</span>
                  ) : null}
                  <span className="muted small">
                    {c.actor}: {row.actor || "—"} · {c.occurredAt}:{" "}
                    {formatDateTime(row.occurred_at, locale)}
                  </span>
                </span>
                <span className="cluster" style={{ gap: "0.5rem" }}>
                  {sev ? <Badge tone={sev.tone}>{sev.label}</Badge> : null}
                </span>
              </li>
            );
          })}
        </ul>
      </SubListBody>
    </Modal>
  );
}
