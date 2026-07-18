"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Users } from "lucide-react";

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
  Switch,
  Textarea,
  useToast,
} from "@/components/ui";
import { GuestCard } from "./GuestCard";
import {
  blockGuest,
  getGuestProfile,
  listGuestDirectory,
  setGuestVip,
  unblockGuest,
  updateGuest,
  type GuestWriteBody,
} from "@/lib/api/guests";
import { messageForError } from "@/lib/api/errors";
import type { Guest, GuestDirectoryRow, GuestProfile } from "@/lib/api/types";
import { isMaskedValue } from "./guestFormat";
import {
  GuestChangeLogModal,
  GuestDocumentsModal,
  GuestReservationsHistoryModal,
  GuestStaysHistoryModal,
} from "./GuestRecordModals";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useI18n } from "@/lib/i18n/I18nProvider";

const PAGE_SIZE = 25;

/** Which read-only record sub-modal is open for a guest. */
type RecordKind = "stays" | "reservations" | "documents" | "changeLog";

/** The minimal identity a record opener needs (satisfied by both a directory row
 * and a full profile). */
type GuestRef = { id: number; full_name: string };

/** Cosmetic permission gate — every API re-checks server-side regardless. */
function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

export function GuestsPanel() {
  const { t } = useI18n();
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
  // The guest whose personal-data edit modal is open (opened DIRECTLY by the card
  // pencil — there is no comprehensive profile step). The full personal record is
  // fetched lazily by GuestEditModal from its id.
  const [editId, setEditId] = useState<number | null>(null);
  const [blockTarget, setBlockTarget] = useState<GuestDirectoryRow | null>(null);
  // The one guest whose inline VIP/ban action is in flight — disables that card's
  // mutating buttons so a slow request cannot be double-fired.
  const [busyId, setBusyId] = useState<number | null>(null);
  // The record sub-modal currently open (stays / reservations / documents /
  // change-log) for a specific guest. Opened from a GuestCard icon OR a profile
  // button; each sub-modal renders only for its own kind.
  const [record, setRecord] = useState<{
    kind: RecordKind;
    id: number;
    name: string;
  } | null>(null);

  const openRecord = (kind: RecordKind) => (g: GuestRef) =>
    setRecord({ kind, id: g.id, name: g.full_name });
  const openStays = openRecord("stays");
  const openReservations = openRecord("reservations");
  const openDocuments = openRecord("documents");
  const openChangeLog = openRecord("changeLog");
  const closeRecord = () => setRecord(null);

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
    // The term is forwarded verbatim to the directory endpoint, which does the
    // matching server-side (name / phone / national_id — an EXACT national_id
    // match is supported). The client never interprets it.
    setQuery(search);
  }

  const openEdit = (g: GuestDirectoryRow) => setEditId(g.id);

  async function toggleVip(g: GuestDirectoryRow) {
    setBusyId(g.id);
    try {
      await setGuestVip(g.id, !g.is_vip);
      notify(t.guests.saved);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusyId(null);
    }
  }

  async function handleBlock(g: GuestDirectoryRow) {
    // Blocking needs a mandatory reason (BlockGuestModal); unblocking is one step.
    if (!g.is_blocked) {
      setBlockTarget(g);
      return;
    }
    setBusyId(g.id);
    try {
      await unblockGuest(g.id);
      notify(t.guests.block.unblocked);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <Card>
        <form onSubmit={applySearch}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="guest-search" hint={t.guests.list.searchHint}>
              <Input id="guest-search" value={search} placeholder={t.guests.list.searchPlaceholder} onChange={(e) => setSearch(e.target.value)} />
            </FormField>
            <div className="filter-bar__actions cluster">
              <Switch id="guest-inactive" label={t.guests.list.showInactive} checked={showInactive} onChange={(v) => { setPage(1); setShowInactive(v); }} />
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
              {rows.map((g) => (
                <div role="listitem" key={g.id}>
                  <GuestCard
                    guest={g}
                    can={can}
                    busy={busyId === g.id}
                    onEdit={openEdit}
                    onToggleVip={toggleVip}
                    onBlock={handleBlock}
                    /* The four record sub-modals open DIRECTLY from the card. Each
                       button renders only when its callback is supplied (and, for
                       documents, GuestCard additionally gates on
                       reservation_documents.view), so gating happens here. */
                    onStays={can("stays.view") ? openStays : undefined}
                    onReservations={
                      can("reservations.view") ? openReservations : undefined
                    }
                    onDocuments={
                      can("reservation_documents.view") ? openDocuments : undefined
                    }
                    onChangeLog={openChangeLog}
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
                status: t.pagination.page.replace("{page}", String(page)).replace("{total}", String(totalPages)),
              }}
            />
          </>
        )
      ) : null}

      <GuestEditModal
        guestId={editId}
        onClose={() => setEditId(null)}
        onSaved={() => { setEditId(null); notify(t.guests.saved); load(); }}
      />

      <BlockGuestModal
        open={blockTarget !== null}
        onClose={() => setBlockTarget(null)}
        onConfirm={async (reason) => {
          if (!blockTarget) return;
          setBusyId(blockTarget.id);
          try {
            await blockGuest(blockTarget.id, reason);
            notify(t.guests.block.blockedToast);
            setBlockTarget(null);
            await load();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setBusyId(null);
          }
        }}
      />

      {/* W6b — the four read-only record sub-modals. Each opens only for its own
          kind; the guest id/name come from whichever card or profile button fired
          it. All four re-check RBAC server-side (documents also client-gates). */}
      <GuestStaysHistoryModal
        open={record?.kind === "stays"}
        guestId={record?.kind === "stays" ? record.id : null}
        guestName={record?.name ?? ""}
        onClose={closeRecord}
      />
      <GuestReservationsHistoryModal
        open={record?.kind === "reservations"}
        guestId={record?.kind === "reservations" ? record.id : null}
        guestName={record?.name ?? ""}
        onClose={closeRecord}
      />
      <GuestDocumentsModal
        open={record?.kind === "documents"}
        guestId={record?.kind === "documents" ? record.id : null}
        guestName={record?.name ?? ""}
        onClose={closeRecord}
      />
      <GuestChangeLogModal
        open={record?.kind === "changeLog"}
        guestId={record?.kind === "changeLog" ? record.id : null}
        guestName={record?.name ?? ""}
        onClose={closeRecord}
      />
    </>
  );
}

