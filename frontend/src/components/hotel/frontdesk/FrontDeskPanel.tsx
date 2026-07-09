"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import {
  DoorOpen,
  LogOut,
  PlaneLanding,
  PlaneTakeoff,
  Plus,
  Users,
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
  SectionHeader,
  Select,
  Tabs,
  Textarea,
  useToast,
  WorkflowCard,
  type TabItem,
} from "@/components/ui";
import {
  checkIn,
  checkOut,
  getStayLogs,
  listArrivalsToday,
  listCurrentResidents,
  listDeparturesToday,
} from "@/lib/api/stays";
import { createGuest, listGuests } from "@/lib/api/guests";
import { listRooms } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type {
  Guest,
  Reservation,
  Room,
  Stay,
  StayStatusLogEntry,
} from "@/lib/api/types";
import { formatDate, stayStatusLabel, stayStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

const TAB_KEYS = ["arrivals", "current", "departures"];

export function FrontDeskPanel() {
  const { t } = useI18n();
  // Deep-linkable initial tab (?tab=departures — the topbar quick actions):
  // read once on mount, tabs themselves stay local state as before.
  const requested = useSearchParams().get("tab");
  const [tab, setTab] = useState(
    requested && TAB_KEYS.includes(requested) ? requested : "arrivals",
  );
  const [reloadKey, setReloadKey] = useState(0);
  const refresh = () => setReloadKey((k) => k + 1);
  const [counts, setCounts] = useState<{
    arrivals: number;
    current: number;
    departures: number;
  } | null>(null);

  useEffect(() => {
    let stale = false;
    Promise.all([listArrivalsToday(), listCurrentResidents(), listDeparturesToday()])
      .then(([a, c, d]) => {
        if (!stale) setCounts({ arrivals: a.length, current: c.count, departures: d.count });
      })
      .catch(() => {
        if (!stale) setCounts(null);
      });
    return () => {
      stale = true;
    };
  }, [reloadKey]);

  const tabs: TabItem[] = [
    { key: "arrivals", label: t.frontDesk.tabs.arrivals, icon: PlaneLanding },
    { key: "current", label: t.frontDesk.tabs.current, icon: DoorOpen },
    { key: "departures", label: t.frontDesk.tabs.departures, icon: LogOut },
  ];

  return (
    <>
      <div className="workflow-grid">
        <WorkflowCard
          icon={PlaneLanding}
          tone="info"
          title={t.frontDesk.workflow.arrivalsTitle}
          value={counts ? counts.arrivals : "—"}
          description={t.frontDesk.workflow.arrivalsDesc}
          action={
            <Button variant="secondary" size="sm" onClick={() => setTab("arrivals")}>
              {t.frontDesk.workflow.view}
            </Button>
          }
        />
        <WorkflowCard
          icon={Users}
          tone="success"
          title={t.frontDesk.workflow.currentTitle}
          value={counts ? counts.current : "—"}
          description={t.frontDesk.workflow.currentDesc}
          action={
            <Button variant="secondary" size="sm" onClick={() => setTab("current")}>
              {t.frontDesk.workflow.view}
            </Button>
          }
        />
        <WorkflowCard
          icon={PlaneTakeoff}
          tone="warning"
          title={t.frontDesk.workflow.departuresTitle}
          value={counts ? counts.departures : "—"}
          description={t.frontDesk.workflow.departuresDesc}
          action={
            <Button variant="secondary" size="sm" onClick={() => setTab("departures")}>
              {t.frontDesk.workflow.view}
            </Button>
          }
        />
        <WorkflowCard
          icon={DoorOpen}
          tone="primary"
          title={t.frontDesk.workflow.checkInTitle}
          description={t.frontDesk.workflow.checkInDesc}
          action={
            <Button size="sm" onClick={() => setTab("arrivals")}>
              {t.frontDesk.workflow.checkInAction}
            </Button>
          }
        />
        <WorkflowCard
          icon={LogOut}
          tone="danger"
          title={t.frontDesk.workflow.checkOutTitle}
          description={t.frontDesk.workflow.checkOutDesc}
          action={
            <Button size="sm" onClick={() => setTab("departures")}>
              {t.frontDesk.workflow.checkOutAction}
            </Button>
          }
        />
      </div>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "arrivals" ? <ArrivalsTab reloadKey={reloadKey} onChange={refresh} /> : null}
      {tab === "current" ? <CurrentTab reloadKey={reloadKey} onChange={refresh} /> : null}
      {tab === "departures" ? <DeparturesTab reloadKey={reloadKey} onChange={refresh} /> : null}
    </>
  );
}

