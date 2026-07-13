"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { useQuickAction } from "@/lib/useQuickAction";
import {
  CalendarCheck,
  Plus,
  Printer,
  SlidersHorizontal,
  X,
} from "lucide-react";

import {
  Alert,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  Modal,
  Pagination,
  PrintDocumentLayout,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  cancelReservation,
  confirmReservation,
  getReservationFinancialSummary,
  getReservationOverview,
  listReservations,
} from "@/lib/api/reservations";
import { listRoomTypes } from "@/lib/api/rooms";
import { getSettings } from "@/lib/api/hotel";
import { messageForError } from "@/lib/api/errors";
import type {
  Reservation,
  ReservationFinancialSummary,
  RoomType,
} from "@/lib/api/types";
import { formatDate, formatMoney, reservationStatusLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useHotelProfile } from "@/lib/session/HotelProfileContext";

import { ReservationCard } from "./ReservationCard";
import { ReservationDetailsModal } from "./ReservationDetailsModal";
import {
  isForeignPayment,
  occupantDisplayName,
  relationshipLabel,
} from "./reservationShared";
import {
  ReservationSummaryCards,
  type ReservationCounts,
  type SummaryCardKey,
} from "./ReservationSummaryCards";

const PAGE_SIZE = 25;
const STATUSES = ["held", "confirmed", "cancelled", "expired"] as const;
const SOURCES = ["direct", "phone", "walk_in", "public_website", "other"] as const;

/** The reservations LIST (reservations rework): cards-first, driven by the
 * hotel-scoped overview counts and a supported-only filter set. Props: a create
 * signal from the page's "New reservation" button and a change callback so the
 * summary counters stay honest. */
