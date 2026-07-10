"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import {
  Ban,
  DoorOpen,
  Pencil,
  Plus,
  ShieldCheck,
  Star,
  Trash2,
  User,
  Users,
} from "lucide-react";

import { useQuickAction } from "@/lib/useQuickAction";

import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  Modal,
  Pagination,
  Select,
  Switch,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  blockGuest,
  createGuest,
  deleteGuest,
  getGuestProfile,
  listGuestDirectory,
  setGuestVip,
  unblockGuest,
  updateGuest,
  type GuestWriteBody,
} from "@/lib/api/guests";
import { messageForError } from "@/lib/api/errors";
import type { Guest, GuestDirectoryRow, GuestProfile } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useI18n } from "@/lib/i18n/I18nProvider";

const PAGE_SIZE = 25;

/** First letters of the first two name words — for the guest avatar. */
function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase();
}

/** Cosmetic permission gate — every API re-checks server-side regardless. */
function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

export function GuestsPanel() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const [rows, setRows] = useState<GuestDirectoryRow[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  // Topbar quick action: ?action=new opens the EXISTING guest modal once.
  useQuickAction("new", () => setCreating(true));
  const [profileId, setProfileId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listGuestDirectory({
        page,
        search: query || undefined,
        is_active: showInactive ? undefined : "true",
      });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, query, showInactive, t]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  function applySearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setQuery(search);
  }

  return (
    <>
      <Card>
        <form onSubmit={applySearch}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="guest-search">
              <Input id="guest-search" value={search} placeholder={t.guests.list.searchPlaceholder} onChange={(e) => setSearch(e.target.value)} />
            </FormField>
            <div className="filter-bar__actions cluster">
              <Switch id="guest-inactive" label={t.guests.list.showInactive} checked={showInactive} onChange={(v) => { setPage(1); setShowInactive(v); }} />
              {can("guests.create") ? (
                <Button icon={Plus} anim="add" onClick={() => setCreating(true)}>{t.guests.list.add}</Button>
              ) : null}
            </div>
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
            title={t.guests.directory.empty}
            hint={t.guests.directory.emptyHint}
            icon={Users}
          />
        ) : (
          <>
            <div className="guest-grid" role="list" aria-label={t.guests.title}>
              {rows.map((r) => (
                <article
                  key={r.id}
                  role="listitem"
                  className={[
                    "guest-card",
                    r.is_blocked
                      ? "guest-card--blocked"
                      : r.is_vip
                        ? "guest-card--vip"
                        : r.is_resident
                          ? "guest-card--resident"
                          : "",
                  ].join(" ")}
                >
                  <div className="guest-card__head">
                    <span className="avatar avatar--lg" aria-hidden="true">{initials(r.full_name)}</span>
                    <div>
                      <div className="guest-card__name">{r.full_name}</div>
                      <div className="cluster" style={{ gap: "0.3rem" }}>
                        {r.is_vip ? <Badge tone="vip"><Star size={12} aria-hidden /> {t.guests.vip.badge}</Badge> : null}
                        {r.is_blocked ? <Badge tone="blocked">{t.guests.block.badge}</Badge> : null}
                        {!r.is_active ? <Badge tone="neutral">{t.guests.inactive}</Badge> : null}
                        {r.is_resident ? (
                          <Badge tone="inhouse">
                            {t.guests.directory.resident}{r.current_room_number ? ` · ${r.current_room_number}` : ""}
                          </Badge>
                        ) : null}
                        <Badge tone={r.is_repeat ? "reserved" : "info"}>
                          {r.is_repeat ? t.guests.directory.repeat : t.guests.directory.firstTime}
                        </Badge>
                      </div>
                    </div>
                  </div>
                  <div className="guest-card__meta">
                    <span>{t.guests.list.phone}: {r.phone || "—"}</span>
                    <span>{t.guests.list.nationality}: {r.nationality || "—"}</span>
                  </div>
                  <div className="guest-card__stats">
                    <span>{t.guests.directory.stays}: <strong>{r.stays_count}</strong></span>
                    <span>{t.guests.profile.nights}: <strong>{r.nights_total}</strong></span>
                    <span>{t.guests.directory.lastStay}: <strong>{r.last_stay_date ? formatDate(r.last_stay_date, locale) : "—"}</strong></span>
                  </div>
                  <div className="guest-card__footer">
                    <Button variant="secondary" size="sm" anim="open" icon={User} onClick={() => setProfileId(r.id)}>
                      {t.guests.directory.openProfile}
                    </Button>
                  </div>
                </article>
              ))}
            </div>
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

      <GuestModal open={creating} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); notify(t.guests.saved); setPage(1); load(); }} />
      <GuestProfileModal
        guestId={profileId}
        onClose={() => setProfileId(null)}
        onChanged={load}
      />
    </>
  );
}

