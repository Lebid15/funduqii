"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeftRight,
  CalendarClock,
  CalendarMinus,
  CalendarPlus,
  Check,
  Clock,
  Coins,
  DoorOpen,
  FileText,
  LogOut,
  PlaneLanding,
  PlaneTakeoff,
  Plus,
  Printer,
  Star,
  Undo2,
  Users,
  Wallet,
} from "lucide-react";

import {
  ActionCard,
  Alert,
  Badge,
  Button,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  PaymentStatusBadge,
  SectionHeader,
  Select,
  Tabs,
  Textarea,
  useToast,
  type TabItem,
} from "@/components/ui";
import {
  checkIn,
  checkOut,
  ensureRoomCharges,
  extendStay,
  getStayFolioSummary,
  getStayLogs,
  getStaysOverview,
  listArrivalsToday,
  listCheckInRooms,
  listCurrentResidents,
  listDeparturesToday,
  listMoveCandidates,
  moveStayRoom,
  remediateStayRate,
  reverseCheckIn,
  shortenStay,
} from "@/lib/api/stays";
import type { StaysOverview } from "@/lib/api/stays";
import { StaysSummaryCards, type OpsCardKey } from "./StaysSummaryCards";
import { StayRegistrationPrintModal, StayStatementPrintModal } from "./StayPrints";
import {
  deductInsurance,
  refundFolioCredit,
  refundInsurance,
  setFolioAwaitingCharges,
  settleFolio,
} from "@/lib/api/finance";
import { createGuest, listGuests } from "@/lib/api/guests";
import { getReservation, markNoShow } from "@/lib/api/reservations";
import { ReservationDocumentsModal } from "@/components/hotel/reservations/ReservationDocumentsModal";
import { messageForError } from "@/lib/api/errors";
import type {
  AdmissibleRoom,
  Guest,
  Reservation,
  Stay,
  StayFolioCardSummary,
  StayFolioSummary,
  StayStatusLogEntry,
} from "@/lib/api/types";
import { formatDate, formatDateTime, formatMoney, stayStatusLabel, stayStatusTone } from "@/lib/format";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useI18n } from "@/lib/i18n/I18nProvider";

const TAB_KEYS = ["arrivals", "current", "departures"];

/** yyyy-mm-dd + n days (local, date-only). */
function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  const pad = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Cosmetic permission gate — every API re-checks server-side regardless. */
function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

/**
 * Operational-card finance block (§12). Renders the folio total / paid /
 * remaining plus the CENTRAL PaymentStatusBadge — status and amounts come
 * straight from the folio ledger (backend), never recomputed here. An
 * awaiting-final-charges operational badge is shown as a distinct signal.
 * Renders nothing when the viewer lacks `finance.view` (backend nulls it).
 */
function FolioCardSummary({
  folio,
  requiresRemediation = false,
}: {
  folio: StayFolioCardSummary | null | undefined;
  requiresRemediation?: boolean;
}) {
  const { t, locale } = useI18n();
  // STAYS rate-integrity — a "stuck" stay (a consumed night with no agreed rate).
  // Show the OPERATIONAL badge (not finance-gated) and NEVER a settled/zero amount:
  // the folio total would understate the real balance, so the money rows and the
  // clearance chip are both suppressed until a rate is set.
  if (requiresRemediation) {
    const rr = t.frontDesk.rateRemediation;
    return (
      <div className="stack" style={{ gap: "0.35rem" }}>
        <div className="cluster" style={{ gap: "0.35rem" }}>
          <Badge tone="danger" icon={AlertTriangle}>{rr.badge}</Badge>
        </div>
        <span className="muted small">{rr.amountPending}</span>
      </div>
    );
  }
  if (!folio) return null;
  const f = t.frontDesk.finance;
  // Non-finance viewer: the backend sends NO amounts — render an operational
  // clearance chip (icon + label, never colour alone) plus a muted permission
  // note. Never print `0`/empty for a hidden amount and never the money rows.
  if (!folio.financial_details_visible) {
    const cleared = folio.financial_clearance_complete;
    return (
      <div className="stack" style={{ gap: "0.35rem" }}>
        <div className="cluster" style={{ gap: "0.35rem" }}>
          <Badge tone={cleared ? "success" : "warning"} icon={cleared ? Check : Clock}>
            {cleared ? f.clearanceComplete : f.clearancePending}
          </Badge>
        </div>
        <span className="muted small">{f.detailsHidden}</span>
      </div>
    );
  }
  return (
    <div className="stack" style={{ gap: "0.35rem" }}>
      <div className="cluster" style={{ gap: "0.35rem" }}>
        <PaymentStatusBadge status={folio.payment_status} labels={f.status} />
        {folio.awaiting_final_charges ? <Badge tone="warning">{f.awaiting}</Badge> : null}
      </div>
      <div className="stay-card__meta">
        <span>{f.total}: {formatMoney(folio.total_charges, folio.currency, locale)}</span>
        <span>{f.paid}: {formatMoney(folio.total_payments, folio.currency, locale)}</span>
        <span>{f.remaining}: {formatMoney(folio.balance, folio.currency, locale)}</span>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Search & filters (§7) — deliberately short: one search box (guest / phone / //
// reservation / stay / room) + a payment-status filter + a clear button.      //
// Applied client-side over the current tab's daily list.                      //
// --------------------------------------------------------------------------- //

interface BoardFilters {
  q: string;
  payment: string;
}

function hay(...parts: (string | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ").toLowerCase();
}

function reservationMatches(res: Reservation, filters: BoardFilters): boolean {
  if (filters.payment && res.payment_status !== filters.payment) return false;
  const q = filters.q.trim().toLowerCase();
  if (!q) return true;
  return hay(
    res.reservation_number,
    res.primary_guest_name,
    res.primary_guest_phone,
    ...res.lines.map((l) => l.room_number),
  ).includes(q);
}

function stayMatches(stay: Stay, filters: BoardFilters): boolean {
  if (filters.payment) {
    // payment_status exists only on the finance-visible variant; a non-finance
    // viewer never has it (and the payment filter is hidden for them anyway).
    const fs = stay.folio_summary;
    const status = fs && fs.financial_details_visible ? fs.payment_status : undefined;
    if (status !== filters.payment) return false;
  }
  const q = filters.q.trim().toLowerCase();
  if (!q) return true;
  return hay(stay.room_number, stay.primary_guest_name, stay.reservation_number).includes(q);
}

function FrontDeskFilters({
  filters,
  onChange,
}: {
  filters: BoardFilters;
  onChange: (next: BoardFilters) => void;
}) {
  const { t } = useI18n();
  const can = useCan();
  const f = t.frontDesk.filters;
  const s = t.frontDesk.finance.status;
  // The payment filter reads folio_summary.payment_status, which exists only on
  // the finance-visible variant of folio_summary (financial_details_visible:
  // true). A viewer without finance.view instead receives the HIDDEN variant
  // (financial_details_visible: false) that omits payment_status entirely, so the
  // filter would match nothing and silently empty the list — hence it is hidden.
  const showPayment = can("finance.view");
  const paymentOptions = [
    { value: "", label: f.allPayments },
    { value: "paid", label: s.paid },
    { value: "partial", label: s.partial },
    { value: "unpaid", label: s.unpaid },
    { value: "overpaid", label: s.overpaid },
  ];
  const active = filters.q.trim() !== "" || filters.payment !== "";
  return (
    <div className="cluster" style={{ gap: "0.5rem", alignItems: "flex-end", flexWrap: "wrap", marginBlock: "0.75rem" }}>
      <FormField label={f.search} htmlFor="fd-search">
        <Input
          id="fd-search"
          value={filters.q}
          placeholder={f.searchPlaceholder}
          onChange={(e) => onChange({ ...filters, q: e.target.value })}
        />
      </FormField>
      {showPayment ? (
        <FormField label={f.payment} htmlFor="fd-payment">
          <Select
            id="fd-payment"
            value={filters.payment}
            options={paymentOptions}
            onChange={(e) => onChange({ ...filters, payment: e.target.value })}
          />
        </FormField>
      ) : null}
      {active ? (
        <Button variant="ghost" size="sm" onClick={() => onChange({ q: "", payment: "" })}>{f.clear}</Button>
      ) : null}
    </div>
  );
}

export function FrontDeskPanel() {
  const { t } = useI18n();
  // Deep-linkable tab (?tab=departures — the topbar quick actions): initial
  // read + follow URL changes so a quick action fired while ALREADY on this
  // page still lands on its tab. Manual tab clicks stay local as before.
  const searchParams = useSearchParams();
  const requested = searchParams.get("tab");
  const search = searchParams.toString();
  const [tab, setTab] = useState(
    requested && TAB_KEYS.includes(requested) ? requested : "arrivals",
  );
  useEffect(() => {
    if (requested && TAB_KEYS.includes(requested)) setTab(requested);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- URL is the trigger
  }, [search]);
  const [reloadKey, setReloadKey] = useState(0);
  const refresh = () => setReloadKey((k) => k + 1);
  const [overview, setOverview] = useState<StaysOverview | null>(null);
  const [activeCard, setActiveCard] = useState<OpsCardKey | null>(null);
  const [filters, setFilters] = useState<BoardFilters>({ q: "", payment: "" });

  useEffect(() => {
    let stale = false;
    getStaysOverview()
      .then((o) => {
        if (!stale) setOverview(o);
      })
      .catch(() => {
        if (!stale) setOverview(null);
      });
    return () => {
      stale = true;
    };
  }, [reloadKey]);

  // §6 — clicking a card applies its filter. Until per-state filtered lists
  // land, each card maps to the tab that shows its guests.
  const CARD_TAB: Record<OpsCardKey, string> = {
    arriving: "arrivals",
    awaiting: "arrivals",
    checked_in_today: "current",
    residents: "current",
    departing: "departures",
    attention: "current",
  };
  const handleCardSelect = (card: OpsCardKey) => {
    setActiveCard(card);
    setTab(CARD_TAB[card]);
  };

  const tabs: TabItem[] = [
    { key: "arrivals", label: t.frontDesk.tabs.arrivals, icon: PlaneLanding },
    { key: "current", label: t.frontDesk.tabs.current, icon: DoorOpen },
    { key: "departures", label: t.frontDesk.tabs.departures, icon: LogOut },
  ];

  return (
    <>
      <StaysSummaryCards
        overview={overview}
        active={activeCard}
        onSelect={handleCardSelect}
      />
      <Tabs tabs={tabs} active={tab} onChange={(k) => { setTab(k); setActiveCard(null); }} />
      <FrontDeskFilters filters={filters} onChange={setFilters} />
      {tab === "arrivals" ? <ArrivalsTab reloadKey={reloadKey} onChange={refresh} filters={filters} /> : null}
      {tab === "current" ? <CurrentTab reloadKey={reloadKey} onChange={refresh} filters={filters} businessDate={overview?.business_date ?? null} /> : null}
      {tab === "departures" ? <DeparturesTab reloadKey={reloadKey} onChange={refresh} filters={filters} /> : null}
    </>
  );
}

// --------------------------------------------------------------------------- //
// Arrivals today                                                              //
// --------------------------------------------------------------------------- //

function ArrivalsTab({ reloadKey, onChange, filters }: { reloadKey: number; onChange: () => void; filters: BoardFilters }) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const [rows, setRows] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<Reservation | null>(null);
  const [noShowTarget, setNoShowTarget] = useState<Reservation | null>(null);
  const [docsRes, setDocsRes] = useState<Reservation | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await listArrivalsToday());
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load, reloadKey]);

  if (loading) return <LoadingState label={t.common.loading} />;
  if (error) return <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} />;
  if (rows.length === 0) {
    return <EmptyState title={t.frontDesk.arrivals.empty} hint={t.frontDesk.arrivals.emptyHint} icon={PlaneLanding} />;
  }

  const visible = rows.filter((res) => reservationMatches(res, filters));

  return (
    <>
      <SectionHeader title={t.frontDesk.tabs.arrivals} icon={PlaneLanding} />
      {visible.length === 0 ? (
        <EmptyState title={t.frontDesk.filters.noMatches} hint={t.frontDesk.filters.noMatchesHint} icon={PlaneLanding} />
      ) : null}
      <div className="stack">
        {visible.map((res) => (
          <ActionCard
            key={res.id}
            icon={PlaneLanding}
            title={`${res.reservation_number} · ${res.primary_guest_name}`}
            description={`${formatDate(res.check_in_date, locale)} → ${formatDate(res.check_out_date, locale)} · ${res.lines.map((l) => `${l.quantity}× ${l.room_type_name}${l.room_number ? ` (${l.room_number})` : ""}`).join(", ")}`}
            action={
              <div className="cluster">
                {can("reservation_documents.view") && res.document_count > 0 ? (
                  <Button variant="ghost" size="sm" icon={FileText} onClick={() => setDocsRes(res)}>
                    {t.frontDesk.documents}
                  </Button>
                ) : null}
                {can("stays.check_in") ? (
                  <Button icon={DoorOpen} size="sm" onClick={() => setTarget(res)}>
                    {t.frontDesk.arrivals.checkIn}
                  </Button>
                ) : null}
                {can("reservations.mark_no_show") ? (
                  <Button variant="ghost" size="sm" onClick={() => setNoShowTarget(res)}>
                    {t.frontDesk.arrivals.noShow}
                  </Button>
                ) : null}
              </div>
            }
          />
        ))}
      </div>
      <CheckInModal
        reservation={target}
        onClose={() => setTarget(null)}
        onDone={() => { setTarget(null); notify(t.frontDesk.saved); onChange(); }}
      />
      <NoShowModal
        reservation={noShowTarget}
        onClose={() => setNoShowTarget(null)}
        onDone={() => { setNoShowTarget(null); notify(t.frontDesk.saved); onChange(); }}
      />
      <ReservationDocumentsModal
        open={docsRes !== null}
        reservation={docsRes ?? undefined}
        onClose={() => setDocsRes(null)}
      />
    </>
  );
}