// --------------------------------------------------------------------------- //
// Arrivals today                                                              //
// --------------------------------------------------------------------------- //

function ArrivalsTab({ reloadKey, onChange }: { reloadKey: number; onChange: () => void }) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [rows, setRows] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<Reservation | null>(null);

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

  return (
    <>
      <SectionHeader title={t.frontDesk.tabs.arrivals} icon={PlaneLanding} />
      <div className="stack">
        {rows.map((res) => (
          <ActionCard
            key={res.id}
            icon={PlaneLanding}
            title={`${res.reservation_number} · ${res.primary_guest_name}`}
            description={`${formatDate(res.check_in_date, locale)} → ${formatDate(res.check_out_date, locale)} · ${res.lines.map((l) => `${l.quantity}× ${l.room_type_name}${l.room_number ? ` (${l.room_number})` : ""}`).join(", ")}`}
            action={<Button icon={DoorOpen} onClick={() => setTarget(res)}>{t.frontDesk.arrivals.checkIn}</Button>}
          />
        ))}
      </div>
      <CheckInModal
        reservation={target}
        onClose={() => setTarget(null)}
        onDone={() => { setTarget(null); notify(t.frontDesk.saved); onChange(); }}
      />
    </>
  );
}

// --------------------------------------------------------------------------- //
// Current residents                                                           //
// --------------------------------------------------------------------------- //

function CurrentTab({ reloadKey, onChange }: { reloadKey: number; onChange: () => void }) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [rows, setRows] = useState<Stay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [details, setDetails] = useState<Stay | null>(null);
  const [checkoutTarget, setCheckoutTarget] = useState<Stay | null>(null);

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

  return (
    <>
      <SectionHeader title={t.frontDesk.tabs.current} icon={DoorOpen} />
      <div className="stay-grid">
        {rows.map((stay) => (
          <article className="stay-card" key={stay.id}>
            <div className="stay-card__head">
              <span className="stay-card__room">{stay.room_number}</span>
              <Badge tone={stayStatusTone(stay.status)}>{stayStatusLabel(stay.status, t)}</Badge>
            </div>
            <div className="stay-card__meta">
              <span><Users size={14} aria-hidden /> {stay.primary_guest_name}</span>
              <span>{t.frontDesk.current.checkInDate}: {formatDate(stay.actual_check_in_at, locale)}</span>
              <span>{t.frontDesk.current.checkOutDate}: {formatDate(stay.planned_check_out_date, locale)} · {stay.nights} {t.frontDesk.current.nights}</span>
            </div>
            <div className="stay-card__actions">
              <Button variant="secondary" size="sm" onClick={() => setDetails(stay)}>{t.frontDesk.current.details}</Button>
              <Button variant="ghost" size="sm" icon={LogOut} onClick={() => setCheckoutTarget(stay)}>{t.frontDesk.current.checkOut}</Button>
            </div>
          </article>
        ))}
      </div>
      <StayDetailsModal stay={details} onClose={() => setDetails(null)} />
      <CheckOutModal
        stay={checkoutTarget}
        onClose={() => setCheckoutTarget(null)}
        onDone={() => { setCheckoutTarget(null); notify(t.frontDesk.saved); onChange(); }}
      />
    </>
  );
}

// --------------------------------------------------------------------------- //
// Departures today                                                            //
// --------------------------------------------------------------------------- //

