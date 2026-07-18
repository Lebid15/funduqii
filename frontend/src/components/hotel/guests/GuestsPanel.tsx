"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
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

/** Live-search debounce: results refetch this long after the last keystroke, so
 * a fast typist never fires a request per character. */
const SEARCH_DEBOUNCE_MS = 350;

/** True when a rejection is a fetch AbortError (a superseded live-search request
 * we deliberately cancelled). Such a rejection must be SWALLOWED — never shown as
 * an error state — because a newer request is already in flight. */
function isAbortError(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    (err as { name?: unknown }).name === "AbortError"
  );
}

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
  // Flips true after the FIRST settled (successful) directory load. It draws the
  // line between the INITIAL load — which owns the full-screen LoadingState /
  // ErrorState — and every later BACKGROUND fetch (live search, filter toggle,
  // page change, post-mutation refresh), which keeps the current view mounted and
  // only shows the subtle inline cue. So a fast typist never sees a full-loader
  // flicker and a transient refetch error never wipes good results.
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
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

  // The in-flight directory request. A new load (typed search, filter toggle,
  // page change, post-mutation refresh) ABORTS the previous one so a stale
  // response can never overwrite a newer one, and the loading flag is owned only
  // by the latest request.
  const requestRef = useRef<AbortController | null>(null);
  // Ref mirror of `hasLoadedOnce`, read INSIDE the async catch so the initial-vs-
  // background decision is never made from a stale closure value.
  const loadedOnceRef = useRef(false);
  // Guards the terminal `setLoading(false)` against a just-unmounted panel (a
  // React 18 no-op today, but explicit and future-proof).
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const data = await listGuestDirectory(
        {
          page,
          search: query || undefined,
          is_active: showInactive ? undefined : "true",
        },
        controller.signal,
      );
      // Stale-response guard: only the LATEST request may write rows/count.
      if (requestRef.current === controller) {
        setRows(data.results);
        setCount(data.count);
        // First settled load: from here on a failure is a BACKGROUND error and
        // the full-screen loader/error are reserved for the initial load only.
        loadedOnceRef.current = true;
        setHasLoadedOnce(true);
      }
    } catch (err) {
      // A deliberately cancelled (superseded) request is not an error.
      if (isAbortError(err)) return;
      if (requestRef.current !== controller) return;
      const message = messageForError(err, t);
      if (loadedOnceRef.current) {
        // BACKGROUND refetch failure — rows are already on screen. Surface it
        // NON-BLOCKINGLY via a toast and keep the current cards mounted; never
        // swap the visible list for the full-screen ErrorState mid-typing.
        notify(message, "error");
      } else {
        // INITIAL load failure (nothing shown yet) — the full ErrorState + retry.
        setError(message);
      }
    } finally {
      // Only the newest request clears the loading flag, so an aborted older
      // request can never flip the spinner off under the request that replaced it;
      // the mounted guard skips the no-op write after the panel has unmounted.
      if (mountedRef.current && requestRef.current === controller) {
        setLoading(false);
      }
    }
  }, [page, query, showInactive, t, notify]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    load();
    return () => requestRef.current?.abort();
  }, [load]);

  // LIVE SEARCH — debounce the applied term. When the input differs from the
  // applied `query`, wait out the debounce then apply it AND reset to page 1
  // (clearing the box drops back to the full list the same way). `showInactive`
  // is untouched here, so the current filter is preserved across searches. Enter
  // (applySearch) short-circuits this by applying the term synchronously.
  useEffect(() => {
    if (search === query) return;
    const id = setTimeout(() => {
      setPage(1);
      setQuery(search);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [search, query]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  // Full-screen loader / error are reserved for the INITIAL load (before the
  // first successful settle) — gated on `hasLoadedOnce`, NOT on `rows.length`, so
  // a zero-result search after a first load keeps the EmptyState (never the full
  // loader) and every later fetch keeps the current view + the subtle inline cue.
  const showInitialLoading = loading && !hasLoadedOnce;
  const showInitialError = !showInitialLoading && !hasLoadedOnce && error !== null;
  const backgroundRefreshing = loading && hasLoadedOnce;

  // FIX C (WCAG 4.1.3) — content of the stable polite live region. Announce the
  // SETTLED result state only: blank while a fetch is in flight (the "searching…"
  // busy cue owns that) and blank before the first successful load, so the text
  // changes exactly once per settled, debounced search — never per keystroke.
  const resultsAnnouncement =
    !loading && hasLoadedOnce
      ? count === 0
        ? t.guests.list.noResults
        : t.guests.list.resultsCount.replace("{count}", String(count))
      : "";

  function applySearch(event: FormEvent) {
    event.preventDefault();
    // Enter is an OPTIONAL shortcut that applies the current term immediately
    // (the debounced effect otherwise applies it on its own).
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

      {/* FIX C — STABLE polite live region: mounted for the panel's whole life
          (even during the initial load / error), so assistive tech announces the
          settled result count by a TEXT CHANGE, never by mounting-with-content.
          It stays blank while a fetch is in flight and updates once the debounced
          search settles. */}
      <div
        className="sr-only"
        aria-live="polite"
        aria-atomic="true"
        data-testid="guest-results-announce"
      >
        {resultsAnnouncement}
      </div>

      {showInitialLoading ? <LoadingState label={t.common.loading} /> : null}
      {showInitialError ? (
        <ErrorState title={t.states.errorTitle} message={error ?? ""} retryLabel={t.common.retry} onRetry={load} />
      ) : null}
      {!showInitialLoading && !showInitialError ? (
        <div className="guest-results">
          {/* FIX D — the background-refetch cue lives in an ALWAYS-present status
              row with a reserved height, so its show/hide never reflows the grid
              or EmptyState below it (no vertical jump on live search). role=status
              keeps it a polite busy region for the in-flight state. */}
          <div className="guest-results__status" role="status" aria-live="polite">
            {backgroundRefreshing ? (
              <span className="guest-results__searching">
                <span className="spinner" aria-hidden="true" />
                <span>{t.guests.list.searching}</span>
              </span>
            ) : null}
          </div>

          {rows.length === 0 ? (
            <EmptyState
              title={t.guests.directory.empty}
              hint={t.guests.directory.emptyHint}
              icon={Users}
            />
          ) : (
            <>
              <div
                className="guest-grid"
                role="list"
                aria-label={t.guests.title}
                aria-busy={backgroundRefreshing}
              >
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
          )}
        </div>
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