function NoShowModal({
  reservation,
  onClose,
  onDone,
}: {
  reservation: Reservation | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setReason("");
    setError(null);
  }, [reservation]);
  if (!reservation) return null;
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await markNoShow(reservation.id, reason);
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title={t.frontDesk.arrivals.noShowTitle}
      closeLabel={t.common.close}
    >
      <div className="stack">
        <p className="muted">{t.frontDesk.arrivals.noShowHint}</p>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField
          label={t.frontDesk.arrivals.noShowReason}
          htmlFor="no-show-reason"
        >
          <Textarea
            id="no-show-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
          />
        </FormField>
        <div className="cluster cluster--end">
          <Button variant="ghost" onClick={onClose}>
            {t.common.cancel}
          </Button>
          <Button
            variant="danger"
            disabled={busy || !reason.trim()}
            onClick={submit}
          >
            {t.frontDesk.arrivals.noShowConfirm}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function ReverseCheckInModal({
  stay,
  onClose,
  onDone,
}: {
  stay: Stay | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setReason("");
    setError(null);
  }, [stay]);
  if (!stay) return null;
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await reverseCheckIn(stay.id, { reason });
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open
      onClose={onClose}
      title={t.frontDesk.current.reverseTitle}
      closeLabel={t.common.close}
    >
      <div className="stack">
        <p className="muted">{t.frontDesk.current.reverseHint}</p>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField
          label={t.frontDesk.current.reverseReason}
          htmlFor="reverse-reason"
        >
          <Textarea
            id="reverse-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
          />
        </FormField>
        <div className="cluster cluster--end">
          <Button variant="ghost" onClick={onClose}>
            {t.common.cancel}
          </Button>
          <Button
            variant="danger"
            disabled={busy || !reason.trim()}
            onClick={submit}
          >
            {t.frontDesk.current.reverseConfirm}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// Current residents                                                           //
// --------------------------------------------------------------------------- //

