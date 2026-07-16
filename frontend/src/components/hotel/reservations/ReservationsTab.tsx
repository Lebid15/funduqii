"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { useQuickAction } from "@/lib/useQuickAction";
import {
  CalendarCheck,
  Plus,
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
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  cancelReservation,
  confirmReservation,
  getReservation,
  getReservationFinancialSummary,
  getReservationOverview,
  listReservationDocuments,
  listReservations,
} from "@/lib/api/reservations";
import { listRoomTypes } from "@/lib/api/rooms";
import { getSettings } from "@/lib/api/hotel";
import { messageForError } from "@/lib/api/errors";
import type {
  Reservation,
  ReservationDocument,
  ReservationFinancialSummary,
  RoomType,
} from "@/lib/api/types";
import { reservationStatusLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { ReservationCard } from "./ReservationCard";
import { ReservationDetailsModal } from "./ReservationDetailsModal";
import { ReservationDocumentsModal } from "./ReservationDocumentsModal";
import { ReservationPrintPreview } from "./ReservationPrintPreview";
import {
  ReservationFormShell,
  createInitialDraft,
  reservationToDraft,
  type ReservationDraft,
} from "./wizard";
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
  refreshSignal = 0,
  onChanged,
}: {
  createSignal?: number;
  refreshSignal?: number;
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
  const [docsTarget, setDocsTarget] = useState<Reservation | null>(null);
  const [printTarget, setPrintTarget] = useState<Reservation | null>(null);
  const [printLoadingId, setPrintLoadingId] = useState<number | null>(null);

  // Printing opens the preview modal (which reads the reservation idempotently and
  // shows its own LoadingState). The card's printer icon shows a brief spinner
  // during the hand-off, released once the modal is open.
  const requestPrint = useCallback((target: Reservation) => {
    setPrintLoadingId(target.id);
    setPrintTarget(target);
  }, []);
  useEffect(() => {
    if (printTarget === null) {
      setPrintLoadingId(null);
      return;
    }
    const id = window.setTimeout(() => setPrintLoadingId(null), 0);
    return () => window.clearTimeout(id);
  }, [printTarget]);

  // The reservation form opens as a MODAL over this list (owner correction): the
  // create + edit actions set this local state to render `<ReservationFormShell>`
  // above the dimmed rows, rather than navigating to a full-screen page. Edit first
  // loads the reservation + documents + financial summary (as the edit route does)
  // so the wizard hydrates identically; `editLoading` covers that fetch.
  const [formState, setFormState] = useState<
    | { mode: "create"; initialDraft?: ReservationDraft }
    | {
        mode: "edit";
        reservation: Reservation;
        draft: ReservationDraft;
        financialSummary: ReservationFinancialSummary | null;
      }
    | null
  >(null);
  const [editLoading, setEditLoading] = useState(false);

  // The page's "New reservation" button pulses this prop — it opens the create
  // MODAL over this list (owner correction). Consume real increments only (the
  // initial value must not auto-open on mount).
  const lastSignal = useRef(createSignal);
  useEffect(() => {
    if (createSignal !== lastSignal.current) {
      lastSignal.current = createSignal;
      setFormState({ mode: "create" });
    }
  }, [createSignal]);

  function openCreate() {
    setFormState({ mode: "create" });
  }

  // Deep-links: ?action=new (topbar quick action / a room pinned from the rooms
  // board) opens the create MODAL over this list, seeding the pinned room. The
  // query is `replace`d away afterwards so the ?action= URL never lingers in
  // history (back/refresh won't re-open it). ?action=find&q= focuses the list.
  const actionParam = searchParams.get("action");
  const roomParam = searchParams.get("room");
  const roomTypeParam = searchParams.get("room_type");
  useEffect(() => {
    if (actionParam !== "new") return;
    let seed: ReservationDraft | undefined;
    if (roomParam && roomTypeParam) {
      seed = createInitialDraft();
      seed.booking.lines = [
        { room_type: roomTypeParam, room: roomParam, quantity: "1" },
      ];
      seed.booking.selected_room_id = Number(roomParam);
    }
    setFormState({ mode: "create", initialDraft: seed });
    router.replace("/hotel/reservations");
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

  // The page pulses `refreshSignal` when the operator returns to this tab
  // (visibilitychange). Refetch the list + overview WITHOUT remounting — filters,
  // pagination, open modals and the in-progress create/edit wizard all survive.
  // Consume real increments only (the initial value must not refetch on mount).
  const lastRefreshSignal = useRef(refreshSignal);
  useEffect(() => {
    if (refreshSignal !== lastRefreshSignal.current) {
      lastRefreshSignal.current = refreshSignal;
      refresh();
    }
  }, [refreshSignal, refresh]);

  // Edit opens the SAME wizard shell as a modal — but first loads the full
  // reservation, its documents and its derived financial summary IN PARALLEL
  // (identical to the /[id]/edit route), degrading gracefully when a supplementary
  // read is not permitted. The reservation fetch is the only hard dependency.
  const openEdit = useCallback(
    async (target: Reservation) => {
      setEditLoading(true);
      try {
        const [reservation, documents, financialSummary] = await Promise.all([
          getReservation(target.id),
          listReservationDocuments(target.id).catch(
            () => [] as ReservationDocument[],
          ),
          getReservationFinancialSummary(target.id).catch(
            () => null as ReservationFinancialSummary | null,
          ),
        ]);
        setFormState({
          mode: "edit",
          reservation,
          draft: reservationToDraft(reservation, { documents }),
          financialSummary,
        });
      } catch (err) {
        notify(messageForError(err, t), "error");
      } finally {
        setEditLoading(false);
      }
    },
    [notify, t],
  );

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
                    printLoading={printLoadingId === r.id}
                    onView={setDetails}
                    onPrint={requestPrint}
                    onDocuments={setDocsTarget}
                    onConfirm={confirm}
                    onEdit={() => openEdit(r)}
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

      {/* Create + edit open as a centered MODAL over this list (owner correction).
          The deep-link routes /new and /[id]/edit render the same shell standalone.
          A brief loading overlay covers the edit fetch before the wizard mounts. */}
      {editLoading && typeof document !== "undefined"
        ? createPortal(
            <div className="resform-overlay" role="presentation">
              <LoadingState label={t.common.loading} />
            </div>,
            document.body,
          )
        : null}
      {formState ? (
        <ReservationFormShell
          mode={formState.mode}
          reservation={
            formState.mode === "edit" ? formState.reservation : undefined
          }
          initialDraft={
            formState.mode === "edit" ? formState.draft : formState.initialDraft
          }
          financialSummary={
            formState.mode === "edit" ? formState.financialSummary : undefined
          }
          onClose={() => setFormState(null)}
          onSaved={refresh}
          onViewReservation={(r) => {
            setFormState(null);
            setDetails(r);
          }}
        />
      ) : null}

      <ReservationDetailsModal
        open={details !== null}
        reservation={details ?? undefined}
        onClose={() => setDetails(null)}
        onEdit={(r) => {
          setDetails(null);
          openEdit(r);
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
      <ReservationDocumentsModal
        open={docsTarget !== null}
        reservation={docsTarget ?? undefined}
        onClose={() => setDocsTarget(null)}
      />
      <ReservationPrintPreview
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