function DeparturesTab({ reloadKey, onChange }: { reloadKey: number; onChange: () => void }) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [rows, setRows] = useState<Stay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [checkoutTarget, setCheckoutTarget] = useState<Stay | null>(null);

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

  return (
    <>
      <SectionHeader title={t.frontDesk.tabs.departures} icon={LogOut} />
      <div className="stack">
        {rows.map((stay) => (
          <ActionCard
            key={stay.id}
            icon={PlaneTakeoff}
            title={`${stay.room_number} · ${stay.primary_guest_name}`}
            description={`${formatDate(stay.actual_check_in_at, locale)} → ${formatDate(stay.planned_check_out_date, locale)}`}
            action={<Button icon={LogOut} onClick={() => setCheckoutTarget(stay)}>{t.frontDesk.current.checkOut}</Button>}
          />
        ))}
      </div>
      <CheckOutModal
        stay={checkoutTarget}
        onClose={() => setCheckoutTarget(null)}
        onDone={() => { setCheckoutTarget(null); notify(t.frontDesk.saved); onChange(); }}
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
  const { t } = useI18n();
  const [lineId, setLineId] = useState("");
  const [roomId, setRoomId] = useState("");
  const [guestId, setGuestId] = useState("");
  const [companions, setCompanions] = useState<number[]>([]);
  const [companionPick, setCompanionPick] = useState("");
  const [notes, setNotes] = useState("");
  const [guests, setGuests] = useState<Guest[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [quickName, setQuickName] = useState("");
  const [quickPhone, setQuickPhone] = useState("");
  const [showQuick, setShowQuick] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
    listGuests({ page_size: 200, is_active: "true" }).then((r) => setGuests(r.results)).catch(() => setGuests([]));
  }, [open, reservation]);

  // Load available rooms of the selected line's room type (unless pinned).
  useEffect(() => {
    if (!open || !line) return;
    if (line.room) {
      setRoomId(String(line.room));
      setRooms([]);
      return;
    }
    setRoomId("");
    listRooms({ room_type: line.room_type, status: "available", page_size: 200 })
      .then((r) => setRooms(r.results))
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
      await checkIn({
        reservation: reservation.id,
        reservation_line: line.id,
        room,
        primary_guest: Number(guestId),
        companions,
        check_in_notes: notes.trim(),
      });
      onDone();
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

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.frontDesk.checkInModal.title}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="checkin-form" type="submit" loading={busy}>{t.frontDesk.checkInModal.submit}</Button>
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
          <div className="line-row">
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
  const [notes, setNotes] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const open = stay !== null;

  useEffect(() => {
    if (open) {
      setNotes("");
      setReason("");
      setError(null);
    }
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!stay) return;
    setBusy(true);
    try {
      await checkOut(stay.id, { check_out_notes: notes.trim(), checkout_reason: reason.trim() });
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
      title={`${t.frontDesk.checkOutModal.title} · ${stay?.room_number ?? ""}`}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="checkout-form" type="submit" loading={busy}>{t.frontDesk.checkOutModal.submit}</Button>
        </>
      }
    >
      <form id="checkout-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="info">{t.frontDesk.checkOutModal.body}</Alert>
        {stay ? (
          <dl className="detail-grid">
            <div><dt>{t.frontDesk.checkOutModal.guest}</dt><dd>{stay.primary_guest_name}</dd></div>
            <div><dt>{t.frontDesk.checkOutModal.room}</dt><dd>{stay.room_number}</dd></div>
            <div><dt>{t.frontDesk.checkOutModal.checkInDate}</dt><dd>{formatDate(stay.actual_check_in_at, locale)}</dd></div>
            <div><dt>{t.frontDesk.checkOutModal.expectedCheckOut}</dt><dd>{formatDate(stay.planned_check_out_date, locale)}</dd></div>
          </dl>
        ) : null}
        <FormField label={t.frontDesk.checkOutModal.notes} htmlFor="co-notes">
          <Input id="co-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </FormField>
        <FormField label={t.frontDesk.checkOutModal.reason} htmlFor="co-reason">
          <Input id="co-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
        <Alert tone="warning">{t.frontDesk.checkOutModal.financeNote}</Alert>
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