function CurrentTab({ reloadKey, onChange, filters, businessDate }: { reloadKey: number; onChange: () => void; filters: BoardFilters; businessDate: string | null }) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const [rows, setRows] = useState<Stay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [details, setDetails] = useState<Stay | null>(null);
  const [checkoutTarget, setCheckoutTarget] = useState<Stay | null>(null);
  const [extendTarget, setExtendTarget] = useState<Stay | null>(null);
  const [shortenTarget, setShortenTarget] = useState<Stay | null>(null);
  const [moveTarget, setMoveTarget] = useState<Stay | null>(null);
  const [reverseTarget, setReverseTarget] = useState<Stay | null>(null);
  const [remediateTarget, setRemediateTarget] = useState<Stay | null>(null);
  const [docsRes, setDocsRes] = useState<Reservation | null>(null);
  const [docsBusy, setDocsBusy] = useState<number | null>(null);

  const openDocs = async (stay: Stay) => {
    if (stay.reservation === null) return;
    setDocsBusy(stay.id);
    try {
      setDocsRes(await getReservation(stay.reservation));
    } catch (err) {
      notify(messageForError(err, t));
    } finally {
      setDocsBusy(null);
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows((await listCurrentResidents()).results);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load, reloadKey]);

  if (loading) return <LoadingState label={t.common.loading} />;
  if (error) return <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} />;
  if (rows.length === 0) {
    return <EmptyState title={t.frontDesk.current.empty} hint={t.frontDesk.current.emptyHint} icon={DoorOpen} />;
  }

  const done = (setter: (s: Stay | null) => void) => () => {
    setter(null);
    notify(t.frontDesk.saved);
    onChange();
  };

  const visible = rows.filter((stay) => stayMatches(stay, filters));

  return (
    <>
      <SectionHeader title={t.frontDesk.tabs.current} icon={DoorOpen} />
      {visible.length === 0 ? (
        <EmptyState title={t.frontDesk.filters.noMatches} hint={t.frontDesk.filters.noMatchesHint} icon={DoorOpen} />
      ) : null}
      <div className="stay-grid">
        {visible.map((stay) => {
          // Overstay = past the planned check-out against the HOTEL business
          // date (both are yyyy-mm-dd, so a lexicographic compare is exact).
          // Display only — nothing is billed or re-dated on the client.
          const overstay = businessDate !== null && stay.planned_check_out_date < businessDate;
          return (
          <article className="stay-card" key={stay.id}>
            <div className="stay-card__head">
              <span className="stay-card__room">{stay.room_number}</span>
              <span className="cluster" style={{ gap: "0.35rem" }}>
                {stay.primary_guest_is_vip ? (
                  <Badge tone="warning"><Star size={12} aria-hidden /> {t.guests.vip.badge}</Badge>
                ) : null}
                {overstay ? (
                  <Badge tone="danger" icon={CalendarClock}>{t.frontDesk.current.overstay}</Badge>
                ) : null}
                <Badge tone={stayStatusTone(stay.status)}>{stayStatusLabel(stay.status, t)}</Badge>
              </span>
            </div>
            <div className="stay-card__meta">
              <span><Users size={14} aria-hidden /> {stay.primary_guest_name}</span>
              <span>{t.frontDesk.current.checkInDate}: {formatDate(stay.actual_check_in_at, locale)}</span>
              <span>{t.frontDesk.current.checkOutDate}: {formatDate(stay.planned_check_out_date, locale)} · {stay.nights} {t.frontDesk.current.nights}</span>
            </div>
            <FolioCardSummary folio={stay.folio_summary} requiresRemediation={stay.requires_rate_remediation} />
            <div className="stay-card__actions">
              {stay.requires_rate_remediation && can("stays.rate_override") ? (
                // STAYS rate-integrity — only a `stays.rate_override` holder can set
                // the missing agreed rate; the backend re-checks the permission.
                <Button variant="primary" size="sm" icon={Coins} onClick={() => setRemediateTarget(stay)}>{t.frontDesk.rateRemediation.setRate}</Button>
              ) : null}
              {can("reservation_documents.view") && stay.document_count > 0 ? (
                <Button variant="ghost" size="sm" icon={FileText} loading={docsBusy === stay.id} onClick={() => openDocs(stay)}>{t.frontDesk.documents}</Button>
              ) : null}
              <Button variant="secondary" size="sm" onClick={() => setDetails(stay)}>{t.frontDesk.current.details}</Button>
              {can("stays.extend") ? (
                // An overstay makes the extend action prominent (primary), so the
                // agent can resolve the overdue stay without a new action.
                <Button variant={overstay ? "primary" : "ghost"} size="sm" icon={CalendarPlus} onClick={() => setExtendTarget(stay)}>{t.frontDesk.current.extend}</Button>
              ) : null}
              {can("stays.shorten") ? (
                <Button variant="ghost" size="sm" icon={CalendarMinus} onClick={() => setShortenTarget(stay)}>{t.frontDesk.current.shorten}</Button>
              ) : null}
              {can("stays.move_room") ? (
                <Button variant="ghost" size="sm" icon={ArrowLeftRight} onClick={() => setMoveTarget(stay)}>{t.frontDesk.current.move}</Button>
              ) : null}
              {can("stays.check_out") ? (
                <Button variant="ghost" size="sm" icon={LogOut} onClick={() => setCheckoutTarget(stay)}>{t.frontDesk.current.checkOut}</Button>
              ) : null}
              {can("stays.reverse_check_in") ? (
                <Button variant="ghost" size="sm" icon={Undo2} onClick={() => setReverseTarget(stay)}>{t.frontDesk.current.reverse}</Button>
              ) : null}
            </div>
          </article>
          );
        })}
      </div>
      <StayDetailsModal stay={details} onClose={() => setDetails(null)} />
      <ReservationDocumentsModal
        open={docsRes !== null}
        reservation={docsRes ?? undefined}
        onClose={() => setDocsRes(null)}
      />
      <CheckOutModal
        stay={checkoutTarget}
        onClose={() => setCheckoutTarget(null)}
        onDone={done(setCheckoutTarget)}
      />
      <ExtendStayModal
        stay={extendTarget}
        onClose={() => setExtendTarget(null)}
        onDone={done(setExtendTarget)}
      />
      <ReverseCheckInModal
        stay={reverseTarget}
        onClose={() => setReverseTarget(null)}
        onDone={done(setReverseTarget)}
      />
      <ShortenStayModal
        stay={shortenTarget}
        onClose={() => setShortenTarget(null)}
        onDone={done(setShortenTarget)}
      />
      <MoveRoomModal
        stay={moveTarget}
        onClose={() => setMoveTarget(null)}
        onDone={done(setMoveTarget)}
      />
      <RemediateRateModal
        stay={remediateTarget}
        onClose={() => setRemediateTarget(null)}
        onDone={done(setRemediateTarget)}
      />
    </>
  );
}

// --------------------------------------------------------------------------- //
// Departures today                                                            //
// --------------------------------------------------------------------------- //

function DeparturesTab({ reloadKey, onChange, filters }: { reloadKey: number; onChange: () => void; filters: BoardFilters }) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const [rows, setRows] = useState<Stay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [checkoutTarget, setCheckoutTarget] = useState<Stay | null>(null);
  const [remediateTarget, setRemediateTarget] = useState<Stay | null>(null);
  const [docsRes, setDocsRes] = useState<Reservation | null>(null);
  const [docsBusy, setDocsBusy] = useState<number | null>(null);

  const openDocs = async (stay: Stay) => {
    if (stay.reservation === null) return;
    setDocsBusy(stay.id);
    try {
      setDocsRes(await getReservation(stay.reservation));
    } catch (err) {
      notify(messageForError(err, t));
    } finally {
      setDocsBusy(null);
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows((await listDeparturesToday()).results);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load, reloadKey]);

  if (loading) return <LoadingState label={t.common.loading} />;
  if (error) return <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} />;
  if (rows.length === 0) {
    return <EmptyState title={t.frontDesk.departures.empty} hint={t.frontDesk.departures.emptyHint} icon={LogOut} />;
  }

  const visible = rows.filter((stay) => stayMatches(stay, filters));

  return (
    <>
      <SectionHeader title={t.frontDesk.tabs.departures} icon={LogOut} />
      {visible.length === 0 ? (
        <EmptyState title={t.frontDesk.filters.noMatches} hint={t.frontDesk.filters.noMatchesHint} icon={LogOut} />
      ) : null}
      <div className="stack">
        {visible.map((stay) => (
          <ActionCard
            key={stay.id}
            icon={PlaneTakeoff}
            title={`${stay.room_number} · ${stay.primary_guest_name}`}
            description={`${formatDate(stay.actual_check_in_at, locale)} → ${formatDate(stay.planned_check_out_date, locale)}`}
            meta={<FolioCardSummary folio={stay.folio_summary} requiresRemediation={stay.requires_rate_remediation} />}
            action={
              <div className="cluster">
                {stay.requires_rate_remediation && can("stays.rate_override") ? (
                  <Button variant="primary" size="sm" icon={Coins} onClick={() => setRemediateTarget(stay)}>{t.frontDesk.rateRemediation.setRate}</Button>
                ) : null}
                {can("reservation_documents.view") && stay.document_count > 0 ? (
                  <Button variant="ghost" size="sm" icon={FileText} loading={docsBusy === stay.id} onClick={() => openDocs(stay)}>{t.frontDesk.documents}</Button>
                ) : null}
                {can("stays.check_out") ? (
                  <Button icon={LogOut} onClick={() => setCheckoutTarget(stay)}>{t.frontDesk.current.checkOut}</Button>
                ) : null}
              </div>
            }
          />
        ))}
      </div>
      <CheckOutModal
        stay={checkoutTarget}
        onClose={() => setCheckoutTarget(null)}
        onDone={() => { setCheckoutTarget(null); notify(t.frontDesk.saved); onChange(); }}
      />
      <RemediateRateModal
        stay={remediateTarget}
        onClose={() => setRemediateTarget(null)}
        onDone={() => { setRemediateTarget(null); notify(t.frontDesk.saved); onChange(); }}
      />
      <ReservationDocumentsModal
        open={docsRes !== null}
        reservation={docsRes ?? undefined}
        onClose={() => setDocsRes(null)}
      />
    </>
  );
}

// --------------------------------------------------------------------------- //
// Check-in modal                                                              //
// --------------------------------------------------------------------------- //