// --------------------------------------------------------------------------- //
// Guest profile modal (read-only history + permission-gated actions)          //
// --------------------------------------------------------------------------- //

function GuestProfileModal({
  guestId,
  onClose,
  onChanged,
}: {
  guestId: number | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const [profile, setProfile] = useState<GuestProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [blocking, setBlocking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const open = guestId !== null;

  const reload = useCallback(() => {
    if (guestId === null) return;
    getGuestProfile(guestId)
      .then((p) => { setProfile(p); setError(null); })
      .catch((err) => setError(messageForError(err, t)));
  }, [guestId, t]);

  useEffect(() => {
    setProfile(null);
    setError(null);
    setEditing(false);
    setBlocking(false);
    setDeleting(false);
    reload();
  }, [reload]);

  async function toggleVip() {
    if (!profile) return;
    setBusy(true);
    try {
      await setGuestVip(profile.id, !profile.is_vip);
      notify(t.guests.saved);
      reload();
      onChanged();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusy(false);
    }
  }

  async function doUnblock() {
    if (!profile) return;
    setBusy(true);
    try {
      await unblockGuest(profile.id);
      notify(t.guests.block.unblocked);
      reload();
      onChanged();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!profile) return;
    setBusy(true);
    try {
      const res = await deleteGuest(profile.id);
      notify(
        res.result === "deleted"
          ? t.guests.deleteResult.deleted
          : t.guests.deleteResult.deactivated,
      );
      setDeleting(false);
      onChanged();
      if (res.result === "deleted") onClose();
      else reload();
    } catch (err) {
      notify(messageForError(err, t), "error");
      setDeleting(false);
    } finally {
      setBusy(false);
    }
  }

  const p = profile;

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={p ? p.full_name : t.guests.profile.title}
        closeLabel={t.common.close}
        footer={<Button variant="secondary" onClick={onClose}>{t.common.close}</Button>}
      >
        {error ? <Alert tone="error">{error}</Alert> : null}
        {!p && !error ? <LoadingState label={t.common.loading} /> : null}
        {p ? (
          <div className="stack">
            <div className="cluster" style={{ alignItems: "center" }}>
              <span className="avatar avatar--lg" aria-hidden="true">{initials(p.full_name)}</span>
              {p.is_resident ? (
                <Badge tone="inhouse">{t.guests.directory.resident}{p.current_room_number ? ` · ${p.current_room_number}` : ""}</Badge>
              ) : (
                <Badge tone="neutral">{t.guests.directory.notResident}</Badge>
              )}
              <Badge tone={p.is_repeat ? "info" : "neutral"}>
                {p.is_repeat ? t.guests.directory.repeat : t.guests.directory.firstTime}
              </Badge>
              {p.is_vip ? <Badge tone="vip"><Star size={12} aria-hidden /> {t.guests.vip.badge}</Badge> : null}
              {p.is_blocked ? <Badge tone="blocked">{t.guests.block.badge}</Badge> : null}
              {!p.is_active ? <Badge tone="neutral">{t.guests.inactive}</Badge> : null}
            </div>

            {p.is_blocked ? (
              <Alert tone="error">
                {t.guests.block.activeNotice}
                {p.block_reason ? ` — ${p.block_reason}` : ""}
                {p.blocked_by ? ` (${p.blocked_by}${p.blocked_at ? ` · ${formatDate(p.blocked_at, locale)}` : ""})` : ""}
              </Alert>
            ) : null}

            <div className="cluster">
              {can("guests.update") ? (
                <Button variant="secondary" size="sm" anim="edit" icon={Pencil} onClick={() => setEditing(true)} disabled={busy}>
                  {t.common.edit}
                </Button>
              ) : null}
              {can("guests.mark_vip") ? (
                <Button variant="ghost" size="sm" anim="vip" icon={Star} onClick={toggleVip} disabled={busy}>
                  {p.is_vip ? t.guests.vip.unmark : t.guests.vip.mark}
                </Button>
              ) : null}
              {can("guests.block") ? (
                p.is_blocked ? (
                  <Button variant="ghost" size="sm" icon={ShieldCheck} onClick={doUnblock} disabled={busy}>
                    {t.guests.block.unblock}
                  </Button>
                ) : (
                  <Button variant="dangerSoft" size="sm" anim="block" icon={Ban} onClick={() => setBlocking(true)} disabled={busy}>
                    {t.guests.block.block}
                  </Button>
                )
              ) : null}
              {can("guests.delete") ? (
                <Button variant="danger" size="sm" anim="delete" icon={Trash2} onClick={() => setDeleting(true)} disabled={busy}>
                  {t.common.delete}
                </Button>
              ) : null}
            </div>

            <dl className="detail-grid">
              <div><dt>{t.guests.form.phone}</dt><dd>{p.phone || "—"}</dd></div>
              <div><dt>{t.guests.form.email}</dt><dd>{p.email || "—"}</dd></div>
              <div><dt>{t.guests.form.nationality}</dt><dd>{p.nationality || "—"}</dd></div>
              <div><dt>{t.guests.form.documentType}</dt><dd>{p.document_type ? t.guests.documentTypes[p.document_type] : "—"}</dd></div>
              <div><dt>{t.guests.form.documentNumber}</dt><dd>{p.document_number || "—"}</dd></div>
              <div><dt>{t.guests.form.dateOfBirth}</dt><dd>{p.date_of_birth ? formatDate(p.date_of_birth, locale) : "—"}</dd></div>
            </dl>

            <dl className="profile-stats">
              <div><dt>{t.guests.directory.stays}</dt><dd>{p.stays_count}</dd></div>
              <div><dt>{t.guests.profile.nights}</dt><dd>{p.nights_total}</dd></div>
              <div><dt>{t.guests.profile.firstStay}</dt><dd>{p.first_stay_date ? formatDate(p.first_stay_date, locale) : "—"}</dd></div>
              <div><dt>{t.guests.directory.lastStay}</dt><dd>{p.last_stay_date ? formatDate(p.last_stay_date, locale) : "—"}</dd></div>
            </dl>

            {p.current ? (
              <Alert tone="info">
                <span className="cluster" style={{ gap: "0.5rem" }}>
                  <DoorOpen size={14} aria-hidden />
                  {t.guests.profile.currentStay}: {p.current.room_number}
                  {p.current.reservation_number ? ` · ${p.current.reservation_number}` : ""}
                  {can("stays.view") ? (
                    <Link className="inline-link" href="/hotel/front-desk?tab=current">{t.guests.profile.openFrontDesk}</Link>
                  ) : null}
                  {p.current.folio_number && can("finance.view") ? (
                    <Link className="inline-link" href="/hotel/finance?tab=folios">{t.guests.profile.openFolio} ({p.current.folio_number})</Link>
                  ) : null}
                </span>
              </Alert>
            ) : null}

            {p.notes ? (
              <div>
                <h4>{t.guests.form.notes}</h4>
                <p>{p.notes}</p>
              </div>
            ) : null}

            <div>
              <h4>{t.guests.profile.stayHistory}</h4>
              {p.stays.length === 0 ? (
                <p className="muted">{t.guests.profile.noStays}</p>
              ) : (
                <ul className="mini-list">
                  {p.stays.map((s) => (
                    <li key={s.stay_id} className="mini-list__row">
                      <span>
                        {s.room_number} · {s.room_type_name} · {formatDate(s.check_in_date, locale)} → {formatDate(s.check_out_date, locale)} · {s.nights} {t.frontDesk.current.nights}
                        {s.is_current ? <> <Badge tone="success">{t.guests.profile.currentBadge}</Badge></> : null}
                        {s.status === "cancelled" ? <> <Badge tone="neutral">{t.frontDesk.status.cancelled}</Badge></> : null}
                      </span>
                      <span className="cluster" style={{ gap: "0.5rem" }}>
                        {s.reservation_number && can("reservations.view") ? (
                          <Link className="inline-link" href={`/hotel/reservations?action=find&q=${s.reservation_number}`}>{s.reservation_number}</Link>
                        ) : null}
                        {s.folio_number && can("finance.view") ? (
                          <Link className="inline-link" href="/hotel/finance?tab=folios">{s.folio_number}</Link>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ) : null}
      </Modal>

      <GuestModal
        open={editing}
        guest={p ? {
          id: p.id,
          full_name: p.full_name,
          phone: p.phone,
          email: p.email,
          nationality: p.nationality,
          document_type: p.document_type,
          document_number: p.document_number,
          date_of_birth: p.date_of_birth,
          gender: p.gender,
          address: p.address,
          notes: p.notes,
          is_active: p.is_active,
          is_vip: p.is_vip,
          is_blocked: p.is_blocked,
          created_at: p.created_at,
          updated_at: p.updated_at,
        } : undefined}
        onClose={() => setEditing(false)}
        onSaved={() => { setEditing(false); notify(t.guests.saved); reload(); onChanged(); }}
      />

      <BlockGuestModal
        open={blocking}
        onClose={() => setBlocking(false)}
        onConfirm={async (reason) => {
          if (!p) return;
          setBusy(true);
          try {
            await blockGuest(p.id, reason);
            notify(t.guests.block.blockedToast);
            setBlocking(false);
            reload();
            onChanged();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setBusy(false);
          }
        }}
      />

      <ConfirmDialog
        open={deleting}
        title={t.guests.deleteTitle}
        body={t.guests.deleteBody}
        confirmLabel={t.common.delete}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        busy={busy}
        onConfirm={confirmDelete}
        onClose={() => setDeleting(false)}
      />
    </>
  );
}

// --------------------------------------------------------------------------- //
// Block modal (mandatory reason)                                              //
// --------------------------------------------------------------------------- //

function BlockGuestModal({
  open,
  onClose,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setReason("");
      setError(null);
    }
  }, [open]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return setError(t.guests.block.reasonRequired);
    onConfirm(reason.trim());
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.guests.block.title}
      closeLabel={t.common.close}
      tone="danger"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t.common.cancel}</Button>
          <Button form="block-form" type="submit" variant="danger" anim="block" icon={Ban}>{t.guests.block.block}</Button>
        </>
      }
    >
      <form id="block-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="warning">{t.guests.block.scopeNote}</Alert>
        <FormField label={t.guests.block.reason} htmlFor="block-reason">
          <Input id="block-reason" value={reason} onChange={(e) => setReason(e.target.value)} required />
        </FormField>
      </form>
    </Modal>
  );
}

// --------------------------------------------------------------------------- //
// Create / edit modal (basic profile data only)                               //
// --------------------------------------------------------------------------- //

function GuestModal({
  open,
  guest,
  onClose,
  onSaved,
}: {
  open: boolean;
  guest?: Guest;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState<GuestWriteBody>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // A masked document number must never round-trip back into the profile.
  const maskedDoc = Boolean(guest?.document_number?.includes("•"));

  useEffect(() => {
    if (!open) return;
    setForm({
      full_name: guest?.full_name ?? "",
      phone: guest?.phone ?? "",
      email: guest?.email ?? "",
      nationality: guest?.nationality ?? "",
      document_type: guest?.document_type ?? "",
      document_number: maskedDoc ? "" : guest?.document_number ?? "",
      date_of_birth: guest?.date_of_birth ?? null,
      gender: guest?.gender ?? "",
      address: guest?.address ?? "",
      notes: guest?.notes ?? "",
      is_active: guest?.is_active ?? true,
    });
    setError(null);
  }, [open, guest, maskedDoc]);

  function set<K extends keyof GuestWriteBody>(key: K, value: GuestWriteBody[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!form.full_name?.trim()) return setError(t.guests.form.nameRequired);
    const body: GuestWriteBody = {
      ...form,
      full_name: form.full_name.trim(),
      date_of_birth: form.date_of_birth || null,
    };
    // Untouched masked document: leave the stored number as-is.
    if (maskedDoc && !form.document_number) {
      delete body.document_number;
      delete body.document_type;
    }
    setBusy(true);
    try {
      if (guest) await updateGuest(guest.id, body);
      else await createGuest(body);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const docOptions = (["", "national_id", "passport", "driving_license", "other"] as const).map((v) => ({
    value: v,
    label: v === "" ? t.guests.documentTypes.none : t.guests.documentTypes[v],
  }));
  const genderOptions = (["", "male", "female", "other", "unspecified"] as const).map((v) => ({
    value: v,
    label: v === "" ? t.guests.genders.none : t.guests.genders[v],
  }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={guest ? t.guests.form.editTitle : t.guests.form.createTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="guest-form" type="submit" anim="save" loading={busy}>{t.common.save}</Button>
        </>
      }
    >
      <form id="guest-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.guests.form.fullName} htmlFor="g-name">
            <Input id="g-name" value={form.full_name ?? ""} required onChange={(e) => set("full_name", e.target.value)} />
          </FormField>
          <FormField label={t.guests.form.phone} htmlFor="g-phone">
            <Input id="g-phone" value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} />
          </FormField>
          <FormField label={t.guests.form.email} htmlFor="g-email">
            <Input id="g-email" type="email" value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} />
          </FormField>
          <FormField label={t.guests.form.nationality} htmlFor="g-nat">
            <Input id="g-nat" value={form.nationality ?? ""} onChange={(e) => set("nationality", e.target.value)} />
          </FormField>
          <FormField label={t.guests.form.documentType} htmlFor="g-doctype">
            <Select id="g-doctype" value={form.document_type ?? ""} options={docOptions} onChange={(e) => set("document_type", e.target.value as GuestWriteBody["document_type"])} />
          </FormField>
          <FormField label={t.guests.form.documentNumber} htmlFor="g-docnum">
            <Input
              id="g-docnum"
              value={form.document_number ?? ""}
              placeholder={maskedDoc ? guest?.document_number ?? "" : undefined}
              onChange={(e) => set("document_number", e.target.value)}
            />
          </FormField>
          <FormField label={t.guests.form.dateOfBirth} htmlFor="g-dob">
            <Input id="g-dob" type="date" value={form.date_of_birth ?? ""} onChange={(e) => set("date_of_birth", e.target.value || null)} />
          </FormField>
          <FormField label={t.guests.form.gender} htmlFor="g-gender">
            <Select id="g-gender" value={form.gender ?? ""} options={genderOptions} onChange={(e) => set("gender", e.target.value as GuestWriteBody["gender"])} />
          </FormField>
        </div>
        <FormField label={t.guests.form.address} htmlFor="g-addr">
          <Input id="g-addr" value={form.address ?? ""} onChange={(e) => set("address", e.target.value)} />
        </FormField>
        <FormField label={t.guests.form.notes} htmlFor="g-notes">
          <Textarea id="g-notes" value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} />
        </FormField>
        <Switch id="g-active" label={t.guests.form.active} checked={form.is_active ?? true} onChange={(v) => set("is_active", v)} />
      </form>
    </Modal>
  );
}