// --------------------------------------------------------------------------- //
// Edit-modal loader (fetches the guest's personal record, opens the form)      //
// --------------------------------------------------------------------------- //

/**
 * Opens the PERSONAL-DATA edit form for a guest, fetched lazily by id. The
 * comprehensive profile modal was removed (owner decision: the card IS the guest
 * interface), so the card pencil now opens this form DIRECTLY. It fetches the
 * guest's full personal record (`getGuestProfile` already carries every editable
 * field) purely to SEED the form — it renders NO reservations / stays / folio /
 * documents / change-log. A masked document number is never echoed back on save
 * (the form omits it — see GuestModal).
 */
function GuestEditModal({
  guestId,
  onClose,
  onSaved,
}: {
  guestId: number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [guest, setGuest] = useState<GuestProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const open = guestId !== null;

  useEffect(() => {
    setGuest(null);
    setError(null);
    if (guestId === null) return;
    let cancelled = false;
    getGuestProfile(guestId)
      .then((p) => {
        if (!cancelled) setGuest(p);
      })
      .catch((err) => {
        if (!cancelled) setError(messageForError(err, t));
      });
    return () => {
      cancelled = true;
    };
  }, [guestId, t]);

  if (!open) return null;

  // Once the personal record has loaded, hand off to the shared edit form (which
  // owns its own Modal). Until then — or on a load error — show a light framing
  // Modal so the interaction always has an anchored, dismissible surface.
  if (guest) {
    return (
      <GuestModal
        open
        guest={{
          id: guest.id,
          full_name: guest.full_name,
          phone: guest.phone,
          email: guest.email,
          nationality: guest.nationality,
          document_type: guest.document_type,
          document_number: guest.document_number,
          date_of_birth: guest.date_of_birth,
          gender: guest.gender,
          address: guest.address,
          notes: guest.notes,
          is_active: guest.is_active,
          is_vip: guest.is_vip,
          is_blocked: guest.is_blocked,
          created_at: guest.created_at,
          updated_at: guest.updated_at,
        }}
        onClose={onClose}
        onSaved={onSaved}
      />
    );
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={t.guests.form.editTitle}
      closeLabel={t.common.close}
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t.common.close}
        </Button>
      }
    >
      {error ? (
        <Alert tone="error">{error}</Alert>
      ) : (
        <LoadingState label={t.common.loading} />
      )}
    </Modal>
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
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t.common.cancel}</Button>
          <Button form="block-form" type="submit" variant="danger">{t.guests.block.block}</Button>
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
  /** Edit-only (GUESTS-CLOSURE Decision 9): standalone guest creation was
   * removed — a profile is always supplied. */
  guest: Guest;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState<GuestWriteBody>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // A masked document number must never round-trip back into the profile.
  const maskedDoc = isMaskedValue(guest.document_number);

  useEffect(() => {
    if (!open) return;
    setForm({
      full_name: guest.full_name,
      phone: guest.phone,
      email: guest.email,
      nationality: guest.nationality,
      document_type: guest.document_type,
      document_number: maskedDoc ? "" : guest.document_number,
      date_of_birth: guest.date_of_birth,
      gender: guest.gender,
      address: guest.address,
      notes: guest.notes,
      is_active: guest.is_active,
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
      await updateGuest(guest.id, body);
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
      title={t.guests.form.editTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="guest-form" type="submit" loading={busy}>{t.common.save}</Button>
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
              placeholder={maskedDoc ? guest.document_number : undefined}
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