function CheckInModal({
  reservation,
  onClose,
  onDone,
}: {
  reservation: Reservation | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t, locale } = useI18n();
  const ci = t.frontDesk.checkInModal;
  const [lineId, setLineId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [guestId, setGuestId] = useState("");
  const [companions, setCompanions] = useState<number[]>([]);
  const [companionPick, setCompanionPick] = useState("");
  const [notes, setNotes] = useState("");
  const [guests, setGuests] = useState<Guest[]>([]);
  const [rooms, setRooms] = useState<AdmissibleRoom[]>([]);
  const [quickName, setQuickName] = useState("");
  const [quickPhone, setQuickPhone] = useState("");
  const [showQuick, setShowQuick] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Stay | null>(null);
  const [resultFolio, setResultFolio] = useState<StayFolioSummary | null>(null);
  const [printReg, setPrintReg] = useState(false);

  const open = reservation !== null;
  const line = reservation?.lines.find((l) => String(l.id) === lineId) ?? reservation?.lines[0];

  useEffect(() => {
    if (!open || !reservation) return;
    const first = reservation.lines[0];
    setLineId(first ? String(first.id) : "");
    setRoomId(first?.room ? String(first.room) : "");
    setGuestId("");
    setCompanions([]);
    setCompanionPick("");
    setNotes("");
    setError(null);
    setShowQuick(false);
    setQuickName("");
    setQuickPhone("");
    setResult(null);
    setResultFolio(null);
    setPrintReg(false);
    listGuests({ page_size: 200, is_active: "true" }).then((r) => setGuests(r.results)).catch(() => setGuests([]));
  }, [open, reservation]);

  // Load the rooms ACTUALLY admissible for the selected line (unless pinned):
  // derived occupancy and conflicting reservations are already excluded.
  useEffect(() => {
    if (!open || !line || !reservation) return;
    if (line.room) {
      setRoomId(String(line.room));
      setRooms([]);
      return;
    }
    setRoomId("");
    listCheckInRooms(reservation.id, line.id)
      .then(setRooms)
      .catch(() => setRooms([]));
  }, [open, lineId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function quickAdd() {
    if (!quickName.trim()) return;
    try {
      const g = await createGuest({ full_name: quickName.trim(), phone: quickPhone.trim() });
      setGuests((prev) => [g, ...prev]);
      setGuestId(String(g.id));
      setShowQuick(false);
      setQuickName("");
      setQuickPhone("");
    } catch (err) {
      setError(messageForError(err, t));
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reservation || !line) return;
    setError(null);
    const room = line.room ?? (roomId ? Number(roomId) : null);
    if (!room) return setError(t.frontDesk.checkInModal.roomRequired);
    if (!guestId) return setError(t.frontDesk.checkInModal.guestRequired);
    setBusy(true);
    try {
      const stay = await checkIn({
        reservation: reservation.id,
        reservation_line: line.id,
        room,
        primary_guest: Number(guestId),
        companions,
        check_in_notes: notes.trim(),
      });
      // §19 — don't vanish without a result. Surface the created stay + its
      // folio state on a success screen; the parent list refreshes on close.
      setResult(stay);
      getStayFolioSummary(stay.id).then(setResultFolio).catch(() => setResultFolio(null));
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const lineOptions = (reservation?.lines ?? []).map((l) => ({
    value: String(l.id),
    label: `${l.room_type_name}${l.room_number ? ` · ${l.room_number}` : ""}`,
  }));
  const guestOptions = guests.map((g) => ({ value: String(g.id), label: g.full_name }));
  const roomOptions = rooms.map((r) => ({ value: String(r.id), label: r.number }));
  const companionOptions = guestOptions.filter(
    (o) => o.value !== guestId && !companions.includes(Number(o.value)),
  );

  if (result) {
    // Amounts (and the money-bearing registration print) are shown only to a
    // finance viewer; a non-finance viewer receives no monetary fields at all.
    const finFolio = resultFolio && resultFolio.financial_details_visible ? resultFolio : null;
    const folioCurrency = finFolio?.open_folios[0]?.currency ?? "";
    const folioId = finFolio?.open_folios[0]?.id ?? null;
    return (
      <Modal
        open={open}
        onClose={onDone}
        title={ci.title}
        closeLabel={t.common.close}
        footer={
          <>
            {folioId !== null ? (
              <Button variant="secondary" icon={Printer} onClick={() => setPrintReg(true)}>{ci.successPrint}</Button>
            ) : null}
            <Button onClick={onDone}>{ci.successDone}</Button>
          </>
        }
      >
        <div className="stack" role="status">
          <Alert tone="success">{ci.successHeading}</Alert>
          <dl className="detail-grid">
            <div><dt>{ci.successGuest}</dt><dd>{result.primary_guest_name}</dd></div>
            <div><dt>{ci.successRoom}</dt><dd>{result.room_number}</dd></div>
            <div><dt>{ci.reservation}</dt><dd>{result.reservation_number ?? "—"}</dd></div>
            <div><dt>{ci.successCheckInTime}</dt><dd>{formatDateTime(result.actual_check_in_at, locale)}</dd></div>
            {finFolio ? (
              <div>
                <dt>{ci.successFolio}</dt>
                <dd>{formatMoney(finFolio.balance, folioCurrency, locale)}</dd>
              </div>
            ) : null}
          </dl>
          <Alert tone="info">{ci.successHint}</Alert>
        </div>
        <StayRegistrationPrintModal
          open={printReg}
          stay={result}
          folioId={folioId}
          onClose={() => setPrintReg(false)}
        />
      </Modal>
    );
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={ci.title}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="checkin-form" type="submit" loading={busy}>{ci.submit}</Button>
        </>
      }
    >
      <form id="checkin-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="detail-grid">
          <div><dt>{t.frontDesk.checkInModal.reservation}</dt><dd>{reservation?.reservation_number}</dd></div>
        </div>
        {lineOptions.length > 1 ? (
          <FormField label={t.frontDesk.checkInModal.roomType} htmlFor="ci-line">
            <Select id="ci-line" value={lineId} options={lineOptions} onChange={(e) => setLineId(e.target.value)} />
          </FormField>
        ) : null}
        {line?.room ? (
          <FormField label={t.frontDesk.checkInModal.roomAssigned} htmlFor="ci-room-fixed">
            <Input id="ci-room-fixed" value={line.room_number ?? ""} disabled readOnly />
          </FormField>
        ) : (
          <FormField label={t.frontDesk.checkInModal.room} htmlFor="ci-room">
            <Select id="ci-room" value={roomId} placeholder={rooms.length ? t.frontDesk.checkInModal.selectRoom : t.frontDesk.checkInModal.noRooms} options={roomOptions} onChange={(e) => setRoomId(e.target.value)} />
          </FormField>
        )}
        <FormField label={t.frontDesk.checkInModal.primaryGuest} htmlFor="ci-guest">
          <Select id="ci-guest" value={guestId} placeholder={t.frontDesk.checkInModal.selectGuest} options={guestOptions} onChange={(e) => setGuestId(e.target.value)} />
        </FormField>
        {showQuick ? (
          <div className="line-row" onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); quickAdd(); } }}>
            <FormField label={t.guests.form.fullName} htmlFor="ci-qname">
              <Input id="ci-qname" value={quickName} onChange={(e) => setQuickName(e.target.value)} />
            </FormField>
            <FormField label={t.guests.form.phone} htmlFor="ci-qphone">
              <Input id="ci-qphone" value={quickPhone} onChange={(e) => setQuickPhone(e.target.value)} />
            </FormField>
            <Button type="button" size="sm" onClick={quickAdd}>{t.common.save}</Button>
          </div>
        ) : (
          <Button type="button" variant="ghost" size="sm" icon={Plus} onClick={() => setShowQuick(true)}>{t.guests.list.add}</Button>
        )}
        <FormField label={t.frontDesk.checkInModal.companions} htmlFor="ci-comp">
          <Select
            id="ci-comp"
            value={companionPick}
            placeholder={t.frontDesk.checkInModal.companions}
            options={companionOptions}
            onChange={(e) => {
              const id = Number(e.target.value);
              if (id) setCompanions((prev) => [...prev, id]);
              setCompanionPick("");
            }}
          />
        </FormField>
        {companions.length > 0 ? (
          <div className="cluster">
            {companions.map((id) => {
              const g = guests.find((x) => x.id === id);
              return (
                <Badge key={id} tone="info">
                  {g?.full_name ?? id}{" "}
                  <button type="button" className="chip-remove" onClick={() => setCompanions((prev) => prev.filter((c) => c !== id))} aria-label={t.common.delete}>×</button>
                </Badge>
              );
            })}
          </div>
        ) : null}
        <FormField label={t.frontDesk.checkInModal.notes} htmlFor="ci-notes">
          <Textarea id="ci-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// Check-out modal                                                             //
// --------------------------------------------------------------------------- //

type CoActionKind = "settle" | "refund" | "ins-refund" | "ins-deduct";

function CheckOutModal({
  stay,
  onClose,
  onDone,
}: {
  stay: Stay | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t, locale } = useI18n();
  const c = t.frontDesk.checkOutModal;
  const finLbl = t.frontDesk.finance;
  const can = useCan();
  const [notes, setNotes] = useState("");
  const [reason, setReason] = useState("");
  const [summary, setSummary] = useState<StayFolioSummary | null>(null);
  const [ensureFailed, setEnsureFailed] = useState(false);
  const [ensureBusy, setEnsureBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toggleBusy, setToggleBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [departedAt, setDepartedAt] = useState<string | null>(null);
  const [printMode, setPrintMode] = useState<"preliminary" | "final" | null>(null);
  // A single inline action form is open at a time (settle / refund / insurance).
  const [action, setAction] = useState<{ kind: CoActionKind; id: number } | null>(null);
  const [amountField, setAmountField] = useState("");
  const [methodField, setMethodField] = useState("cash");
  const [reasonField, setReasonField] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const open = stay !== null;
  // The stay the dialog is currently targeting. Because CheckOutModal stays
  // mounted, a slow request (esp. a manual Retry) must skip its writes once the
  // dialog has moved to another stay — this ref is the "still the current stay"
  // check the effect's `ignore` flag cannot cover on the Retry path.
  const currentStayRef = useRef(stay?.id);

  const methodOptions = (["cash", "card", "bank_transfer", "electronic", "other"] as const).map(
    (v) => ({ value: v, label: t.finance.methods[v] }),
  );

  // Post any room night that has become due FIRST (the safety net) so the front
  // desk settles the COMPLETE amount. If that POST fails we must NOT silently
  // show a plain read that may understate the balance: flag ensureFailed (which
  // warns the agent and blocks departure), still fall back to a read so the
  // agent sees something, and if even the read fails surface a real error
  // instead of a permanent silent spinner. `isStale` guards against a slower
  // ensure POST resolving after the dialog was reopened for another stay.
  const runEnsure = useCallback(
    async (stayId: number, isStale: () => boolean = () => false) => {
      // A write is stale if the effect was torn down (`isStale`) OR the dialog
      // has since moved to another stay (ref). The ref covers the Retry path,
      // which has no per-call `ignore` flag of its own.
      const stale = () => isStale() || currentStayRef.current !== stayId;
      setError(null);
      setEnsureBusy(true);
      try {
        const s = await ensureRoomCharges(stayId);
        if (stale()) return;
        setSummary(s);
        setEnsureFailed(false);
      } catch {
        if (stale()) return;
        setEnsureFailed(true);
        try {
          const s = await getStayFolioSummary(stayId);
          if (stale()) return;
          setSummary(s);
        } catch (err) {
          if (stale()) return;
          setError(messageForError(err, t));
        }
      } finally {
        if (!stale()) setEnsureBusy(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (!open || !stay) return;
    let ignore = false;
    currentStayRef.current = stay.id;
    setNotes("");
    setReason("");
    setError(null);
    setSummary(null);
    setEnsureFailed(false);
    setDone(false);
    setDepartedAt(null);
    setPrintMode(null);
    setAction(null);
    void runEnsure(stay.id, () => ignore);
    return () => {
      ignore = true;
    };
  }, [open, stay, runEnsure]);

  async function reload() {
    if (!stay) return;
    // Keep the last-known summary on a transient fetch failure — an action
    // already succeeded, so blanking to a permanent spinner would be worse.
    try {
      setSummary(await getStayFolioSummary(stay.id));
    } catch (err) {
      setError(messageForError(err, t));
    }
  }

  // A finance viewer receives the monetary block; a non-finance viewer receives
  // only abstract operational states. `finSummary` narrows to the finance-visible
  // variant so every money access below is type-safe (and hidden for others).
  const finSummary = summary && summary.financial_details_visible ? summary : null;
  const early = summary?.is_early_departure ?? false;
  const balance = finSummary ? Number(finSummary.balance) : 0;
  const chargesReady = summary !== null && !summary.awaiting_final_charges;
  const balanceReady = finSummary !== null && balance === 0;
  const insuranceReady = finSummary !== null && !finSummary.insurance_pending;
  const canDepartFinance = chargesReady && balanceReady && insuranceReady;
  // The backend is the single checkout-readiness authority: a non-finance viewer
  // has no amounts, so gate on can_check_out; a finance viewer keeps the existing
  // money-derived checklist. Either way a failed ensure POST still blocks (the
  // shown state may be understated). Cancel is never blocked.
  const canDepart = summary !== null && (finSummary ? canDepartFinance : summary.can_check_out);
  // STAYS rate-integrity — a "stuck" stay (a consumed night with no agreed rate)
  // is refused server-side (MissingAgreedNightlyRate, 409). Block the confirm
  // button locally too and show a clear reason so the agent remediates the rate
  // first. This is an OPERATIONAL flag on the stay (not finance-gated).
  const rateRemediationNeeded = stay?.requires_rate_remediation ?? false;
  const blocked = !canDepart || ensureFailed || rateRemediationNeeded;

  function openSettle(folioId: number, folioBalance: string) {
    setAction({ kind: "settle", id: folioId });
    setAmountField(Math.abs(Number(folioBalance)).toFixed(2));
    setMethodField("cash");
    setReasonField("");
    setActionError(null);
  }
  function openRefund(folioId: number, folioBalance: string) {
    setAction({ kind: "refund", id: folioId });
    setAmountField(Math.abs(Number(folioBalance)).toFixed(2));
    setMethodField("cash");
    setReasonField("");
    setActionError(null);
  }
  function openInsAction(kind: "ins-refund" | "ins-deduct", insId: number, held: string) {
    setAction({ kind, id: insId });
    setAmountField(kind === "ins-refund" ? Number(held).toFixed(2) : "");
    setReasonField("");
    setActionError(null);
  }

  async function runAction() {
    if (!action) return;
    setActionBusy(true);
    setActionError(null);
    try {
      if (action.kind === "settle") {
        const folio = finSummary?.open_folios.find((f) => f.id === action.id);
        await settleFolio(action.id, {
          method: methodField,
          amount: amountField.trim(),
          currency: folio?.currency,
        });
      } else if (action.kind === "refund") {
        await refundFolioCredit(action.id, {
          reason: reasonField.trim(),
          amount: amountField.trim() || undefined,
          method: methodField,
        });
      } else if (action.kind === "ins-refund") {
        await refundInsurance(action.id, {
          reason: reasonField.trim() || undefined,
          amount: amountField.trim() || undefined,
        });
      } else {
        await deductInsurance(action.id, {
          amount: amountField.trim(),
          reason: reasonField.trim(),
        });
      }
      setAction(null);
      await reload();
    } catch (err) {
      setActionError(messageForError(err, t));
    } finally {
      setActionBusy(false);
    }
  }

  async function confirmCharges(folioId: number) {
    setToggleBusy(true);
    setError(null);
    try {
      await setFolioAwaitingCharges(folioId, false);
      await reload();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setToggleBusy(false);
    }
  }

  async function submit() {
    if (!stay) return;
    if (early && !reason.trim()) {
      setError(c.reasonRequired);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await checkOut(stay.id, {
        check_out_notes: notes.trim(),
        checkout_reason: reason.trim(),
      });
      setDepartedAt(result.actual_check_out_at);
      setDone(true);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  // Inline action editor (settle / refund / insurance) — a plain block (NOT a
  // nested form) so it lives safely inside the review body.
  function actionEditor(kind: CoActionKind) {
    const withAmount = kind !== "ins-refund";
    const withReason = kind === "refund" || kind === "ins-deduct" || kind === "ins-refund";
    const withMethod = kind === "settle" || kind === "refund";
    const reasonRequired = kind === "refund" || kind === "ins-deduct";
    const submitLabel =
      kind === "settle" ? c.settleSubmit
        : kind === "refund" ? c.refundSubmit
        : kind === "ins-refund" ? c.insuranceRefund
        : c.insuranceDeduct;
    const disabled =
      actionBusy
      || (withAmount && !amountField.trim())
      || (reasonRequired && !reasonField.trim());
    return (
      <div className="stack" style={{ gap: "0.5rem", padding: "0.5rem", background: "var(--surface-2)", borderRadius: "0.5rem" }}>
        {actionError ? <Alert tone="error">{actionError}</Alert> : null}
        {withAmount ? (
          <FormField label={c.settleAmount} htmlFor="co-amount">
            <Input id="co-amount" inputMode="decimal" value={amountField} onChange={(e) => setAmountField(e.target.value)} />
          </FormField>
        ) : null}
        {withMethod ? (
          <FormField label={c.settleMethod} htmlFor="co-method">
            <Select id="co-method" value={methodField} options={methodOptions} onChange={(e) => setMethodField(e.target.value)} />
          </FormField>
        ) : null}
        {withReason ? (
          <FormField label={c.insuranceReason} htmlFor="co-action-reason">
            <Input id="co-action-reason" value={reasonField} onChange={(e) => setReasonField(e.target.value)} required={reasonRequired} />
          </FormField>
        ) : null}
        <div className="row" style={{ gap: "0.5rem" }}>
          <Button type="button" size="sm" loading={actionBusy} disabled={disabled} onClick={runAction}>{submitLabel}</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setAction(null)}>{t.common.cancel}</Button>
        </div>
      </div>
    );
  }

  // Checklist item — never signals met/unmet by colour alone: a distinct icon
  // plus an sr-only state word so the label ("All charges posted") is not read
  // as already-true by assistive tech when the item is still pending.
  function checklistBadge(ok: boolean, label: string) {
    return (
      <Badge tone={ok ? "success" : "warning"} icon={ok ? Check : Clock}>
        {label} <span className="sr-only">— {ok ? c.checkMet : c.checkUnmet}</span>
      </Badge>
    );
  }

  return (
    <Modal
      open={open}
      onClose={done ? onDone : onClose}
      title={`${c.title} · ${stay?.room_number ?? ""}`}
      closeLabel={t.common.close}
      footer={
        done ? (
          <>
            {finSummary && finSummary.open_folios.length > 0 ? (
              <Button variant="secondary" icon={Printer} onClick={() => setPrintMode("final")}>{c.printFinal}</Button>
            ) : null}
            <Button onClick={onDone}>{c.done}</Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
            <Button type="button" loading={busy} disabled={blocked} onClick={submit}>{c.submit}</Button>
          </>
        )
      }
    >
      {done ? (
        <div className="stack" role="status">
          <Alert tone="success">{c.successHeading}</Alert>
          {/* Only a finance viewer gets the monetary "fully settled" confirmation
              and the folio number; others get a money-free departure notice. */}
          <p>{finSummary ? c.successBody : c.successCleared}</p>
          <dl className="detail-grid">
            <div><dt>{c.guest}</dt><dd>{stay?.primary_guest_name}</dd></div>
            <div><dt>{c.room}</dt><dd>{stay?.room_number}</dd></div>
            {finSummary && finSummary.open_folios.length > 0 ? (
              <div><dt>{c.successFolio}</dt><dd>{finSummary.open_folios.map((f) => f.folio_number).join(", ")}</dd></div>
            ) : null}
            <div><dt>{c.successDeparted}</dt><dd>{formatDateTime(departedAt, locale)}</dd></div>
          </dl>
          {finSummary ? <div><Badge tone="success">{c.successPaid}</Badge></div> : null}
          <Alert tone="info">{c.successRoom}</Alert>
        </div>
      ) : (
        <div className="stack">
          {error ? <Alert tone="error">{error}</Alert> : null}
          {rateRemediationNeeded ? (
            <Alert tone="warning">{t.frontDesk.rateRemediation.blockedCheckout}</Alert>
          ) : null}
          <Alert tone="info">{c.body}</Alert>
          {ensureFailed ? (
            <div className="stack" style={{ gap: "0.5rem" }}>
              <Alert tone="warning">
                <strong>{c.ensureFailedTitle}</strong> — {c.ensureFailedBody}
              </Alert>
              <div className="row">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  loading={ensureBusy}
                  onClick={() => { if (stay) void runEnsure(stay.id); }}
                >
                  {t.common.retry}
                </Button>
              </div>
            </div>
          ) : null}
          {stay ? (
            <dl className="detail-grid">
              <div><dt>{c.guest}</dt><dd>{stay.primary_guest_name}</dd></div>
              <div><dt>{c.room}</dt><dd>{stay.room_number}</dd></div>
              <div><dt>{c.checkInDate}</dt><dd>{formatDate(stay.actual_check_in_at, locale)}</dd></div>
              <div><dt>{c.expectedCheckOut}</dt><dd>{formatDate(stay.planned_check_out_date, locale)}</dd></div>
            </dl>
          ) : null}

          {summary === null ? (
            // No spinner once the ensure flow has failed: the warning + retry
            // (and any error) above convey the state instead of a silent loader.
            ensureFailed || error ? null : <LoadingState label={t.common.loading} />
          ) : finSummary ? (
            <div className="stack" style={{ gap: "0.75rem" }}>
              {/* Statement + per-folio settlement / refund (§17/§34/§37) */}
              <div className="stack" style={{ gap: "0.5rem" }}>
                <div className="row" style={{ justifyContent: "space-between", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                  <h4 style={{ margin: 0 }}>{c.statementHeading}</h4>
                  {finSummary.open_folios.length > 0 ? (
                    <Button type="button" size="sm" variant="ghost" icon={Printer} onClick={() => setPrintMode("preliminary")}>{c.printPreliminary}</Button>
                  ) : null}
                </div>
                <p className="muted small">{c.statementNote}</p>
                {finSummary.has_folio && finSummary.open_folios.length > 0 ? (
                  finSummary.open_folios.map((f) => {
                    const b = Number(f.balance);
                    return (
                      <div key={f.id} className="stack" style={{ gap: "0.35rem", paddingBlock: "0.4rem", borderTop: "1px solid var(--border)" }}>
                        <div className="row" style={{ justifyContent: "space-between", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                          <span>{f.folio_number}</span>
                          <strong>{formatMoney(f.balance, f.currency, locale)}</strong>
                        </div>
                        {f.awaiting_final_charges ? (
                          <div className="row" style={{ gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                            <Badge tone="warning">{c.awaitingBadge}</Badge>
                            <Button type="button" size="sm" variant="secondary" loading={toggleBusy} onClick={() => confirmCharges(f.id)}>{c.confirmCharges}</Button>
                          </div>
                        ) : null}
                        {b > 0 && can("finance.payment_create") ? (
                          action?.kind === "settle" && action.id === f.id
                            ? actionEditor("settle")
                            : <div className="row"><Button type="button" size="sm" icon={Wallet} onClick={() => openSettle(f.id, f.balance)}>{c.settle}</Button></div>
                        ) : null}
                        {b < 0 && can("finance.refund") ? (
                          action?.kind === "refund" && action.id === f.id
                            ? actionEditor("refund")
                            : <div className="row"><Button type="button" size="sm" variant="secondary" onClick={() => openRefund(f.id, f.balance)}>{c.refund}</Button></div>
                        ) : null}
                      </div>
                    );
                  })
                ) : (
                  <p className="muted">{c.folioNone}</p>
                )}
              </div>

              {/* Refundable insurance (§35) */}
              {finSummary.insurances.length > 0 ? (
                <div className="stack" style={{ gap: "0.5rem" }}>
                  <h4 style={{ margin: 0 }}>{c.insuranceHeading}</h4>
                  {finSummary.insurances.map((ins) => {
                    const held = Number(ins.held_amount);
                    return (
                      <div key={ins.id} className="stack" style={{ gap: "0.35rem", paddingBlock: "0.4rem", borderTop: "1px solid var(--border)" }}>
                        <div className="row" style={{ justifyContent: "space-between", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                          <span>{c.insuranceHeld}: {formatMoney(ins.held_amount, ins.currency, locale)}</span>
                          {held <= 0 ? <Badge tone="success">{c.insuranceSettled}</Badge> : null}
                        </div>
                        {held > 0 && can("finance.insurance_manage") ? (
                          action && (action.kind === "ins-refund" || action.kind === "ins-deduct") && action.id === ins.id ? (
                            actionEditor(action.kind)
                          ) : (
                            <div className="row" style={{ gap: "0.5rem" }}>
                              <Button type="button" size="sm" onClick={() => openInsAction("ins-refund", ins.id, ins.held_amount)}>{c.insuranceRefund}</Button>
                              <Button type="button" size="sm" variant="secondary" onClick={() => openInsAction("ins-deduct", ins.id, ins.held_amount)}>{c.insuranceDeduct}</Button>
                            </div>
                          )
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ) : null}

              {/* Departure checklist (§39) — color is never the only signal */}
              <div className="stack" style={{ gap: "0.35rem" }}>
                <h4 style={{ margin: 0 }}>{c.checklistHeading}</h4>
                <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
                  {checklistBadge(chargesReady, c.checkCharges)}
                  {checklistBadge(balanceReady, c.checkBalance)}
                  {checklistBadge(insuranceReady, c.checkInsurance)}
                </div>
              </div>

              {early ? <Alert tone="warning">{c.earlyDeparture}</Alert> : null}
            </div>
          ) : (
            // Non-finance viewer — the backend sent NO amounts. Show only the
            // operational clearance state + a permission note; departure is
            // authorised by the backend's can_check_out (see `blocked`), never by
            // a money-derived flag. No statement/settlement/refund/insurance UI.
            <div className="stack" style={{ gap: "0.5rem" }}>
              <div className="cluster" style={{ gap: "0.35rem" }}>
                {checklistBadge(
                  summary.financial_clearance_complete,
                  summary.financial_clearance_complete ? finLbl.clearanceComplete : finLbl.clearancePending,
                )}
              </div>
              <Alert tone="info">{finLbl.detailsHidden}</Alert>
              {early ? <Alert tone="warning">{c.earlyDeparture}</Alert> : null}
            </div>
          )}

          <FormField label={c.notes} htmlFor="co-notes">
            <Input id="co-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </FormField>
          {early ? (
            <FormField label={c.reason} htmlFor="co-reason">
              <Input id="co-reason" value={reason} onChange={(e) => setReason(e.target.value)} required />
            </FormField>
          ) : null}
          {finSummary ? <Alert tone="warning">{c.financeNote}</Alert> : null}
        </div>
      )}
      <StayStatementPrintModal
        open={printMode !== null}
        folioId={finSummary?.open_folios[0]?.id ?? null}
        mode={printMode ?? "preliminary"}
        onClose={() => setPrintMode(null)}
      />
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// Extend / shorten stay modals                                                //
// --------------------------------------------------------------------------- //

function ExtendStayModal({
  stay,
  onClose,
  onDone,
}: {
  stay: Stay | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t, locale } = useI18n();
  const can = useCan();
  const em = t.frontDesk.extendModal;
  const [newDate, setNewDate] = useState("");
  const [reason, setReason] = useState("");
  const [rate, setRate] = useState("");
  const [triedSubmit, setTriedSubmit] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const open = stay !== null;

  // The stay's CURRENT nightly rate (the value an extension defaults from) comes
  // straight from the backend folio summary — finance.view ONLY, and NEVER
  // recomputed here. It rides on the finance-visible variant of the card summary
  // already loaded with the residents list, so no extra request/permission.
  const finFolio =
    stay?.folio_summary && stay.folio_summary.financial_details_visible
      ? stay.folio_summary
      : null;
  const showRate = can("finance.view");
  // The added-period rate OVERRIDE is gated on `stays.rate_override` (the backend
  // moved this off `finance.charge_create`). Displaying the current rate value
  // still requires `finance.view` (it is finance-derived data), so a viewer needs
  // BOTH to edit it; the backend re-checks `stays.rate_override` on submit.
  const canOverride = can("stays.rate_override");
  const defaultRate = finFolio?.current_nightly_rate ?? null;
  const rateCurrency = finFolio?.current_rate_currency ?? null;

  useEffect(() => {
    if (open && stay) {
      const ff =
        stay.folio_summary && stay.folio_summary.financial_details_visible
          ? stay.folio_summary
          : null;
      setNewDate(addDays(stay.planned_check_out_date, 1));
      setReason("");
      // Seed the editable rate with the backend default so an unchanged submit is
      // never treated as an override (empty when there is no current rate).
      setRate(ff?.current_nightly_rate ?? "");
      setTriedSubmit(false);
      setError(null);
    }
  }, [open, stay]);

  const trimmedRate = rate.trim();
  // Mirror the backend gate (apps.stays.services._apply_extension): an OVERRIDE is
  // a `stays.rate_override` holder setting a rate that differs from the default
  // (or ANY rate when the stay has no default). Only an override sends
  // nightly_rate and demands a non-empty reason; everything else stays the plain,
  // backward-compatible date-only extend.
  const isOverride =
    canOverride &&
    trimmedRate !== "" &&
    (defaultRate === null || Number(trimmedRate) !== Number(defaultRate));
  const reasonMissing = isOverride && !reason.trim();
  // An override rate must be a positive number (backend min 0.01). Block submit
  // locally with an inline error instead of relying only on the server.
  const rateInvalid =
    isOverride &&
    (!Number.isFinite(Number(trimmedRate)) || Number(trimmedRate) <= 0);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!stay || !newDate) return;
    setTriedSubmit(true);
    // Block submit locally when an override lacks its mandatory reason or carries a
    // non-positive rate — the inline errors explain why (the backend also rejects).
    if (reasonMissing || rateInvalid) return;
    setBusy(true);
    setError(null);
    try {
      await extendStay(stay.id, {
        new_check_out_date: newDate,
        reason: reason.trim(),
        ...(isOverride ? { nightly_rate: trimmedRate } : {}),
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
      title={`${em.title} · ${stay?.room_number ?? ""}`}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="extend-form" type="submit" loading={busy}>{em.submit}</Button>
        </>
      }
    >
      <form id="extend-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        {stay ? (
          <dl className="detail-grid">
            <div><dt>{t.frontDesk.checkOutModal.guest}</dt><dd>{stay.primary_guest_name}</dd></div>
            <div><dt>{em.currentCheckOut}</dt><dd>{formatDate(stay.planned_check_out_date, locale)}</dd></div>
          </dl>
        ) : null}
        <FormField label={em.newCheckOut} htmlFor="ext-date">
          <Input
            id="ext-date"
            type="date"
            value={newDate}
            min={stay ? addDays(stay.planned_check_out_date, 1) : undefined}
            onChange={(e) => setNewDate(e.target.value)}
          />
        </FormField>
        {/* Added-period nightly rate — finance.view ONLY. The value is DISPLAYED
            from the backend (never computed); a viewer without the pricing
            permission sees it read-only, and a non-finance viewer sees nothing. */}
        {showRate ? (
          <FormField
            label={em.rateLabel}
            htmlFor="ext-rate"
            hint={canOverride ? em.rateCurrentHint : em.overrideHint}
            error={triedSubmit && rateInvalid ? t.frontDesk.rateRemediation.rateInvalid : undefined}
          >
            {canOverride ? (
              <Input
                id="ext-rate"
                inputMode="decimal"
                value={rate}
                placeholder={defaultRate ?? em.rateCurrentHint}
                onChange={(e) => setRate(e.target.value)}
              />
            ) : (
              <Input
                id="ext-rate"
                value={defaultRate ? formatMoney(defaultRate, rateCurrency ?? "", locale) : em.rateCurrentHint}
                disabled
                readOnly
              />
            )}
          </FormField>
        ) : null}
        <FormField
          label={isOverride ? em.overrideReasonLabel : em.reason}
          htmlFor="ext-reason"
          error={triedSubmit && reasonMissing ? em.reasonRequired : undefined}
        >
          <Input
            id="ext-reason"
            value={reason}
            placeholder={isOverride ? em.overrideReasonPlaceholder : undefined}
            required={isOverride}
            onChange={(e) => setReason(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function ShortenStayModal({
  stay,
  onClose,
  onDone,
}: {
  stay: Stay | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t, locale } = useI18n();
  const [newDate, setNewDate] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const open = stay !== null;

  useEffect(() => {
    if (open && stay) {
      setNewDate(addDays(stay.planned_check_out_date, -1));
      setReason("");
      setError(null);
    }
  }, [open, stay]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!stay || !newDate) return;
    setBusy(true);
    setError(null);
    try {
      await shortenStay(stay.id, { new_check_out_date: newDate, reason: reason.trim() });
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
      title={`${t.frontDesk.shortenModal.title} · ${stay?.room_number ?? ""}`}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="shorten-form" type="submit" loading={busy}>{t.frontDesk.shortenModal.submit}</Button>
        </>
      }
    >
      <form id="shorten-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        {stay ? (
          <dl className="detail-grid">
            <div><dt>{t.frontDesk.checkOutModal.guest}</dt><dd>{stay.primary_guest_name}</dd></div>
            <div><dt>{t.frontDesk.shortenModal.currentCheckOut}</dt><dd>{formatDate(stay.planned_check_out_date, locale)}</dd></div>
          </dl>
        ) : null}
        <Alert tone="warning">{t.frontDesk.shortenModal.chargesWarning}</Alert>
        <FormField label={t.frontDesk.shortenModal.newCheckOut} htmlFor="sho-date">
          <Input
            id="sho-date"
            type="date"
            value={newDate}
            max={stay ? addDays(stay.planned_check_out_date, -1) : undefined}
            onChange={(e) => setNewDate(e.target.value)}
          />
        </FormField>
        <FormField label={t.frontDesk.shortenModal.reason} htmlFor="sho-reason">
          <Input id="sho-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// Room move modal                                                             //
// --------------------------------------------------------------------------- //

function MoveRoomModal({
  stay,
  onClose,
  onDone,
}: {
  stay: Stay | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [rooms, setRooms] = useState<AdmissibleRoom[]>([]);
  const [roomId, setRoomId] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const open = stay !== null;

  useEffect(() => {
    if (!open || !stay) return;
    setRoomId("");
    setReason("");
    setError(null);
    setRooms([]);
    listMoveCandidates(stay.id).then(setRooms).catch(() => setRooms([]));
  }, [open, stay]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!stay) return;
    if (!roomId) return setError(t.frontDesk.moveModal.roomRequired);
    if (!reason.trim()) return setError(t.frontDesk.moveModal.reasonRequired);
    setBusy(true);
    setError(null);
    try {
      await moveStayRoom(stay.id, { room: Number(roomId), reason: reason.trim() });
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const options = rooms.map((r) => ({
    value: String(r.id),
    label: r.room_type_name ? `${r.number} · ${r.room_type_name}` : r.number,
  }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${t.frontDesk.moveModal.title} · ${stay?.room_number ?? ""}`}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="move-form" type="submit" loading={busy}>{t.frontDesk.moveModal.submit}</Button>
        </>
      }
    >
      <form id="move-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        {stay ? (
          <dl className="detail-grid">
            <div><dt>{t.frontDesk.moveModal.currentRoom}</dt><dd>{stay.room_number}</dd></div>
            <div><dt>{t.frontDesk.checkOutModal.guest}</dt><dd>{stay.primary_guest_name}</dd></div>
          </dl>
        ) : null}
        <FormField label={t.frontDesk.moveModal.newRoom} htmlFor="mv-room">
          <Select
            id="mv-room"
            value={roomId}
            placeholder={options.length ? t.frontDesk.moveModal.selectRoom : t.frontDesk.moveModal.noRooms}
            options={options}
            onChange={(e) => setRoomId(e.target.value)}
          />
        </FormField>
        <FormField label={t.frontDesk.moveModal.reason} htmlFor="mv-reason">
          <Input id="mv-reason" value={reason} onChange={(e) => setReason(e.target.value)} required />
        </FormField>
      </form>
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// Rate remediation modal (STAYS rate-integrity)                               //
// --------------------------------------------------------------------------- //

/**
 * A LIMITED corrective form (NOT a price-management page): a `stays.rate_override`
 * holder sets the missing agreed nightly rate for a "stuck" stay's uncovered
 * window. The frontend NEVER computes night charges — it only records the agreed
 * rate; the backend re-checks the permission, requires the reason, and enforces
 * that the currency matches the folio. On success the parent refetches the folio +
 * operational state (via `onDone`). The period defaults to the stay's own dates
 * (the backend does not expose the specific uncovered nights on the serializer).
 */
function RemediateRateModal({
  stay,
  onClose,
  onDone,
}: {
  stay: Stay | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const rr = t.frontDesk.rateRemediation;
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [rate, setRate] = useState("");
  const [currency, setCurrency] = useState("");
  const [reason, setReason] = useState("");
  const [triedSubmit, setTriedSubmit] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const open = stay !== null;

  useEffect(() => {
    if (!open || !stay) return;
    setStartDate(stay.planned_check_in_date);
    setEndDate(stay.planned_check_out_date);
    setRate("");
    // Prefill the currency from the folio when the viewer can see it (finance
    // viewer); a rate_override-only viewer types it and the backend validates it
    // against the folio currency.
    const fin =
      stay.folio_summary && stay.folio_summary.financial_details_visible
        ? stay.folio_summary
        : null;
    setCurrency(fin?.currency ?? "");
    setReason("");
    setTriedSubmit(false);
    setError(null);
  }, [open, stay]);

  const reasonMissing = !reason.trim();
  // Inline positive-rate guard — block submit locally (the backend also enforces a
  // strictly-positive min 0.01) so the agent gets an immediate, specific error.
  const rateValue = rate.trim();
  const rateInvalid =
    rateValue === "" ||
    !Number.isFinite(Number(rateValue)) ||
    Number(rateValue) <= 0;
  const incomplete =
    reasonMissing || rateInvalid || !currency.trim() || !startDate || !endDate;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!stay) return;
    setTriedSubmit(true);
    if (incomplete) return;
    setBusy(true);
    setError(null);
    try {
      await remediateStayRate(stay.id, {
        start_date: startDate,
        end_date: endDate,
        nightly_rate: rate.trim(),
        currency: currency.trim(),
        reason: reason.trim(),
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
      title={`${rr.title} · ${stay?.room_number ?? ""}`}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="remediate-form" type="submit" loading={busy}>{rr.submit}</Button>
        </>
      }
    >
      <form id="remediate-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="info">{rr.hint}</Alert>
        {stay ? (
          <dl className="detail-grid">
            <div><dt>{t.frontDesk.checkOutModal.guest}</dt><dd>{stay.primary_guest_name}</dd></div>
            <div><dt>{t.frontDesk.checkOutModal.room}</dt><dd>{stay.room_number}</dd></div>
          </dl>
        ) : null}
        <div className="line-row">
          <FormField label={rr.periodStart} htmlFor="rr-start">
            <Input id="rr-start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </FormField>
          <FormField label={rr.periodEnd} htmlFor="rr-end">
            <Input id="rr-end" type="date" value={endDate} min={startDate || undefined} onChange={(e) => setEndDate(e.target.value)} />
          </FormField>
        </div>
        <div className="line-row">
          <FormField
            label={rr.rate}
            htmlFor="rr-rate"
            error={triedSubmit && rateInvalid ? rr.rateInvalid : undefined}
          >
            <Input id="rr-rate" inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} />
          </FormField>
          <FormField label={rr.currency} htmlFor="rr-currency">
            <Input id="rr-currency" value={currency} maxLength={3} onChange={(e) => setCurrency(e.target.value.toUpperCase())} />
          </FormField>
        </div>
        <FormField
          label={rr.reason}
          htmlFor="rr-reason"
          error={triedSubmit && reasonMissing ? rr.reasonRequired : undefined}
        >
          <Input id="rr-reason" value={reason} required onChange={(e) => setReason(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// Stay details modal                                                          //
// --------------------------------------------------------------------------- //

function StayDetailsModal({ stay, onClose }: { stay: Stay | null; onClose: () => void }) {
  const { t, locale } = useI18n();
  const [logs, setLogs] = useState<StayStatusLogEntry[]>([]);
  const open = stay !== null;

  useEffect(() => {
    if (!open || !stay) return;
    getStayLogs(stay.id).then(setLogs).catch(() => setLogs([]));
  }, [open, stay]);

  if (!stay) return null;

  return (
    <Modal open={open} onClose={onClose} title={`${t.frontDesk.details.title} · ${stay.room_number}`} closeLabel={t.common.close} footer={<Button variant="secondary" onClick={onClose}>{t.common.close}</Button>}>
      <div className="stack">
        <div className="cluster">
          <Badge tone={stayStatusTone(stay.status)}>{stayStatusLabel(stay.status, t)}</Badge>
          {stay.reservation_number ? <span className="muted">{t.frontDesk.details.reservation}: {stay.reservation_number}</span> : null}
        </div>
        <dl className="detail-grid">
          <div><dt>{t.frontDesk.details.room}</dt><dd>{stay.room_number} · {stay.room_type_name}</dd></div>
          <div><dt>{t.frontDesk.details.guest}</dt><dd>{stay.primary_guest_name}</dd></div>
          <div><dt>{t.frontDesk.details.dates}</dt><dd>{formatDate(stay.planned_check_in_date, locale)} → {formatDate(stay.planned_check_out_date, locale)}</dd></div>
          <div><dt>{t.frontDesk.details.nights}</dt><dd>{stay.nights}</dd></div>
          <div><dt>{t.frontDesk.details.checkedInAt}</dt><dd>{formatDate(stay.actual_check_in_at, locale)}</dd></div>
          {stay.actual_check_out_at ? <div><dt>{t.frontDesk.details.checkedOutAt}</dt><dd>{formatDate(stay.actual_check_out_at, locale)}</dd></div> : null}
          {stay.checked_in_by ? <div><dt>{t.frontDesk.details.checkedInBy}</dt><dd>{stay.checked_in_by}</dd></div> : null}
          {stay.checked_out_by ? <div><dt>{t.frontDesk.details.checkedOutBy}</dt><dd>{stay.checked_out_by}</dd></div> : null}
        </dl>
        <div>
          <h4>{t.frontDesk.details.companions}</h4>
          <ul className="mini-list">
            {stay.guests.map((g) => (
              <li key={g.id} className="mini-list__row">
                <span>{g.guest_name}</span>
                <Badge tone={g.role === "primary" ? "success" : "neutral"}>{g.role}</Badge>
              </li>
            ))}
          </ul>
        </div>
        {stay.check_in_notes || stay.check_out_notes ? (
          <div>
            <h4>{t.frontDesk.details.notes}</h4>
            {stay.check_in_notes ? <p>{stay.check_in_notes}</p> : null}
            {stay.check_out_notes ? <p className="muted">{stay.check_out_notes}</p> : null}
          </div>
        ) : null}
        <div>
          <h4>{t.frontDesk.details.history}</h4>
          {logs.length === 0 ? (
            <p className="muted">{t.frontDesk.details.noHistory}</p>
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
