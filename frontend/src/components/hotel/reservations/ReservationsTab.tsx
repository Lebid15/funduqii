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
  MessageSquareText,
  Plus,
  SlidersHorizontal,
  Trash2,
  UserRound,
  X,
  Zap,
} from "lucide-react";

import {
  Alert,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Icon,
  Input,
  LoadingState,
  Modal,
  Pagination,
  SectionCard,
  Select,
  StepSummaryCard,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  cancelReservation,
  checkAvailability,
  confirmReservation,
  createReservation,
  getReservationOverview,
  listReservations,
  updateReservation,
  type ReservationCreateBody,
  type ReservationLineBody,
  type ReservationUpdateBody,
} from "@/lib/api/reservations";
import { createGuest, listGuests } from "@/lib/api/guests";
import { checkIn as frontDeskCheckIn } from "@/lib/api/stays";
import { listRoomTypes, listRooms } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type {
  Guest,
  Reservation,
  Room,
  RoomType,
  TypeAvailability,
} from "@/lib/api/types";
import { formatDate, reservationStatusLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { ReservationCard } from "./ReservationCard";
import { ReservationDetailsModal } from "./ReservationDetailsModal";
import {
  ReservationSummaryCards,
  type ReservationCounts,
  type StatusCard,
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
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));

  const [types, setTypes] = useState<RoomType[]>([]);
  const [typesLoaded, setTypesLoaded] = useState(false);
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

  const [creating, setCreating] = useState(false);
  const [chooserOpen, setChooserOpen] = useState(false);
  const [initialKind, setInitialKind] = useState<"instant" | "future" | null>(null);
  const [quickLine, setQuickLine] = useState<{ room_type: string; room: string } | null>(null);
  const [editing, setEditing] = useState<Reservation | null>(null);
  const [details, setDetails] = useState<Reservation | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Reservation | null>(null);
  const [renewTarget, setRenewTarget] = useState<Reservation | null>(null);

  // The page's "New reservation" button pulses this prop — it opens the TYPE
  // CHOOSER (instant vs future). Consume real increments only (the initial
  // value must not auto-open on mount).
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

  // Deep-links: ?action=new opens the chooser (optionally with a room pinned
  // from the rooms board); ?action=find&q= focuses the list on a reservation.
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

  const loadOverview = useCallback(() => {
    getReservationOverview()
      .then((o) =>
        setOverview({
          counts: {
            total: o.total,
            confirmed: o.confirmed,
            held: o.held,
            cancelled: o.cancelled,
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

  // The active summary card mirrors the status filter; a non-card status
  // (expired) highlights nothing, and Total (=="") highlights on no filter.
  const activeCard: StatusCard | null =
    status === "" || status === "confirmed" || status === "held" || status === "cancelled"
      ? (status as StatusCard)
      : null;

  function onCard(next: StatusCard) {
    setPage(1);
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
                    onView={setDetails}
                    onConfirm={confirm}
                    onEdit={setEditing}
                    onCancel={setCancelTarget}
                    onRenewHold={setRenewTarget}
                    onCopyNumber={copyNumber}
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

      {/* Type chooser (instant vs future) — an explicit modal, never a dropdown. */}
      <Modal
        open={chooserOpen}
        onClose={() => setChooserOpen(false)}
        title={t.reservations.views.chooseType}
        closeLabel={t.common.close}
      >
        <div className="choice-cards">
          <button
            type="button"
            className="choice-card"
            disabled={!can("stays.check_in")}
            title={!can("stays.check_in") ? t.reservations.views.needCheckInPerm : undefined}
            onClick={() => chooseKind("instant")}
          >
            <span className="choice-card__icon">
              <Icon icon={Zap} size="lg" />
            </span>
            <strong>{t.reservations.views.instantTitle}</strong>
            <span className="muted">{t.reservations.views.instantDesc}</span>
          </button>
          <button type="button" className="choice-card" onClick={() => chooseKind("future")}>
            <span className="choice-card__icon">
              <Icon icon={CalendarClock} size="lg" />
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
        onClose={() => {
          setCreating(false);
          setQuickLine(null);
          setInitialKind(null);
        }}
        onSaved={() => {
          setCreating(false);
          setQuickLine(null);
          setInitialKind(null);
          notify(t.reservations.saved);
          setPage(1);
          refresh();
        }}
        onView={(r) => {
          setCreating(false);
          setQuickLine(null);
          setInitialKind(null);
          setPage(1);
          refresh();
          setDetails(r);
        }}
        onRefresh={refresh}
      />
      <ReservationModal
        open={editing !== null}
        reservation={editing ?? undefined}
        types={types}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          notify(t.reservations.saved);
          refresh();
        }}
      />
      <ReservationDetailsModal
        open={details !== null}
        reservation={details ?? undefined}
        onClose={() => setDetails(null)}
        onEdit={(r) => {
          setDetails(null);
          setEditing(r);
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
      <RenewHoldModal
        open={renewTarget !== null}
        reservation={renewTarget ?? undefined}
        onClose={() => setRenewTarget(null)}
        onDone={() => {
          setRenewTarget(null);
          notify(t.reservations.saved);
          refresh();
        }}
      />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Create / edit wizard                                                        //
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
  initialLine?: { room_type: string; room: string } | null;
  initialKind?: "instant" | "future" | null;
  onClose: () => void;
  onSaved: () => void;
  onView?: (r: Reservation) => void;
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
  // Two ordered steps (guest → booking+review), an optional existing-guest
  // pick (required for the IMMEDIATE check-in), the hotel business date, and
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
    setCheckIn(reservation?.check_in_date ?? (kind === "future" ? "" : todayISO()));
    if (!reservation && kind === "instant") {
      getReservationOverview()
        .then((o) => {
          setBusinessDate(o.business_date);
          setCheckIn(o.business_date);
        })
        .catch(() => {
          /* The client date stays as a fallback; the backend re-validates. */
        });
    }
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
    listRooms({ page_size: 200 })
      .then((r) => setRooms(r.results))
      .catch(() => setRooms([]));
  }, [open, reservation, initialLine, initialKind]);

  function changeKind(kind: "instant" | "future") {
    setBookingKind(kind);
    if (kind === "instant") setCheckIn(todayISO());
  }

  // Live availability for the chosen dates AND party size — the backend applies
  // its own capacity/overbooking rule; conflicts show per line and are
  // re-validated before saving.
  useEffect(() => {
    if (!open || !checkIn || !checkOut || checkIn >= checkOut) {
      setAvailability([]);
      return;
    }
    let stale = false;
    checkAvailability({
      check_in_date: checkIn,
      check_out_date: checkOut,
      adults: Number(adults) || undefined,
      children: Number(children) || undefined,
    })
      .then((r) => {
        if (!stale) setAvailability(r.results);
      })
      .catch(() => {
        if (!stale) setAvailability([]);
      });
    return () => {
      stale = true;
    };
  }, [open, checkIn, checkOut, adults, children]);

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
        if (patch.room_type !== undefined && patch.room_type !== l.room_type) {
          next.room = "";
        }
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

  /** Pick an existing guest → autofill the snapshot fields (never silently
   * overwrite a masked document number). */
  function selectGuest(id: string) {
    setGuestId(id);
    const guest = guests.find((g) => String(g.id) === id);
    if (!guest) return;
    setName(guest.full_name);
    setPhone(guest.phone ?? "");
    setEmail(guest.email ?? "");
    setNationality(guest.nationality ?? "");
    if (guest.document_type) setDocType(guest.document_type);
    if (guest.document_number && !guest.document_number.includes("•")) {
      setDocNumber(guest.document_number);
    }
  }

  const isInstant = !editing && bookingKind === "instant";
  // Post-check-in guard: the guest is in-house — dates and rooms are frozen
  // (the backend refuses them too); only safe fields travel in the PATCH.
  const frozen = Boolean(reservation?.has_in_house_stay);

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
    setStep((s) => Math.min(1, s + 1));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!name.trim()) {
      setStep(0);
      return setError(t.reservations.form.nameRequired);
    }
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
        if (frozen) {
          const safe: ReservationUpdateBody = { ...common };
          delete safe.check_in_date;
          delete safe.check_out_date;
          delete safe.booking_kind;
          delete safe.lines;
          await updateReservation(reservation.id, safe);
        } else {
          await updateReservation(reservation.id, common);
        }
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
            ...(docType ? { document_type: docType as Guest["document_type"] } : {}),
          });
          checkinGuestId = guest.id;
        }
      }
      const body: ReservationCreateBody = {
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
          roomNumber: rooms.find((r) => String(r.id) === lines[0]?.room)?.number ?? "",
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
  const docTypeOptions = (["national_id", "passport", "driving_license", "other"] as const).map(
    (v) => ({ value: v, label: t.guests.documentTypes[v] }),
  );

  const summaryType = types.find((ty) => String(ty.id) === lines[0]?.room_type);
  const summaryRoom = rooms.find((r) => String(r.id) === lines[0]?.room);

  const v = t.reservations.views;
  const stepTitles = [v.stepGuest, v.stepBooking];
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
      size="lg"
      footer={
        result ? (
          <Button variant="secondary" onClick={onSaved}>
            {t.common.close}
          </Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              {t.common.cancel}
            </Button>
            {step > 0 ? (
              <Button
                variant="ghost"
                onClick={() => {
                  setError(null);
                  setStep((s) => s - 1);
                }}
                disabled={busy}
              >
                {t.pagination.previous}
              </Button>
            ) : null}
            {step < 1 ? (
              <Button onClick={goNext} disabled={busy}>
                {t.pagination.next}
              </Button>
            ) : (
              <Button form="res-form" type="submit" loading={busy}>
                {finalLabel}
              </Button>
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
            <div className="room-op-details__row">
              <dt>{t.common.status}</dt>
              <dd>{reservationStatusLabel(result.reservation.status, t)}</dd>
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

          {/* Step indicator — two clear ordered steps. */}
          <div className="cluster" aria-label={stepTitles[step]}>
            {stepTitles.map((title, i) => (
              <span key={title} className={i === step ? "chip" : "floor-chip"}>
                {i + 1}. {title}
              </span>
            ))}
          </div>

          {/* STEP 1 — guest snapshot (existing-guest pick autofills). */}
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
                <FormField label={t.reservations.form.documentType} htmlFor="res-doc-type">
                  <Select
                    id="res-doc-type"
                    value={docType}
                    placeholder={t.guests.documentTypes.none}
                    options={docTypeOptions}
                    onChange={(e) => setDocType(e.target.value)}
                  />
                </FormField>
                <FormField label={t.reservations.form.documentNumber} htmlFor="res-doc-num">
                  <Input id="res-doc-num" value={docNumber} onChange={(e) => setDocNumber(e.target.value)} />
                </FormField>
              </div>
            </SectionCard>
          ) : null}

          {/* STEP 2 — booking details, capacity-aware rooms, and review. */}
          {step === 1 ? (
            <>
              {frozen ? (
                <Alert tone="warning">
                  {v.inHouseFrozen}{" "}
                  <Link href="/hotel/front-desk?tab=current" className="btn btn--ghost btn--sm">
                    {v.goToFrontDesk}
                  </Link>
                </Alert>
              ) : null}

              <SectionCard title={t.reservations.form.sectionKindDates} icon={CalendarClock}>
                <div className="form-grid">
                  {editing ? (
                    <FormField
                      label={t.reservations.form.bookingKind}
                      htmlFor="res-kind"
                      hint={bookingKind === "instant" ? t.reservations.form.instantHint : t.reservations.form.futureHint}
                    >
                      <Select
                        id="res-kind"
                        value={bookingKind}
                        options={kindOptions}
                        disabled={frozen}
                        onChange={(e) => changeKind(e.target.value as "instant" | "future")}
                      />
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
                    <Input
                      id="res-in"
                      type="date"
                      value={checkIn}
                      required
                      disabled={bookingKind === "instant" || frozen}
                      onChange={(e) => setCheckIn(e.target.value)}
                    />
                  </FormField>
                  <FormField label={t.reservations.form.checkOut} htmlFor="res-out">
                    <Input id="res-out" type="date" value={checkOut} required disabled={frozen} onChange={(e) => setCheckOut(e.target.value)} />
                  </FormField>
                  <FormField label={t.reservations.form.nights} htmlFor="res-nights">
                    <Input id="res-nights" value={String(nights)} disabled readOnly />
                  </FormField>
                  <FormField label={t.reservations.form.arrivalTime} htmlFor="res-arrival">
                    <Input id="res-arrival" type="time" value={arrivalTime} onChange={(e) => setArrivalTime(e.target.value)} />
                  </FormField>
                </div>
              </SectionCard>

              <SectionCard title={t.reservations.form.sectionRooms} icon={BedDouble}>
                <div className="form-grid">
                  <FormField label={t.reservations.form.adults} htmlFor="res-adults">
                    <Input id="res-adults" type="number" min="1" value={adults} onChange={(e) => setAdults(e.target.value)} />
                  </FormField>
                  <FormField label={t.reservations.form.children} htmlFor="res-children">
                    <Input id="res-children" type="number" min="0" value={children} onChange={(e) => setChildren(e.target.value)} />
                  </FormField>
                </div>
                {isInstant ? <p className="muted small">{v.roomRequiredInstant}</p> : null}
                {frozen ? <p className="muted small">{v.inHouseFrozen}</p> : null}
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
                              disabled={frozen}
                              onChange={(e) => updateLine(i, { room_type: e.target.value })}
                            />
                          </FormField>
                          <FormField label={t.reservations.form.room} htmlFor={`line-room-${i}`} hint={t.reservations.form.roomHint}>
                            <Select
                              id={`line-room-${i}`}
                              value={line.room}
                              placeholder={t.reservations.form.roomAny}
                              options={roomOptionsFor(line.room_type)}
                              disabled={!line.room_type || frozen}
                              onChange={(e) => updateLine(i, { room: e.target.value })}
                            />
                          </FormField>
                          <FormField label={t.reservations.form.quantity} htmlFor={`line-qty-${i}`}>
                            <Input id={`line-qty-${i}`} type="number" min="1" value={line.quantity} disabled={Boolean(line.room) || frozen} onChange={(e) => updateLine(i, { quantity: e.target.value })} />
                          </FormField>
                          <Button type="button" variant="ghost" size="sm" icon={Trash2} onClick={() => removeLine(i)} disabled={lines.length === 1 || frozen}>
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
                  {!isInstant && !frozen ? (
                    <Button type="button" variant="secondary" size="sm" icon={Plus} onClick={addLine}>
                      {t.reservations.form.addLine}
                    </Button>
                  ) : null}
                </div>
                <p className="muted small">{t.reservations.form.availabilityHint}</p>
              </SectionCard>

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
                    value:
                      editing && reservation
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
// Renew-hold modal                                                            //
// --------------------------------------------------------------------------- //

/** Extend a held reservation's hold expiry (owner UX: kept off the primary
 * action row, in the card's overflow menu). Consumes the existing PATCH — the
 * backend still owns the state cycle. */
function RenewHoldModal({
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
  const [expires, setExpires] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setError(null);
    // Prefill with the current expiry (in the input's local format), if any.
    if (reservation?.hold_expires_at) {
      const d = new Date(reservation.hold_expires_at);
      const off = d.getTimezoneOffset();
      setExpires(new Date(d.getTime() - off * 60_000).toISOString().slice(0, 16));
    } else {
      setExpires("");
    }
  }, [open, reservation]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reservation) return;
    if (!expires) return setError(t.reservations.form.holdExpiryHint);
    setBusy(true);
    try {
      await updateReservation(reservation.id, {
        hold_expires_at: new Date(expires).toISOString(),
      });
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
      title={t.reservations.card.renewHoldTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="renew-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="renew-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="info">{t.reservations.card.renewHoldBody}</Alert>
        <FormField label={t.reservations.form.holdExpiry} htmlFor="renew-expires">
          <Input
            id="renew-expires"
            type="datetime-local"
            value={expires}
            required
            onChange={(e) => setExpires(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}
