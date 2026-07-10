"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import Link from "next/link";

import { useQuickAction } from "@/lib/useQuickAction";
import {
  BedDouble,
  CalendarCheck,
  CalendarClock,
  ClipboardCheck,
  Copy,
  DoorOpen,
  MessageSquareText,
  Plus,
  Trash2,
  UserRound,
  X,
  Zap,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  Modal,
  Pagination,
  SectionCard,
  Select,
  StepSummaryCard,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import {
  cancelReservation,
  checkAvailability,
  confirmReservation,
  createReservation,
  getReservationLogs,
  getReservationOverview,
  listReservations,
  updateReservation,
  type ReservationCreateBody,
  type ReservationLineBody,
} from "@/lib/api/reservations";
import { createGuest, listGuests } from "@/lib/api/guests";
import { checkIn as frontDeskCheckIn } from "@/lib/api/stays";
import { listRoomTypes, listRooms } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type {
  Guest,
  Reservation,
  ReservationStatusLogEntry,
  Room,
  RoomType,
  TypeAvailability,
} from "@/lib/api/types";
import { formatDate, reservationStatusLabel, reservationStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import {
  STATUS_BOUND_VIEWS,
  VIEW_PARAMS,
  type ReservationView,
} from "./reservationViews";

const PAGE_SIZE = 25;
const STATUSES = ["held", "confirmed", "cancelled", "expired"] as const;
const SOURCES = ["direct", "phone", "walk_in", "public_website", "other"] as const;

/** The reservations LIST (owner reorg): one component serves all seven
 * views — bookings only, never stays/check-ins. Props come from the page:
 * the active view, a create signal from the page's "New Reservation"
 * button, and a change callback so the summary counters stay honest. */
export function ReservationsTab({
  view = "all",
  createSignal = 0,
  onChanged,
}: {
  view?: ReservationView;
  createSignal?: number;
  onChanged?: () => void;
}) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const access = useHotelAccess();
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));

  const [types, setTypes] = useState<RoomType[]>([]);
  const [rows, setRows] = useState<Reservation[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [type, setType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [creating, setCreating] = useState(false);
  const [chooserOpen, setChooserOpen] = useState(false);
  const [initialKind, setInitialKind] = useState<"instant" | "future" | null>(null);
  // The page's "New Reservation" button pulses this prop — it opens the
  // TYPE CHOOSER (instant vs future), never a hidden dropdown. Consume real
  // increments only (the initial value must not auto-open on mount).
  const lastSignal = useRef(createSignal);
  useEffect(() => {
    if (createSignal !== lastSignal.current) {
      lastSignal.current = createSignal;
      setChooserOpen(true);
    }
  }, [createSignal]);

  function chooseKind(kind: "instant" | "future") {
    setChooserOpen(false);
    setInitialKind(kind);
    setCreating(true);
  }
  // Switching views resets pagination and any conflicting bound filters.
  useEffect(() => {
    setPage(1);
    if (STATUS_BOUND_VIEWS.includes(view)) setStatus("");
    if (view === "website") setSource("");
  }, [view]);
  const [quickLine, setQuickLine] = useState<{ room_type: string; room: string } | null>(null);
  // Quick actions: ?action=new ALWAYS opens the type chooser (owner UX) —
  // a preselected room from the rooms board is carried through so either
  // card opens the wizard with that room pinned. ?action=find&q= focuses
  // the list on a reservation number.
  useQuickAction("new", (params) => {
    const room = params.get("room");
    const roomType = params.get("room_type");
    setQuickLine(room && roomType ? { room, room_type: roomType } : null);
    setChooserOpen(true);
  });
  useQuickAction("find", (params) => {
    const q = params.get("q") ?? "";
    setSearch(q);
    setQuery(q);
    setPage(1);
  });
  const [editing, setEditing] = useState<Reservation | null>(null);
  const [details, setDetails] = useState<Reservation | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Reservation | null>(null);

  useEffect(() => {
    listRoomTypes()
      .then((r) => setTypes(r.results))
      .catch(() => setTypes([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listReservations({
        // The view's own slice first — user filters narrow WITHIN it.
        ...VIEW_PARAMS[view],
        page,
        status: status || VIEW_PARAMS[view].status,
        source: source || VIEW_PARAMS[view].source,
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
  }, [view, page, status, source, type, dateFrom, dateTo, query, t]);

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

  async function confirm(r: Reservation) {
    try {
      await confirmReservation(r.id);
      notify(t.reservations.saved);
      load();
      onChanged?.();
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  async function copyNumber(r: Reservation) {
    try {
      await navigator.clipboard.writeText(r.reservation_number);
      notify(t.reservations.views.copied);
    } catch {
      notify(r.reservation_number);
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

  const columns: Column<Reservation>[] = [
    {
      key: "reservation_number",
      header: t.reservations.list.number,
      render: (r) => (
        <span className="cluster">
          <strong>{r.reservation_number}</strong>
          <Button
            variant="ghost"
            size="sm"
            icon={Copy}
            onClick={() => copyNumber(r)}
          >
            {""}
          </Button>
        </span>
      ),
    },
    {
      key: "guest",
      header: t.reservations.list.guest,
      render: (r) => (
        <span className="stack-tight">
          <strong>{r.primary_guest_name}</strong>
          {r.primary_guest_phone ? <span className="muted">{r.primary_guest_phone}</span> : null}
        </span>
      ),
    },
    {
      key: "source",
      header: t.reservations.views.sourceLabel,
      render: (r) => (
        <Badge tone={r.source === "public_website" ? "info" : "neutral"}>
          {t.reservations.source[r.source] ?? r.source}
        </Badge>
      ),
    },
    {
      key: "dates",
      header: t.reservations.list.dates,
      render: (r) => `${formatDate(r.check_in_date, locale)} → ${formatDate(r.check_out_date, locale)}`,
    },
    { key: "nights", header: t.reservations.list.nights, render: (r) => r.nights },
    {
      key: "guests_count",
      header: t.reservations.views.guestsCount,
      render: (r) => r.total_guests,
    },
    {
      key: "rooms",
      header: t.reservations.list.rooms,
      render: (r) => r.lines.reduce((sum, l) => sum + l.quantity, 0),
    },
    {
      key: "created",
      header: t.reservations.views.createdAt,
      render: (r) => formatDate(r.created_at, locale),
    },
    {
      key: "status",
      header: t.common.status,
      render: (r) => (
        <Badge tone={reservationStatusTone(r.status)}>
          {reservationStatusLabel(r.status, t)}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => (
        <div className="table__actions">
          <Button variant="secondary" size="sm" onClick={() => setDetails(r)}>
            {t.reservations.list.view}
          </Button>
          {r.status === "held" && can("reservations.confirm") ? (
            <Button variant="ghost" size="sm" onClick={() => confirm(r)}>
              {t.reservations.list.confirm}
            </Button>
          ) : null}
          {(r.status === "held" || r.status === "confirmed") &&
          can("reservations.update") ? (
            <Button variant="ghost" size="sm" onClick={() => setEditing(r)}>
              {t.common.edit}
            </Button>
          ) : null}
          {(r.status === "held" || r.status === "confirmed") &&
          can("reservations.cancel") ? (
            <Button variant="danger" size="sm" onClick={() => setCancelTarget(r)}>
              {t.reservations.list.cancel}
            </Button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <Card>
        <form onSubmit={applySearch}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="res-search">
              <Input id="res-search" value={search} placeholder={t.reservations.views.searchPlaceholder} onChange={(e) => setSearch(e.target.value)} />
            </FormField>
            {!STATUS_BOUND_VIEWS.includes(view) ? (
              <FormField label={t.reservations.list.filterStatus} htmlFor="res-status">
                <Select id="res-status" value={status} placeholder={t.common.all} options={statusOptions} onChange={(e) => { setPage(1); setStatus(e.target.value); }} />
              </FormField>
            ) : null}
            {view !== "website" ? (
              <FormField label={t.reservations.views.sourceLabel} htmlFor="res-source">
                <Select id="res-source" value={source} placeholder={t.common.all} options={sourceOptions} onChange={(e) => { setPage(1); setSource(e.target.value); }} />
              </FormField>
            ) : null}
            <FormField label={t.reservations.list.filterType} htmlFor="res-type">
              <Select id="res-type" value={type} placeholder={t.common.all} options={typeOptions} onChange={(e) => { setPage(1); setType(e.target.value); }} />
            </FormField>
            <FormField label={t.reservations.list.dateFrom} htmlFor="res-from">
              <Input id="res-from" type="date" value={dateFrom} onChange={(e) => { setPage(1); setDateFrom(e.target.value); }} />
            </FormField>
            <FormField label={t.reservations.list.dateTo} htmlFor="res-to">
              <Input id="res-to" type="date" value={dateTo} onChange={(e) => { setPage(1); setDateTo(e.target.value); }} />
            </FormField>
            {hasFilters ? (
              <div className="filter-bar__actions cluster">
                <Button variant="ghost" size="sm" icon={X} onClick={clearFilters}>
                  {t.rooms.board.clearFilters}
                </Button>
              </div>
            ) : null}
          </FilterBar>
        </form>
      </Card>

      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? (
        <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} />
      ) : null}
      {!loading && !error ? (
        rows.length === 0 ? (
          <EmptyState
            title={t.reservations.views.noReservations}
            hint={t.reservations.views.emptyFiltered}
            icon={CalendarCheck}
          />
        ) : (
          <>
            <DataTable caption={t.reservations.list.title} columns={columns} rows={rows} rowKey={(r) => r.id} />
            <Pagination
              page={page}
              totalPages={totalPages}
              onPageChange={setPage}
              labels={{
                previous: t.pagination.previous,
                next: t.pagination.next,
                status: t.pagination.page.replace("{page}", String(page)).replace("{total}", String(totalPages)),
              }}
            />
          </>
        )
      ) : null}

      {/* Owner UX: choosing the reservation TYPE is an explicit modal with
          two big cards — never a dropdown. Instant stays a RESERVATION
          (check-in remains front-desk business). */}
      <Modal
        open={chooserOpen}
        onClose={() => setChooserOpen(false)}
        title={t.reservations.views.chooseType}
        closeLabel={t.common.close}
      >
        <div className="choice-cards">
          {/* Immediate = create + check the guest in via the EXISTING
              front-desk service, so it needs the real check-in permission. */}
          <button
            type="button"
            className="choice-card"
            disabled={!can("stays.check_in")}
            title={!can("stays.check_in") ? t.reservations.views.needCheckInPerm : undefined}
            onClick={() => chooseKind("instant")}
          >
            <span className="choice-card__icon">
              <Zap size={22} />
            </span>
            <strong>{t.reservations.views.instantTitle}</strong>
            <span className="muted">{t.reservations.views.instantDesc}</span>
          </button>
          <button type="button" className="choice-card" onClick={() => chooseKind("future")}>
            <span className="choice-card__icon">
              <CalendarClock size={22} />
            </span>
            <strong>{t.reservations.views.futureTitle}</strong>
            <span className="muted">{t.reservations.views.futureDesc}</span>
          </button>
        </div>
      </Modal>

      <ReservationModal
        open={creating}
        types={types}
        initialLine={quickLine}
        initialKind={initialKind}
        onClose={() => { setCreating(false); setQuickLine(null); setInitialKind(null); }}
        onSaved={() => { setCreating(false); setQuickLine(null); setInitialKind(null); notify(t.reservations.saved); setPage(1); load(); onChanged?.(); }}
        onView={(r) => { setCreating(false); setQuickLine(null); setInitialKind(null); setPage(1); load(); onChanged?.(); setDetails(r); }}
        onRefresh={() => { load(); onChanged?.(); }}
      />
      <ReservationModal
        open={editing !== null}
        reservation={editing ?? undefined}
        types={types}
        onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); notify(t.reservations.saved); load(); onChanged?.(); }}
      />
      <DetailsModal
        open={details !== null}
        reservation={details ?? undefined}
        onClose={() => setDetails(null)}
        onEdit={(r) => { setDetails(null); setEditing(r); }}
        onConfirm={(r) => { setDetails(null); confirm(r); }}
        onCancel={(r) => { setDetails(null); setCancelTarget(r); }}
      />
      <CancelModal
        open={cancelTarget !== null}
        reservation={cancelTarget ?? undefined}
        onClose={() => setCancelTarget(null)}
        onDone={() => { setCancelTarget(null); notify(t.reservations.saved); load(); onChanged?.(); }}
      />
    </>
  );
}

// --------------------------------------------------------------------------- //
// Create / edit modal                                                         //
// --------------------------------------------------------------------------- //

interface LineDraft {
  room_type: string;
  room: string;
  quantity: string;
}

function todayISO(): string {
  const now = new Date();
  const off = now.getTimezoneOffset();
  return new Date(now.getTime() - off * 60_000).toISOString().slice(0, 10);
}

type WizardResult =
  | { type: "created"; reservation: Reservation }
  | { type: "checkedIn"; reservation: Reservation; roomNumber: string }
  | { type: "checkinFailed"; reservation: Reservation; reason: string };

function ReservationModal({
  open,
  reservation,
  types,
  initialLine,
  initialKind,
  onClose,
  onSaved,
  onView,
  onRefresh,
}: {
  open: boolean;
  reservation?: Reservation;
  types: RoomType[];
  /** Optional preselected room line (operational board deep-link). */
  initialLine?: { room_type: string; room: string } | null;
  /** Booking kind from the type-chooser cards (owner UX): IMMEDIATE creates
   * the reservation then checks the guest in via the EXISTING front-desk
   * check-in service; FUTURE stays a plain booking with the arrival date
   * left to the user. */
  initialKind?: "instant" | "future" | null;
  onClose: () => void;
  onSaved: () => void;
  /** Open the created reservation's details (success screens). */
  onView?: (r: Reservation) => void;
  /** Refresh the list/counters WITHOUT closing (success screens stay up). */
  onRefresh?: () => void;
}) {
  const { t, locale } = useI18n();
  const editing = Boolean(reservation);
  const [bookingKind, setBookingKind] = useState<"instant" | "future">("instant");
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [arrivalTime, setArrivalTime] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [nationality, setNationality] = useState("");
  const [docType, setDocType] = useState("");
  const [docNumber, setDocNumber] = useState("");
  const [adults, setAdults] = useState("2");
  const [children, setChildren] = useState("0");
  const [notes, setNotes] = useState("");
  const [special, setSpecial] = useState("");
  const [source, setSource] = useState("direct");
  const [channelName, setChannelName] = useState("");
  const [expectedPay, setExpectedPay] = useState("");
  const [initialStatus, setInitialStatus] = useState<"held" | "confirmed">("confirmed");
  const [holdExpires, setHoldExpires] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([{ room_type: "", room: "", quantity: "1" }]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [availability, setAvailability] = useState<TypeAvailability[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Wizard state (owner UX): four ordered steps, optional existing-guest
  // pick (required data for the IMMEDIATE check-in), the hotel business
  // date (the immediate arrival date — the client clock can differ), and
  // the final success / partial-failure screen.
  const [step, setStep] = useState(0);
  const [guests, setGuests] = useState<Guest[]>([]);
  const [guestId, setGuestId] = useState("");
  const [businessDate, setBusinessDate] = useState("");
  const [result, setResult] = useState<WizardResult | null>(null);

  useEffect(() => {
    if (!open) return;
    const kind = reservation?.booking_kind ?? initialKind ?? "instant";
    setBookingKind(kind);
    setStep(0);
    setGuestId("");
    setResult(null);
    setBusinessDate("");
    // Future bookings leave the arrival date to the user; instant starts
    // on the HOTEL business date (still a RESERVATION until check-in).
    setCheckIn(reservation?.check_in_date ?? (kind === "future" ? "" : todayISO()));
    if (!reservation && kind === "instant") {
      getReservationOverview()
        .then((o) => {
          setBusinessDate(o.business_date);
          setCheckIn(o.business_date);
        })
        .catch(() => {
          // The client date stays as a fallback; the backend re-validates.
        });
    }
    // Existing guests for the optional pick / the immediate check-in.
    listGuests({ page_size: 200, is_active: "true" })
      .then((r) => setGuests(r.results))
      .catch(() => setGuests([]));
    setCheckOut(reservation?.check_out_date ?? "");
    setArrivalTime(reservation?.expected_arrival_time ?? "");
    setName(reservation?.primary_guest_name ?? "");
    setPhone(reservation?.primary_guest_phone ?? "");
    setEmail(reservation?.primary_guest_email ?? "");
    setNationality(reservation?.primary_guest_nationality ?? "");
    setDocType(reservation?.primary_guest_document_type ?? "");
    setDocNumber(reservation?.primary_guest_document_number ?? "");
    setAdults(String(reservation?.adults ?? 2));
    setChildren(String(reservation?.children ?? 0));
    setNotes(reservation?.notes ?? "");
    setSpecial(reservation?.special_requests ?? "");
    setSource(reservation?.source ?? "direct");
    setChannelName(reservation?.booking_channel_name ?? "");
    setExpectedPay(reservation?.expected_payment_method ?? "");
    setInitialStatus("confirmed");
    setHoldExpires("");
    setLines(
      reservation && reservation.lines.length > 0
        ? reservation.lines.map((l) => ({
            room_type: String(l.room_type),
            room: l.room ? String(l.room) : "",
            quantity: String(l.quantity),
          }))
        : [
            {
              room_type: initialLine?.room_type ?? "",
              room: initialLine?.room ?? "",
              quantity: "1",
            },
          ],
    );
    setError(null);
    // Bookable rooms for the optional per-line assignment (UX only — the
    // backend re-validates assignability and conflicts).
    listRooms({ page_size: 200 })
      .then((r) => setRooms(r.results))
      .catch(() => setRooms([]));
  }, [open, reservation, initialLine, initialKind]);

  // Instant bookings start today; switching kinds keeps the dates honest.
  function changeKind(kind: "instant" | "future") {
    setBookingKind(kind);
    if (kind === "instant") setCheckIn(todayISO());
  }

  // Live availability for the chosen dates — conflicts are shown per line and
  // re-validated by the backend before saving.
  useEffect(() => {
    if (!open || !checkIn || !checkOut || checkIn >= checkOut) {
      setAvailability([]);
      return;
    }
    let stale = false;
    checkAvailability({ check_in_date: checkIn, check_out_date: checkOut })
      .then((r) => { if (!stale) setAvailability(r.results); })
      .catch(() => { if (!stale) setAvailability([]); });
    return () => { stale = true; };
  }, [open, checkIn, checkOut]);

  const nights = useMemo(() => {
    if (!checkIn || !checkOut) return 0;
    const diff = (new Date(checkOut).getTime() - new Date(checkIn).getTime()) / 86_400_000;
    return diff > 0 ? Math.round(diff) : 0;
  }, [checkIn, checkOut]);

  function updateLine(i: number, patch: Partial<LineDraft>) {
    setLines((prev) =>
      prev.map((l, idx) => {
        if (idx !== i) return l;
        const next = { ...l, ...patch };
        // Changing the room type invalidates a specific room assignment.
        if (patch.room_type !== undefined && patch.room_type !== l.room_type) {
          next.room = "";
        }
        // A pinned room implies quantity 1.
        if (patch.room) next.quantity = "1";
        return next;
      }),
    );
  }
  function addLine() {
    setLines((prev) => [...prev, { room_type: "", room: "", quantity: "1" }]);
  }
  function removeLine(i: number) {
    setLines((prev) => (prev.length > 1 ? prev.filter((_, idx) => idx !== i) : prev));
  }

  const ASSIGNABLE = new Set(["available", "dirty", "cleaning"]);
  function roomOptionsFor(typeId: string) {
    if (!typeId) return [];
    return rooms
      .filter((r) => String(r.room_type) === typeId && r.is_active && ASSIGNABLE.has(r.status))
      .map((r) => ({ value: String(r.id), label: r.number }));
  }

  function availabilityFor(typeId: string): TypeAvailability | undefined {
    return availability.find((a) => String(a.room_type) === typeId);
  }

  /** Pick an existing guest → autofill the snapshot fields. */
  function selectGuest(id: string) {
    setGuestId(id);
    const guest = guests.find((g) => String(g.id) === id);
    if (!guest) return;
    setName(guest.full_name);
    setPhone(guest.phone ?? "");
    setEmail(guest.email ?? "");
    setNationality(guest.nationality ?? "");
    if (guest.document_type) setDocType(guest.document_type);
    if (guest.document_number) setDocNumber(guest.document_number);
  }

  const isInstant = !editing && bookingKind === "instant";

  /** Per-step gate (owner spec: no advancing with missing basics). */
  function validateStep(current: number): string | null {
    if (current === 0 && !name.trim()) return t.reservations.form.nameRequired;
    return null;
  }

  function goNext() {
    const problem = validateStep(step);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setStep((s) => Math.min(3, s + 1));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!name.trim()) return setError(t.reservations.form.nameRequired);
    if (!checkIn || !checkOut) return setError(t.errors.validation);
    if (checkOut <= checkIn) return setError(t.errors.validation);
    const cleanLines: ReservationLineBody[] = lines
      .filter((l) => l.room_type)
      .map((l) => ({
        room_type: Number(l.room_type),
        room: l.room ? Number(l.room) : null,
        quantity: l.room ? 1 : Number(l.quantity) || 1,
      }));
    if (cleanLines.length === 0) return setError(t.reservations.form.linesRequired);
    // The IMMEDIATE flow admits the guest right away — the existing
    // check-in service requires one specific room.
    if (isInstant && !cleanLines[0]?.room) {
      return setError(t.reservations.views.roomRequiredInstant);
    }

    setBusy(true);
    try {
      const common = {
        booking_kind: bookingKind,
        check_in_date: checkIn,
        check_out_date: checkOut,
        expected_arrival_time: arrivalTime || null,
        primary_guest_name: name.trim(),
        primary_guest_phone: phone.trim(),
        primary_guest_email: email.trim(),
        primary_guest_nationality: nationality.trim(),
        primary_guest_document_type: docType,
        primary_guest_document_number: docNumber.trim(),
        adults: Number(adults) || 1,
        children: Number(children) || 0,
        notes: notes.trim(),
        special_requests: special.trim(),
        source,
        booking_channel_name: channelName.trim(),
        expected_payment_method: expectedPay,
        lines: cleanLines,
      };
      if (editing && reservation) {
        await updateReservation(reservation.id, common);
        onSaved();
        return;
      }
      // The check-in service needs a GUEST PROFILE — resolve it FIRST so a
      // guest failure leaves nothing half-done (same flow as front-desk).
      let checkinGuestId: number | null = null;
      if (isInstant) {
        if (guestId) {
          checkinGuestId = Number(guestId);
        } else {
          const guest = await createGuest({
            full_name: name.trim(),
            phone: phone.trim(),
            email: email.trim(),
            nationality: nationality.trim(),
            document_number: docNumber.trim(),
            ...(docType
              ? { document_type: docType as Guest["document_type"] }
              : {}),
          });
          checkinGuestId = guest.id;
        }
      }
      const body: ReservationCreateBody = {
        // Immediate check-in requires a CONFIRMED reservation (existing rule).
        status: isInstant ? "confirmed" : initialStatus,
        ...common,
      };
      if (!isInstant && initialStatus === "held") {
        body.hold_expires_at = holdExpires ? new Date(holdExpires).toISOString() : null;
      }
      const created = await createReservation(body);
      if (!isInstant) {
        setResult({ type: "created", reservation: created });
        onRefresh?.();
        return;
      }
      // IMMEDIATE: admit the guest through the EXISTING front-desk check-in
      // service — no new logic, all its validations apply. A failure here
      // must never hide: the reservation exists, say so plainly.
      try {
        await frontDeskCheckIn({
          reservation: created.id,
          reservation_line: created.lines[0]?.id ?? null,
          room: Number(cleanLines[0].room),
          primary_guest: checkinGuestId as number,
        });
        setResult({
          type: "checkedIn",
          reservation: created,
          roomNumber:
            rooms.find((r) => String(r.id) === lines[0]?.room)?.number ?? "",
        });
      } catch (err) {
        setResult({
          type: "checkinFailed",
          reservation: created,
          reason: messageForError(err, t),
        });
      }
      onRefresh?.();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const typeOptions = types
    .filter((ty) => ty.is_active)
    .map((ty) => ({ value: String(ty.id), label: `${ty.name} (${ty.max_capacity})` }));
  const sourceOptions = (["direct", "phone", "walk_in", "other"] as const).map((s) => ({
    value: s,
    label: t.reservations.source[s],
  }));
  const kindOptions = (["instant", "future"] as const).map((k) => ({
    value: k,
    label: t.reservations.kind[k],
  }));
  const payOptions = (["cash", "card", "bank_transfer", "other"] as const).map((v) => ({
    value: v,
    label: t.reservations.expectedPayment[v],
  }));
  const docTypeOptions = (["national_id", "passport", "driving_license", "other"] as const).map((v) => ({
    value: v,
    label: t.guests.documentTypes[v],
  }));

  const summaryType = types.find((ty) => String(ty.id) === lines[0]?.room_type);
  const summaryRoom = rooms.find((r) => String(r.id) === lines[0]?.room);

  const v = t.reservations.views;
  const stepTitles = [v.stepGuest, v.stepCompanions, v.stepDocuments, v.stepBooking];
  const finalLabel = editing
    ? t.reservations.form.save
    : isInstant
      ? v.saveAndCheckIn
      : v.saveReservation;

  return (
    <Modal
      open={open}
      onClose={result ? onSaved : onClose}
      title={editing ? t.reservations.form.editTitle : t.reservations.form.createTitle}
      closeLabel={t.common.close}
      footer={
        result ? (
          <Button variant="secondary" onClick={onSaved}>{t.common.close}</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
            {step > 0 ? (
              <Button variant="ghost" onClick={() => { setError(null); setStep((s) => s - 1); }} disabled={busy}>
                {t.pagination.previous}
              </Button>
            ) : null}
            {step < 3 ? (
              <Button onClick={goNext} disabled={busy}>{t.pagination.next}</Button>
            ) : (
              <Button form="res-form" type="submit" loading={busy}>{finalLabel}</Button>
            )}
          </>
        )
      }
    >
      {result ? (
        <div className="stack">
          {result.type === "checkinFailed" ? (
            <Alert tone="warning">
              {v.checkinFailed} — {result.reason}
            </Alert>
          ) : (
            <Alert tone="success">
              {result.type === "checkedIn" ? v.successCheckedIn : v.successCreated}
            </Alert>
          )}
          <dl className="room-op-details">
            <div className="room-op-details__row">
              <dt>{t.reservations.list.number}</dt>
              <dd>{result.reservation.reservation_number}</dd>
            </div>
            <div className="room-op-details__row">
              <dt>{t.reservations.form.name}</dt>
              <dd>{result.reservation.primary_guest_name}</dd>
            </div>
            {result.type === "checkedIn" && result.roomNumber ? (
              <div className="room-op-details__row">
                <dt>{t.reservations.form.room}</dt>
                <dd>{result.roomNumber}</dd>
              </div>
            ) : null}
            <div className="room-op-details__row">
              <dt>{t.reservations.form.stayDates}</dt>
              <dd>
                {formatDate(result.reservation.check_in_date, locale)} →{" "}
                {formatDate(result.reservation.check_out_date, locale)}
              </dd>
            </div>
          </dl>
          <div className="cluster">
            <Button variant="secondary" size="sm" onClick={() => onView?.(result.reservation)}>
              {v.openReservation}
            </Button>
            {result.type === "checkedIn" ? (
              <>
                <Link href="/hotel/front-desk?tab=current" className="btn btn--secondary btn--sm">
                  {v.viewStay}
                </Link>
                <Link href="/hotel/finance?tab=folios" className="btn btn--ghost btn--sm">
                  {t.quickActions.guestFolio}
                </Link>
              </>
            ) : null}
            {result.type === "checkinFailed" ? (
              <Link href="/hotel/front-desk?tab=arrivals" className="btn btn--secondary btn--sm">
                {v.goToFrontDesk}
              </Link>
            ) : null}
          </div>
        </div>
      ) : (
      <form id="res-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}

        {/* Wizard step indicator (owner UX): four clear ordered steps. */}
        <div className="cluster" aria-label={stepTitles[step]}>
          {stepTitles.map((title, i) => (
            <span key={title} className={i === step ? "chip" : "floor-chip"}>
              {i + 1}. {title}
            </span>
          ))}
        </div>

        {/* STEP 1 — guest information (existing-guest pick autofills; the
            IMMEDIATE flow uses the picked/created GUEST PROFILE at check-in). */}
        {step === 0 ? (
          <SectionCard title={v.stepGuest} icon={UserRound}>
            <FormField
              label={v.existingGuestLabel}
              htmlFor="res-guest-pick"
              hint={isInstant ? v.existingGuestHintInstant : undefined}
            >
              <Select
                id="res-guest-pick"
                value={guestId}
                placeholder={t.frontDesk.checkInModal.selectGuest}
                options={guests.map((g) => ({ value: String(g.id), label: g.full_name }))}
                onChange={(e) => selectGuest(e.target.value)}
              />
            </FormField>
            <div className="form-grid">
              <FormField label={t.reservations.form.name} htmlFor="res-name">
                <Input id="res-name" value={name} required onChange={(e) => setName(e.target.value)} />
              </FormField>
              <FormField label={t.reservations.form.phone} htmlFor="res-phone">
                <Input id="res-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
              </FormField>
              <FormField label={t.reservations.form.email} htmlFor="res-email">
                <Input id="res-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </FormField>
              <FormField label={t.reservations.form.nationality} htmlFor="res-nat">
                <Input id="res-nat" value={nationality} onChange={(e) => setNationality(e.target.value)} />
              </FormField>
            </div>
          </SectionCard>
        ) : null}

        {/* STEP 2 — companions: the reservation model carries COUNTS; named
            companions are attached at check-in (front desk), by design. */}
        {step === 1 ? (
          <SectionCard title={v.stepCompanions} icon={UserRound}>
            <div className="form-grid">
              <FormField label={t.reservations.form.adults} htmlFor="res-adults">
                <Input id="res-adults" type="number" min="1" value={adults} onChange={(e) => setAdults(e.target.value)} />
              </FormField>
              <FormField label={t.reservations.form.children} htmlFor="res-children">
                <Input id="res-children" type="number" min="0" value={children} onChange={(e) => setChildren(e.target.value)} />
              </FormField>
            </div>
            <p className="muted small">{v.companionsHint}</p>
          </SectionCard>
        ) : null}

        {/* STEP 3 — documents (the reservation's existing snapshot fields —
            there is no reservation-document upload in the current system). */}
        {step === 2 ? (
          <SectionCard title={v.stepDocuments} icon={ClipboardCheck}>
            <div className="form-grid">
              <FormField label={t.reservations.form.documentType} htmlFor="res-doc-type">
                <Select id="res-doc-type" value={docType} placeholder={t.guests.documentTypes.none} options={docTypeOptions} onChange={(e) => setDocType(e.target.value)} />
              </FormField>
              <FormField label={t.reservations.form.documentNumber} htmlFor="res-doc-num">
                <Input id="res-doc-num" value={docNumber} onChange={(e) => setDocNumber(e.target.value)} />
              </FormField>
            </div>
            <p className="muted small">{v.documentsHint}</p>
          </SectionCard>
        ) : null}

        {step === 3 ? (
          <>
        {/* Booking kind & dates */}
        <SectionCard title={t.reservations.form.sectionKindDates} icon={CalendarClock}>
          <div className="form-grid">
            {editing ? (
              <FormField label={t.reservations.form.bookingKind} htmlFor="res-kind" hint={bookingKind === "instant" ? t.reservations.form.instantHint : t.reservations.form.futureHint}>
                <Select id="res-kind" value={bookingKind} options={kindOptions} onChange={(e) => changeKind(e.target.value as "instant" | "future")} />
              </FormField>
            ) : (
              <FormField label={t.reservations.form.bookingKind} htmlFor="res-kind-fixed">
                <Input id="res-kind-fixed" value={t.reservations.kind[bookingKind]} disabled readOnly />
              </FormField>
            )}
            <FormField
              label={t.reservations.form.checkIn}
              htmlFor="res-in"
              hint={isInstant && businessDate ? t.reservations.form.instantHint : undefined}
            >
              <Input id="res-in" type="date" value={checkIn} required disabled={bookingKind === "instant"} onChange={(e) => setCheckIn(e.target.value)} />
            </FormField>
            <FormField label={t.reservations.form.checkOut} htmlFor="res-out">
              <Input id="res-out" type="date" value={checkOut} required onChange={(e) => setCheckOut(e.target.value)} />
            </FormField>
            <FormField label={t.reservations.form.nights} htmlFor="res-nights">
              <Input id="res-nights" value={String(nights)} disabled readOnly />
            </FormField>
            <FormField label={t.reservations.form.arrivalTime} htmlFor="res-arrival">
              <Input id="res-arrival" type="time" value={arrivalTime} onChange={(e) => setArrivalTime(e.target.value)} />
            </FormField>
          </div>
        </SectionCard>

        {/* Rooms & availability */}
        <SectionCard title={t.reservations.form.sectionRooms} icon={BedDouble}>
          {isInstant ? <p className="muted small">{v.roomRequiredInstant}</p> : null}
          <div className="stack-tight">
            {lines.map((line, i) => {
              const avail = availabilityFor(line.room_type);
              const wanted = line.room ? 1 : Number(line.quantity) || 1;
              const conflict = avail && (!avail.can_book || avail.available_quantity < wanted);
              return (
                <div key={i} className="stack-tight">
                  <div className="line-row line-row--assign">
                    <FormField label={t.reservations.form.roomType} htmlFor={`line-type-${i}`}>
                      <Select
                        id={`line-type-${i}`}
                        value={line.room_type}
                        placeholder={t.reservations.form.selectType}
                        options={typeOptions}
                        onChange={(e) => updateLine(i, { room_type: e.target.value })}
                      />
                    </FormField>
                    <FormField label={t.reservations.form.room} htmlFor={`line-room-${i}`} hint={t.reservations.form.roomHint}>
                      <Select
                        id={`line-room-${i}`}
                        value={line.room}
                        placeholder={t.reservations.form.roomAny}
                        options={roomOptionsFor(line.room_type)}
                        disabled={!line.room_type}
                        onChange={(e) => updateLine(i, { room: e.target.value })}
                      />
                    </FormField>
                    <FormField label={t.reservations.form.quantity} htmlFor={`line-qty-${i}`}>
                      <Input id={`line-qty-${i}`} type="number" min="1" value={line.quantity} disabled={Boolean(line.room)} onChange={(e) => updateLine(i, { quantity: e.target.value })} />
                    </FormField>
                    <Button type="button" variant="ghost" size="sm" icon={Trash2} onClick={() => removeLine(i)} disabled={lines.length === 1}>
                      {t.reservations.form.removeLine}
                    </Button>
                  </div>
                  {line.room_type && avail ? (
                    conflict ? (
                      <Alert tone="warning">
                        {t.reservations.form.availabilityConflict.replace("{count}", String(avail.available_quantity))}
                      </Alert>
                    ) : (
                      <p className="muted small">
                        {t.reservations.form.availabilityOk.replace("{count}", String(avail.available_quantity))}
                      </p>
                    )
                  ) : null}
                </div>
              );
            })}
            {!isInstant ? (
              <Button type="button" variant="secondary" size="sm" icon={Plus} onClick={addLine}>
                {t.reservations.form.addLine}
              </Button>
            ) : null}
          </div>
          <p className="muted small">{t.reservations.form.availabilityHint}</p>
        </SectionCard>

        {/* Section 4 — source & notes */}
        <SectionCard title={t.reservations.form.sectionSourceNotes} icon={MessageSquareText}>
          <div className="form-grid">
            <FormField label={t.reservations.form.source} htmlFor="res-source">
              <Select id="res-source" value={source} options={sourceOptions} onChange={(e) => setSource(e.target.value)} />
            </FormField>
            <FormField label={t.reservations.form.channelName} htmlFor="res-channel">
              <Input id="res-channel" value={channelName} onChange={(e) => setChannelName(e.target.value)} />
            </FormField>
            <FormField label={t.reservations.form.expectedPayment} htmlFor="res-pay" hint={t.reservations.form.expectedPaymentHint}>
              <Select id="res-pay" value={expectedPay} placeholder={t.common.all} options={payOptions} onChange={(e) => setExpectedPay(e.target.value)} />
            </FormField>
            {!editing && !isInstant ? (
              <FormField label={t.reservations.form.initialStatus} htmlFor="res-init">
                <Select
                  id="res-init"
                  value={initialStatus}
                  options={[
                    { value: "confirmed", label: t.reservations.form.createConfirmed },
                    { value: "held", label: t.reservations.form.createHeld },
                  ]}
                  onChange={(e) => setInitialStatus(e.target.value as "held" | "confirmed")}
                />
              </FormField>
            ) : null}
            {!editing && !isInstant && initialStatus === "held" ? (
              <FormField label={t.reservations.form.holdExpiry} htmlFor="res-hold" hint={t.reservations.form.holdExpiryHint}>
                <Input id="res-hold" type="datetime-local" value={holdExpires} onChange={(e) => setHoldExpires(e.target.value)} />
              </FormField>
            ) : null}
          </div>
          <FormField label={t.reservations.form.specialRequests} htmlFor="res-special">
            <Textarea id="res-special" value={special} onChange={(e) => setSpecial(e.target.value)} />
          </FormField>
          <FormField label={t.reservations.form.internalNotes} htmlFor="res-notes">
            <Textarea id="res-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </FormField>
        </SectionCard>

        {/* Review & save */}
        <StepSummaryCard
          title={t.reservations.form.sectionReview}
          icon={ClipboardCheck}
          hint={t.reservations.form.reviewHint}
          rows={[
            { label: t.reservations.form.name, value: name.trim() || "—" },
            { label: t.reservations.form.phone, value: phone.trim() || "—" },
            {
              label: t.reservations.form.bookingKind,
              value: (
                <span className="cluster">
                  {bookingKind === "instant" ? <Zap size={14} aria-hidden /> : <CalendarClock size={14} aria-hidden />}
                  {t.reservations.kind[bookingKind]}
                </span>
              ),
            },
            {
              label: t.reservations.form.stayDates,
              value: checkIn && checkOut ? `${formatDate(checkIn, locale)} → ${formatDate(checkOut, locale)}` : "—",
            },
            { label: t.reservations.form.nights, value: nights || "—" },
            { label: t.reservations.form.roomType, value: summaryType?.name ?? "—" },
            { label: t.reservations.form.room, value: summaryRoom?.number ?? t.reservations.form.roomAny },
            {
              label: t.common.status,
              value: editing && reservation
                ? reservationStatusLabel(reservation.status, t)
                : isInstant || initialStatus === "confirmed"
                  ? t.reservations.form.createConfirmed
                  : t.reservations.form.createHeld,
            },
          ]}
        />
          </>
        ) : null}
      </form>
      )}
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// Details modal                                                               //
// --------------------------------------------------------------------------- //

function DetailsModal({
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
  const [logs, setLogs] = useState<ReservationStatusLogEntry[]>([]);

  useEffect(() => {
    if (!open || !reservation) return;
    getReservationLogs(reservation.id)
      .then(setLogs)
      .catch(() => setLogs([]));
  }, [open, reservation]);

  if (!reservation) return null;
  const r = reservation;
  const editable = r.status === "held" || r.status === "confirmed";

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${t.reservations.details.title} ${r.reservation_number}`}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t.common.close}</Button>
          {/* A LIGHT operational link only (owner rule): check-in/out stay
              front-desk business — never actions inside reservations. */}
          {r.status === "confirmed" ? (
            <Link href="/hotel/front-desk?tab=arrivals" className="btn btn--ghost btn--sm">
              <DoorOpen size={16} />
              {t.reservations.views.frontDeskLink}
            </Link>
          ) : null}
          {editable ? <Button variant="ghost" onClick={() => onEdit(r)}>{t.reservations.details.edit}</Button> : null}
          {r.status === "held" ? <Button onClick={() => onConfirm(r)}>{t.reservations.details.confirm}</Button> : null}
          {editable ? <Button variant="danger" onClick={() => onCancel(r)}>{t.reservations.details.cancel}</Button> : null}
        </>
      }
    >
      <div className="stack">
        <div className="cluster">
          <Badge tone={reservationStatusTone(r.status)}>{reservationStatusLabel(r.status, t)}</Badge>
          <Badge tone={r.booking_kind === "instant" ? "success" : "info"}>
            {t.reservations.kind[r.booking_kind]}
          </Badge>
          <span className="muted">{t.reservations.source[r.source]}</span>
        </div>
        {r.public_cancel_requested_at ? (
          <Alert tone="warning">
            {t.reservations.details.publicCancelRequested}{" "}
            ({formatDate(r.public_cancel_requested_at, locale)})
            {r.public_cancel_reason ? ` — ${r.public_cancel_reason}` : ""}
          </Alert>
        ) : null}
        <dl className="detail-grid">
          <div><dt>{t.reservations.details.guest}</dt><dd>{r.primary_guest_name}</dd></div>
          {r.primary_guest_phone ? <div><dt>{t.reservations.details.phone}</dt><dd>{r.primary_guest_phone}</dd></div> : null}
          {r.primary_guest_email ? <div><dt>{t.reservations.details.email}</dt><dd>{r.primary_guest_email}</dd></div> : null}
          {r.primary_guest_nationality ? <div><dt>{t.reservations.form.nationality}</dt><dd>{r.primary_guest_nationality}</dd></div> : null}
          {r.primary_guest_document_number ? (
            <div>
              <dt>{t.reservations.form.documentNumber}</dt>
              <dd>{r.primary_guest_document_number}</dd>
            </div>
          ) : null}
          <div><dt>{t.reservations.details.dates}</dt><dd>{formatDate(r.check_in_date, locale)} → {formatDate(r.check_out_date, locale)}</dd></div>
          <div><dt>{t.reservations.details.nights}</dt><dd>{r.nights}</dd></div>
          <div><dt>{t.reservations.details.guests}</dt><dd>{r.total_guests}</dd></div>
          {r.expected_arrival_time ? <div><dt>{t.reservations.form.arrivalTime}</dt><dd>{r.expected_arrival_time}</dd></div> : null}
          {r.booking_channel_name ? <div><dt>{t.reservations.form.channelName}</dt><dd>{r.booking_channel_name}</dd></div> : null}
          {r.expected_payment_method ? (
            <div>
              <dt>{t.reservations.form.expectedPayment}</dt>
              <dd>{t.reservations.expectedPayment[r.expected_payment_method]}</dd>
            </div>
          ) : null}
          {r.hold_expires_at ? <div><dt>{t.reservations.details.holdExpires}</dt><dd>{formatDate(r.hold_expires_at, locale)}</dd></div> : null}
          {r.no_show_reason ? <div><dt>{t.reservations.details.noShowReason}</dt><dd>{r.no_show_reason}</dd></div> : null}
          {r.cancellation_reason ? <div><dt>{t.reservations.details.cancellationReason}</dt><dd>{r.cancellation_reason}</dd></div> : null}
          {r.created_by ? <div><dt>{t.reservations.details.createdBy}</dt><dd>{r.created_by}</dd></div> : null}
        </dl>

        <div>
          <h4>{t.reservations.details.rooms}</h4>
          <ul className="mini-list">
            {r.lines.map((l) => (
              <li key={l.id} className="mini-list__row">
                <span>{l.room_type_name} <span className="muted">({l.room_type_code})</span></span>
                <span>
                  {l.room_number ? (
                    <Badge tone="info">{t.reservations.details.room} {l.room_number}</Badge>
                  ) : (
                    `× ${l.quantity}`
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {r.notes ? <div><h4>{t.reservations.details.notes}</h4><p>{r.notes}</p></div> : null}
        {r.special_requests ? <div><h4>{t.reservations.details.specialRequests}</h4><p>{r.special_requests}</p></div> : null}

        <div>
          <h4>{t.reservations.details.history}</h4>
          {logs.length === 0 ? (
            <p className="muted">{t.reservations.details.noHistory}</p>
          ) : (
            <ul className="mini-list">
              {logs.map((log, i) => (
                <li key={i} className="mini-list__row">
                  <span>{log.previous_status ? `${log.previous_status} → ` : ""}{log.new_status}{log.note ? ` · ${log.note}` : ""}</span>
                  <span className="muted">{formatDate(log.created_at, locale)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
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
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="cancel-form" type="submit" variant="danger" loading={busy}>{t.reservations.cancelDialog.confirm}</Button>
        </>
      }
    >
      <form id="cancel-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="info">{t.reservations.cancelDialog.body}</Alert>
        <FormField label={t.reservations.cancelDialog.reason} htmlFor="cancel-reason">
          <Textarea id="cancel-reason" value={reason} required placeholder={t.reservations.cancelDialog.reasonPlaceholder} onChange={(e) => setReason(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}