export function ReservationsTab({
  createSignal = 0,
  onChanged,
}: {
  createSignal?: number;
  onChanged?: () => void;
}) {
  const { t } = useI18n();
  const { notify } = useToast();
  const access = useHotelAccess();
  const router = useRouter();
  const searchParams = useSearchParams();
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));

  const [types, setTypes] = useState<RoomType[]>([]);
  const [typesLoaded, setTypesLoaded] = useState(false);
  // Hotel-wide expected checkout time — fetched ONCE for the whole list (not per
  // card) so each card's stay block can show the departure time (§35).
  const [checkoutTime, setCheckoutTime] = useState<string | null>(null);
  const [rows, setRows] = useState<Reservation[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [overview, setOverview] = useState<{
    counts: ReservationCounts;
    businessDate: string | null;
  }>({ counts: {}, businessDate: null });

  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [type, setType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [showMoreFilters, setShowMoreFilters] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [details, setDetails] = useState<Reservation | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Reservation | null>(null);
  const [printTarget, setPrintTarget] = useState<Reservation | null>(null);

  // The page's "New reservation" button pulses this prop — it now navigates to
  // the full-screen create PAGE (no modal). Consume real increments only (the
  // initial value must not auto-navigate on mount).
  const lastSignal = useRef(createSignal);
  useEffect(() => {
    if (createSignal !== lastSignal.current) {
      lastSignal.current = createSignal;
      router.push("/hotel/reservations/new");
    }
  }, [createSignal, router]);

  function openCreate() {
    router.push("/hotel/reservations/new");
  }

  // Deep-links: ?action=new (topbar quick action / a room pinned from the rooms
  // board) now opens the full-screen create PAGE, forwarding the pinned room.
  // `replace` so the ?action= URL never lingers in history (back/refresh won't
  // re-trigger it). ?action=find&q= focuses the list (below).
  const actionParam = searchParams.get("action");
  const roomParam = searchParams.get("room");
  const roomTypeParam = searchParams.get("room_type");
  useEffect(() => {
    if (actionParam !== "new") return;
    const params = new URLSearchParams();
    if (roomParam) params.set("room", roomParam);
    if (roomTypeParam) params.set("room_type", roomTypeParam);
    const qs = params.toString();
    router.replace(`/hotel/reservations/new${qs ? `?${qs}` : ""}`);
  }, [actionParam, roomParam, roomTypeParam, router]);
  useQuickAction("find", (params) => {
    const q = params.get("q") ?? "";
    setSearch(q);
    setQuery(q);
    setPage(1);
  });

  // Debounced free-text search (reservation no / guest / phone / room number).
  useEffect(() => {
    const id = setTimeout(() => {
      setQuery(search);
      setPage(1);
    }, 350);
    return () => clearTimeout(id);
  }, [search]);

  useEffect(() => {
    listRoomTypes()
      .then((r) => setTypes(r.results))
      .catch(() => setTypes([]))
      .finally(() => setTypesLoaded(true));
  }, []);

  useEffect(() => {
    getSettings()
      .then((s) => setCheckoutTime(s.check_out_time))
      .catch(() => setCheckoutTime(null));
  }, []);

  const loadOverview = useCallback(() => {
    getReservationOverview()
      .then((o) =>
        setOverview({
          counts: {
            total: o.total,
            confirmed: o.confirmed,
            held: o.held,
            cancelled: o.cancelled,
            website: o.website,
          },
          businessDate: o.business_date,
        }),
      )
      .catch(() => {
        /* Counts stay as "…"; the list itself still renders. */
      });
  }, []);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listReservations({
        page,
        status: status || undefined,
        source: source || undefined,
        room_type: type ? Number(type) : undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        search: query || undefined,
      });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, status, source, type, dateFrom, dateTo, query, t]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const hasFilters =
    status !== "" ||
    source !== "" ||
    type !== "" ||
    dateFrom !== "" ||
    dateTo !== "" ||
    query !== "";

  // Which summary card is active. Website is a SOURCE filter (public_website);
  // the others are STATUS filters. Total highlights only when NO status AND NO
  // source is applied; a non-card status (expired) or non-website source
  // highlights nothing.
  const activeCard: SummaryCardKey | null =
    source === "public_website"
      ? "website"
      : source !== ""
        ? null
        : status === "" || status === "confirmed" || status === "held" || status === "cancelled"
          ? (status as SummaryCardKey)
          : null;

  function onCard(next: SummaryCardKey) {
    setPage(1);
    if (next === "website") {
      // Source filter: show every status of the public_website source so the
      // list matches the card count. Toggling it off clears the source.
      setStatus("");
      setSource((prev) => (prev === "public_website" ? "" : "public_website"));
      return;
    }
    // A status card (incl. Total "") clears the source dimension and toggles
    // the status — Total therefore clears both status AND source.
    setSource("");
    setStatus((prev) => (prev === next ? "" : next));
  }

  function applySearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setQuery(search);
  }

  function clearFilters() {
    setStatus("");
    setSource("");
    setType("");
    setDateFrom("");
    setDateTo("");
    setSearch("");
    setQuery("");
    setPage(1);
  }

  const refresh = useCallback(() => {
    load();
    loadOverview();
    onChanged?.();
  }, [load, loadOverview, onChanged]);

  async function confirm(r: Reservation) {
    try {
      await confirmReservation(r.id);
      notify(t.reservations.saved);
      refresh();
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  const statusOptions = STATUSES.map((s) => ({
    value: s,
    label: reservationStatusLabel(s, t),
  }));
  const sourceOptions = SOURCES.map((s) => ({
    value: s,
    label: t.reservations.source[s],
  }));
  const typeOptions = types.map((ty) => ({ value: String(ty.id), label: ty.name }));

  const activeTypes = types.filter((ty) => ty.is_active);
  const noBookable = typesLoaded && activeTypes.length === 0;

  // Section-level permission guard (the route also enforces reservations.view).
  if (access && !access.loading && !access.can("reservations.view")) {
    return (
      <EmptyState
        title={t.reservations.views.noPermissionTitle}
        hint={t.reservations.views.noPermissionHint}
        icon={CalendarCheck}
      />
    );
  }

  return (
    <div className="stack">
      {noBookable ? (
        <Alert tone="warning">
          {t.reservations.views.noBookableRoomsHint}{" "}
          <Link href="/hotel/rooms" className="btn btn--secondary btn--sm">
            {t.reservations.views.goToRooms}
          </Link>
        </Alert>
      ) : null}

      <ReservationSummaryCards
        counts={overview.counts}
        active={activeCard}
        onSelect={onCard}
      />

      <Card>
        <form onSubmit={applySearch} aria-label={t.common.filter}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="res-search">
              <Input
                id="res-search"
                value={search}
                placeholder={t.reservations.views.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
              />
            </FormField>
            <FormField label={t.reservations.list.filterStatus} htmlFor="res-status">
              <Select
                id="res-status"
                value={status}
                placeholder={t.common.all}
                options={statusOptions}
                onChange={(e) => {
                  setPage(1);
                  setStatus(e.target.value);
                }}
              />
            </FormField>
            <div className="filter-bar__actions cluster">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                icon={SlidersHorizontal}
                aria-expanded={showMoreFilters}
                onClick={() => setShowMoreFilters((v) => !v)}
              >
                {showMoreFilters ? t.reservations.views.fewerFilters : t.reservations.views.moreFilters}
              </Button>
              {hasFilters ? (
                <Button variant="ghost" size="sm" icon={X} onClick={clearFilters}>
                  {t.rooms.board.clearFilters}
                </Button>
              ) : null}
            </div>
          </FilterBar>

          {showMoreFilters ? (
            <FilterBar>
              <FormField label={t.reservations.views.sourceLabel} htmlFor="res-source">
                <Select
                  id="res-source"
                  value={source}
                  placeholder={t.common.all}
                  options={sourceOptions}
                  onChange={(e) => {
                    setPage(1);
                    setSource(e.target.value);
                  }}
                />
              </FormField>
              <FormField label={t.reservations.list.filterType} htmlFor="res-type">
                <Select
                  id="res-type"
                  value={type}
                  placeholder={t.common.all}
                  options={typeOptions}
                  onChange={(e) => {
                    setPage(1);
                    setType(e.target.value);
                  }}
                />
              </FormField>
              <FormField
                label={t.reservations.views.stayOverlapFrom}
                htmlFor="res-from"
                hint={t.reservations.views.stayOverlapHint}
              >
                <Input
                  id="res-from"
                  type="date"
                  value={dateFrom}
                  onChange={(e) => {
                    setPage(1);
                    setDateFrom(e.target.value);
                  }}
                />
              </FormField>
              <FormField label={t.reservations.views.stayOverlapTo} htmlFor="res-to">
                <Input
                  id="res-to"
                  type="date"
                  value={dateTo}
                  onChange={(e) => {
                    setPage(1);
                    setDateTo(e.target.value);
                  }}
                />
              </FormField>
            </FilterBar>
          ) : null}
        </form>
      </Card>

      {!loading && !error ? (
        <div className="res-list__meta">
          <span className="muted">
            {t.reservations.views.resultCount.replace("{count}", String(count))}
          </span>
          <span className="res-list__order muted">{t.reservations.views.newestFirst}</span>
        </div>
      ) : null}

      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? (
        <ErrorState
          title={t.states.errorTitle}
          message={error}
          retryLabel={t.common.retry}
          onRetry={load}
        />
      ) : null}
      {!loading && !error ? (
        rows.length === 0 ? (
          hasFilters ? (
            <EmptyState
              title={t.reservations.views.emptyFiltered}
              icon={CalendarCheck}
              action={
                <Button variant="secondary" icon={X} onClick={clearFilters}>
                  {t.rooms.board.clearFilters}
                </Button>
              }
            />
          ) : (
            <EmptyState
              title={t.reservations.views.noReservations}
              hint={t.reservations.list.emptyHint}
              icon={CalendarCheck}
              action={
                can("reservations.create") ? (
                  <Button icon={Plus} onClick={openCreate}>
                    {t.reservations.views.newReservation}
                  </Button>
                ) : undefined
              }
            />
          )
        ) : (
          <>
            <div
              className="reservation-list"
              role="list"
              aria-label={t.reservations.list.title}
            >
              {rows.map((r) => (
                <div role="listitem" key={r.id}>
                  <ReservationCard
                    reservation={r}
                    businessDate={overview.businessDate}
                    checkoutTime={checkoutTime}
                    onView={setDetails}
                    onPrint={setPrintTarget}
                    onConfirm={confirm}
                    onEdit={() => router.push(`/hotel/reservations/${r.id}/edit`)}
                    onCancel={setCancelTarget}
                  />
                </div>
              ))}
            </div>
            <Pagination
              page={page}
              totalPages={totalPages}
              onPageChange={setPage}
              labels={{
                previous: t.pagination.previous,
                next: t.pagination.next,
                status: t.pagination.page
                  .replace("{page}", String(page))
                  .replace("{total}", String(totalPages)),
              }}
            />
          </>
        )
      ) : null}

      {/* Create and edit both live on full-screen pages
          (/hotel/reservations/new and /hotel/reservations/[id]/edit). */}
      <ReservationDetailsModal
        open={details !== null}
        reservation={details ?? undefined}
        onClose={() => setDetails(null)}
        onEdit={(r) => {
          setDetails(null);
          router.push(`/hotel/reservations/${r.id}/edit`);
        }}
        onConfirm={(r) => {
          setDetails(null);
          confirm(r);
        }}
        onCancel={(r) => {
          setDetails(null);
          setCancelTarget(r);
        }}
      />
      <CancelModal
        open={cancelTarget !== null}
        reservation={cancelTarget ?? undefined}
        onClose={() => setCancelTarget(null)}
        onDone={() => {
          setCancelTarget(null);
          notify(t.reservations.saved);
          refresh();
        }}
      />
      <ReservationPrintModal
        open={printTarget !== null}
        reservation={printTarget ?? undefined}
        onClose={() => setPrintTarget(null)}
      />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Cancel modal                                                                //
// --------------------------------------------------------------------------- //

function CancelModal({
  open,
  reservation,
  onClose,
  onDone,
}: {
  open: boolean;
  reservation?: Reservation;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setReason("");
      setError(null);
    }
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reservation) return;
    if (!reason.trim()) return setError(t.reservations.errors.reasonRequired);
    setBusy(true);
    try {
      await cancelReservation(reservation.id, reason.trim());
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.reservations.cancelDialog.title}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="cancel-form" type="submit" variant="danger" loading={busy}>
            {t.reservations.cancelDialog.confirm}
          </Button>
        </>
      }
    >
      <form id="cancel-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="info">{t.reservations.cancelDialog.body}</Alert>
        <FormField label={t.reservations.cancelDialog.reason} htmlFor="cancel-reason">
          <Textarea
            id="cancel-reason"
            value={reason}
            required
            placeholder={t.reservations.cancelDialog.reasonPlaceholder}
            onChange={(e) => setReason(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// Print modal — a localized, RTL-aware reservation confirmation               //
// --------------------------------------------------------------------------- //

/** A print-friendly reservation confirmation. Reuses the shared
 * PrintDocumentLayout primitive inside a `.print-doc` node — the same
 * `@media print` rule the finance vouchers rely on hides everything else, so
 * window.print() emits ONLY this document. It inherits the page direction, so
 * it is RTL-aware, and every label is localized. It carries the booking facts
 * (number, status, source, kind, guest, rooms, floor, type, dates, arrival,
 * nights, guests, notes) plus — WHEN PRESENT and the caller may see money
 * (finance.view) — a DERIVED financial block (§40): total, paid, remaining and
 * the recorded payments. Money renders from backend Decimal strings via
 * formatMoney (never Float); with no priced summary the block is omitted
 * honestly. Document images and identity-only fields are never printed. */
function ReservationPrintModal({
  open,
  reservation,
  onClose,
}: {
  open: boolean;
  reservation?: Reservation;
  onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const profile = useHotelProfile();
  const access = useHotelAccess();
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));

  // §40 — DERIVED financial summary for the slip, fetched only when the caller
  // may see money (finance.view). The backend re-derives and masks it for
  // callers without the grant; a failed/absent fetch simply omits the block.
  const canMoney = can("finance.view");
  const reservationId = reservation?.id ?? null;
  const [summary, setSummary] = useState<ReservationFinancialSummary | null>(
    null,
  );

  useEffect(() => {
    if (!open || reservationId === null || !canMoney) {
      setSummary(null);
      return;
    }
    let active = true;
    getReservationFinancialSummary(reservationId)
      .then((s) => {
        if (active) setSummary(s);
      })
      .catch(() => {
        if (active) setSummary(null);
      });
    return () => {
      active = false;
    };
  }, [open, reservationId, canMoney]);

  if (!reservation) return null;
  const r = reservation;
  const d = t.reservations.details;
  const p = t.reservations.print;
  const b = t.reservations.wizard.booking;
  const card = t.reservations.card;
  const g = t.reservations.wizard.guest;

  // Money is shown only when the summary is priced AND viewable; otherwise the
  // whole financial block is left off the slip (honest-when-empty).
  const money =
    summary !== null && summary.can_view_money && summary.is_priced !== false
      ? summary
      : null;
  const companions = r.occupants ?? [];
  const docLabel = (v: string) =>
    (t.guests.documentTypes as Record<string, string>)[v] ?? v;

  const roomLabels = r.lines.map((l) =>
    l.room_number ? `${d.room} ${l.room_number}` : `${l.room_type_name} ×${l.quantity}`,
  );
  const floorNames = Array.from(
    new Set(r.lines.map((l) => l.floor_name).filter((f): f is string => Boolean(f))),
  );
  const typeNames = Array.from(new Set(r.lines.map((l) => l.room_type_name)));
  const note = [r.notes, r.special_requests].filter(Boolean).join(" · ");

  const meta = [
    { label: t.common.status, value: reservationStatusLabel(r.status, t) },
    { label: t.reservations.views.sourceLabel, value: t.reservations.source[r.source] ?? r.source },
    { label: t.reservations.form.bookingKind, value: t.reservations.kind[r.booking_kind] },
    { label: d.guest, value: r.primary_guest_name || "—" },
    ...(r.primary_guest_father_name
      ? [{ label: g.fatherName, value: r.primary_guest_father_name }]
      : []),
    ...(r.primary_guest_mother_name
      ? [{ label: g.motherName, value: r.primary_guest_mother_name }]
      : []),
    ...(r.primary_guest_national_id
      ? [{ label: g.nationalId, value: r.primary_guest_national_id }]
      : []),
    ...(r.primary_guest_date_of_birth
      ? [{ label: g.dateOfBirth, value: formatDate(r.primary_guest_date_of_birth, locale) }]
      : []),
    ...(r.primary_guest_nationality
      ? [{ label: t.reservations.form.nationality, value: r.primary_guest_nationality }]
      : []),
    ...(r.primary_guest_phone ? [{ label: d.phone, value: r.primary_guest_phone }] : []),
    ...(r.primary_guest_email ? [{ label: d.email, value: r.primary_guest_email }] : []),
    ...(r.primary_guest_document_type
      ? [{ label: t.reservations.form.documentType, value: docLabel(r.primary_guest_document_type) }]
      : []),
    ...(r.primary_guest_document_number
      ? [{ label: t.reservations.form.documentNumber, value: r.primary_guest_document_number }]
      : []),
    ...(roomLabels.length ? [{ label: d.rooms, value: roomLabels.join(" · ") }] : []),
    ...(floorNames.length ? [{ label: t.reservations.card.floor, value: floorNames.join(" · ") }] : []),
    ...(typeNames.length ? [{ label: t.reservations.form.roomType, value: typeNames.join(" · ") }] : []),
    {
      label: d.dates,
      value: `${formatDate(r.check_in_date, locale)} → ${formatDate(r.check_out_date, locale)}`,
    },
    ...(r.expected_arrival_time
      ? [{ label: t.reservations.form.arrivalTime, value: r.expected_arrival_time }]
      : []),
    { label: d.nights, value: String(r.nights) },
    { label: d.guests, value: String(r.total_guests) },
    ...(r.expected_payment_method
      ? [
          {
            label: t.reservations.form.expectedPayment,
            value: t.reservations.expectedPayment[r.expected_payment_method],
          },
        ]
      : []),
    // §40 — DERIVED money, only when a priced+viewable summary is present.
    ...(money
      ? [
          ...(money.nightly_rate
            ? [
                {
                  label: card.nightly,
                  value: formatMoney(money.nightly_rate, money.currency, locale),
                },
              ]
            : []),
          ...(money.reservation_total !== null
            ? [
                {
                  label: card.total,
                  value: formatMoney(
                    money.reservation_total,
                    money.currency,
                    locale,
                  ),
                },
              ]
            : []),
          ...(money.paid !== null
            ? [
                {
                  label: card.paid,
                  value: formatMoney(money.paid, money.currency, locale),
                },
              ]
            : []),
          ...(money.remaining !== null
            ? [
                {
                  label: card.remaining,
                  value: formatMoney(money.remaining, money.currency, locale),
                },
              ]
            : []),
        ]
      : []),
  ];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={p.title}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t.common.close}
          </Button>
          <Button icon={Printer} onClick={() => window.print()}>
            {p.action}
          </Button>
        </>
      }
    >
      <div className="print-doc">
        <PrintDocumentLayout
          hotelName={profile?.display_name || profile?.hotel.name || p.title}
          hotelAddress={[profile?.city, profile?.country].filter(Boolean).join(", ") || undefined}
          docTitle={p.title}
          docNumber={r.reservation_number}
          meta={meta}
          notes={note || undefined}
          notesLabel={d.notes}
          footer={money ? p.footerFinancial : p.footer}
        >
          {companions.length > 0 ? (
            <div className="print-companions">
              <p className="muted">
                <strong>{d.sectionCompanions}</strong>
              </p>
              <table className="print-table">
                <thead>
                  <tr>
                    <th>{t.reservations.form.name}</th>
                    <th>{t.reservations.wizard.companions.relationship}</th>
                  </tr>
                </thead>
                <tbody>
                  {companions.map((occ) => (
                    <tr key={occ.id}>
                      <td>{occupantDisplayName(occ, t)}</td>
                      <td>{relationshipLabel(occ.relationship, t)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {/* §40 — recorded payments: method + base amount, with the original
              tender in parentheses for a foreign-currency payment. Printed only
              when a viewable summary carries payments. */}
          {money && money.payments.length > 0 ? (
            <div className="print-payments">
              <p className="muted">
                <strong>{b.recordedPaymentsSection}</strong>
              </p>
              <table className="print-table">
                <thead>
                  <tr>
                    <th>{t.finance.print.method}</th>
                    <th>{t.finance.print.amount}</th>
                  </tr>
                </thead>
                <tbody>
                  {money.payments.map((payment) => (
                    <tr key={payment.id}>
                      <td>{t.finance.methods[payment.method]}</td>
                      <td>
                        {formatMoney(
                          payment.amount,
                          payment.currency || money.currency,
                          locale,
                        )}
                        {isForeignPayment(payment, money.currency)
                          ? ` (${formatMoney(
                              payment.original_amount as string,
                              payment.payment_currency,
                              locale,
                            )})`
                          : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </PrintDocumentLayout>
      </div>
    </Modal>
  );
}
