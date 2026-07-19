"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  Archive,
  BedDouble,
  Check,
  Clock,
  FileText,
  HandCoins,
  MapPin,
  Package,
  PackageSearch,
  Plus,
  ShieldCheck,
  Undo2,
  User,
  UserCheck,
  XCircle,
} from "lucide-react";

import {
  Alert,
  Badge,
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
  SectionHeader,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  claimLostFoundItem,
  closeLostFoundItem,
  createLostFoundItem,
  disposeLostFoundItem,
  listLostFoundItems,
  returnLostFoundItem,
  setLostFoundStatus,
  type ClaimBody,
  type LostFoundCreateBody,
} from "@/lib/api/operations";
import { listGuests } from "@/lib/api/guests";
import { messageForError } from "@/lib/api/errors";
import type {
  Guest,
  LostFoundCategory,
  LostFoundClaimProofType,
  LostFoundItemListItem,
} from "@/lib/api/types";
import { formatDateTime, lostFoundStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { LostReportsSection } from "./LostReportsSection";
import { OperationCard, type OperationMenuItem } from "./OperationCard";
import { RoomOptionSelect } from "./RoomOptionSelect";
import { StatCards, type OperationStat } from "./StatCards";
import { isSensitiveCategory, useCan } from "./operationsShared";

const PAGE_SIZE = 25;
const CATEGORIES: LostFoundCategory[] = [
  "electronics",
  "documents",
  "clothing",
  "jewelry",
  "money",
  "luggage",
  "other",
];
const STATUSES = ["found", "stored", "claimed", "returned", "disposed", "closed"] as const;
const PROOF_TYPES: LostFoundClaimProofType[] = [
  "identity_last4",
  "receipt_reference",
  "ownership_description",
  "other",
];

type HandOverMode = "claim" | "return";

interface LfStats {
  found: number | null;
  stored: number | null;
  claimed: number | null;
  returned: number | null;
}

export function LostFoundTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const lf = t.operations.lf;
  const lr = t.operations.lr;
  const can = useCan();

  // WP10 hard invariant: still EXACTLY three tabs. A second RECORD KIND — the
  // guest-reported "lost report" cycle — lives INSIDE this tab, chosen by a
  // segmented type control (the type filter). "found" keeps the original UI
  // byte-stable; "lost_report" renders the self-contained LostReportsSection.
  const [recordType, setRecordType] = useState<"found" | "lost_report">("found");
  // The lost-report CREATE modal open flag lives here because its trigger button
  // sits in the shared type bar; the section renders the modal from this flag.
  const [lrCreateOpen, setLrCreateOpen] = useState(false);

  const [rows, setRows] = useState<LostFoundItemListItem[]>([]);
  const [count, setCount] = useState(0);
  const [stats, setStats] = useState<LfStats>({
    found: null,
    stored: null,
    claimed: null,
    returned: null,
  });
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Flips true after the FIRST settled load — the initial load owns the full
  // LoadingState / ErrorState, later fetches keep the cards mounted (a11y M1).
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const loadedOnceRef = useRef(false);
  const mountedRef = useRef(true);
  const seqRef = useRef(0);
  const resultsRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [handOver, setHandOver] = useState<{
    item: LostFoundItemListItem;
    mode: HandOverMode;
  } | null>(null);
  const [disposeItem, setDisposeItem] = useState<LostFoundItemListItem | null>(null);

  // Type-bar handlers — declared AFTER every useState they touch (setCreateOpen
  // included), so no state setter is referenced before its declaration (which
  // would defeat the React Compiler's memoization analysis).
  function selectFound() {
    setRecordType("found");
    setLrCreateOpen(false);
  }
  function selectLostReport() {
    setRecordType("lost_report");
  }
  function registerFound() {
    setRecordType("found");
    setLrCreateOpen(false);
    setCreateOpen(true);
  }
  function fileLostReport() {
    setRecordType("lost_report");
    setLrCreateOpen(true);
  }

  const load = useCallback(async () => {
    const seq = (seqRef.current += 1);
    setLoading(true);
    setError(null);
    try {
      const [items, found, stored, claimed, returned] = await Promise.all([
        listLostFoundItems({
          page,
          search: query || undefined,
          status: status || undefined,
          category: category || undefined,
        }),
        listLostFoundItems({ status: "found", page: 1 }),
        listLostFoundItems({ status: "stored", page: 1 }),
        listLostFoundItems({ status: "claimed", page: 1 }),
        listLostFoundItems({ status: "returned", page: 1 }),
      ]);
      if (seqRef.current !== seq) return;
      setRows(items.results);
      setCount(items.count);
      setStats({
        found: found.count,
        stored: stored.count,
        claimed: claimed.count,
        returned: returned.count,
      });
      loadedOnceRef.current = true;
      setHasLoadedOnce(true);
    } catch (err) {
      if (seqRef.current !== seq) return;
      const message = messageForError(err, t);
      // BACKGROUND refetch failure — keep the cards, surface a non-blocking toast;
      // the full ErrorState + retry is reserved for the initial load.
      if (loadedOnceRef.current) notify(message, "error");
      else setError(message);
    } finally {
      if (mountedRef.current && seqRef.current === seq) setLoading(false);
    }
  }, [page, query, status, category, t, notify]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // a11y M1 — after an ACTION-triggered reload settles, restore focus to the
  // stable results anchor if the acting control unmounted (focus fell to <body>
  // or a now-detached node). Keyed on `rows` (a fresh array on every successful
  // load) so it fires reliably even when React coalesces the loading toggle.
  useEffect(() => {
    if (loading || !restoreFocusRef.current) return;
    restoreFocusRef.current = false;
    const active = document.activeElement as HTMLElement | null;
    if (!active || active === document.body || !active.isConnected) {
      resultsRef.current?.focus();
    }
  }, [rows, loading]);

  const reloadAfterAction = useCallback(() => {
    restoreFocusRef.current = true;
    return load();
  }, [load]);

  async function run(id: number, action: () => Promise<unknown>, msg: string) {
    setBusyId(id);
    try {
      await action();
      notify(msg);
      await reloadAfterAction();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusyId(null);
    }
  }

  function applyStatusFilter(next: string) {
    setPage(1);
    setStatus((current) => (current === next ? "" : next));
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: lf.status[s] }));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: lf.categories[c] }));

  const statCards: OperationStat[] = [
    {
      key: "found",
      label: lf.stats.found,
      value: stats.found,
      icon: Package,
      tone: "warning",
      active: status === "found",
      onFilter: () => applyStatusFilter("found"),
    },
    {
      key: "stored",
      label: lf.stats.stored,
      value: stats.stored,
      icon: Archive,
      tone: "info",
      active: status === "stored",
      onFilter: () => applyStatusFilter("stored"),
    },
    {
      key: "claimed",
      label: lf.stats.claimed,
      value: stats.claimed,
      icon: HandCoins,
      tone: "primary",
      active: status === "claimed",
      onFilter: () => applyStatusFilter("claimed"),
    },
    {
      key: "returned",
      label: lf.stats.returned,
      value: stats.returned,
      icon: Undo2,
      tone: "success",
      active: status === "returned",
      onFilter: () => applyStatusFilter("returned"),
    },
  ];

  const showInitialLoading = loading && !hasLoadedOnce;
  const showInitialError = !showInitialLoading && !hasLoadedOnce && error !== null;
  const backgroundRefreshing = loading && hasLoadedOnce;
  const resultsAnnouncement =
    !loading && hasLoadedOnce
      ? count === 0
        ? t.operations.noResults
        : t.operations.resultsCount.replace("{count}", String(count))
      : "";

  function renderCard(row: LostFoundItemListItem) {
    const canStatus = can("lost_found.status_update");
    const sensitive = isSensitiveCategory(row.category);

    let primary: React.ComponentProps<typeof OperationCard>["primary"] = null;
    if (row.status === "found" && canStatus) {
      primary = {
        label: lf.store,
        icon: Archive,
        loading: busyId === row.id,
        onClick: () => run(row.id, () => setLostFoundStatus(row.id, "stored"), lf.storedMsg),
      };
    } else if ((row.status === "stored" || row.status === "claimed") && canStatus) {
      primary = {
        label: lf.returnItem,
        icon: Undo2,
        onClick: () => setHandOver({ item: row, mode: "return" }),
      };
    } else if ((row.status === "returned" || row.status === "disposed") && can("lost_found.close")) {
      primary = {
        label: lf.close,
        icon: Check,
        loading: busyId === row.id,
        onClick: () => run(row.id, () => closeLostFoundItem(row.id), lf.closedMsg),
      };
    }

    const menu: OperationMenuItem[] = [];
    if ((row.status === "found" || row.status === "stored") && canStatus) {
      menu.push({
        key: "claim",
        label: lf.claim,
        icon: HandCoins,
        onSelect: () => setHandOver({ item: row, mode: "claim" }),
      });
      if (row.status === "found") {
        menu.push({
          key: "return",
          label: lf.returnItem,
          icon: Undo2,
          onSelect: () => setHandOver({ item: row, mode: "return" }),
        });
      }
      menu.push({
        key: "dispose",
        label: lf.dispose,
        icon: XCircle,
        danger: true,
        onSelect: () => setDisposeItem(row),
      });
    }

    return (
      <OperationCard
        accent={lostFoundStatusTone(row.status)}
        number={row.item_number}
        title={row.title}
        note={row.description || null}
        ariaLabel={`${lf.title} ${row.item_number}`}
        moreLabel={t.operations.moreActions}
        badges={
          <>
            <Badge tone={lostFoundStatusTone(row.status)} variant="filled">
              {lf.status[row.status]}
            </Badge>
            <Badge tone="neutral">{lf.categories[row.category]}</Badge>
            {/* Record-kind badge (additive) — the found-item counterpart of the
                lost-report badge, so a merged view reads unambiguously. */}
            <Badge tone="neutral" variant="outline" icon={Package}>
              {lr.badge.found}
            </Badge>
            {sensitive ? (
              <Badge tone="warning" variant="outline" icon={ShieldCheck}>
                {lf.sensitive}
              </Badge>
            ) : null}
          </>
        }
        facts={[
          {
            key: "foundLocation",
            label: lf.foundLocation,
            value: row.found_location || (row.room_number ? <bdi dir="ltr">{row.room_number}</bdi> : "—"),
            icon: MapPin,
          },
          {
            key: "foundAt",
            label: lf.foundAt,
            value: formatDateTime(row.found_at, locale),
            icon: Clock,
          },
          ...(row.found_by_name
            ? [
                {
                  key: "finder",
                  label: lf.finder,
                  value: row.found_by_name,
                  icon: User,
                },
              ]
            : []),
          {
            key: "storedLocation",
            label: lf.storedLocation,
            value: row.stored_location || "—",
            icon: Archive,
          },
          ...(row.guest_name
            ? [{ key: "guest", label: lf.guest, value: row.guest_name, icon: User }]
            : []),
          ...(row.claimed_by_name
            ? [
                {
                  key: "claimant",
                  label: lf.claimant,
                  value: row.claimed_by_name,
                  icon: UserCheck,
                },
              ]
            : []),
          ...(row.room_number
            ? [
                {
                  key: "room",
                  label: lf.room,
                  value: <bdi dir="ltr">{row.room_number}</bdi>,
                  icon: BedDouble,
                },
              ]
            : []),
          ...(row.returned_at
            ? [
                {
                  key: "returned",
                  label: lf.status.returned,
                  value: formatDateTime(row.returned_at, locale),
                  icon: Undo2,
                },
              ]
            : []),
        ]}
        primary={primary}
        menu={menu}
      />
    );
  }

  return (
    <>
      {/* Shared type bar: the segmented TYPE FILTER (found ↔ lost report) plus
          BOTH primary register buttons (owner requirement), always visible when
          the user can create. Register buttons are relocated here from the found
          SectionHeader so both kinds are reachable from either sub-view. */}
      <div className="op-typebar">
        <div className="op-typebar__toggle" role="group" aria-label={lr.typeFilter.label}>
          <Button
            type="button"
            size="sm"
            variant={recordType === "found" ? "primary" : "secondary"}
            aria-pressed={recordType === "found"}
            onClick={selectFound}
          >
            {lr.typeFilter.found}
          </Button>
          <Button
            type="button"
            size="sm"
            variant={recordType === "lost_report" ? "primary" : "secondary"}
            aria-pressed={recordType === "lost_report"}
            onClick={selectLostReport}
          >
            {lr.typeFilter.lostReport}
          </Button>
        </div>
        {can("lost_found.create") ? (
          <div className="op-typebar__actions">
            {/* Emphasis follows the active sub-view: the register button for the
                current recordType is primary, the other secondary. Both always
                visible (owner requirement). */}
            <Button
              icon={Plus}
              variant={recordType === "found" ? "primary" : "secondary"}
              onClick={registerFound}
            >
              {lf.create}
            </Button>
            <Button
              icon={FileText}
              variant={recordType === "lost_report" ? "primary" : "secondary"}
              onClick={fileLostReport}
            >
              {lr.register}
            </Button>
          </div>
        ) : null}
      </div>

      {recordType === "lost_report" ? (
        <LostReportsSection
          createOpen={lrCreateOpen}
          onCreateClose={() => setLrCreateOpen(false)}
        />
      ) : (
        <>
      {/* The original FOUND-item body — kept byte-stable (only additive: the
          record badge in renderCard). Inlined in the type ternary so it keeps
          sharing the parent's state/effects with no remount. */}
      <StatCards stats={statCards} loading={loading} ariaLabel={lf.title} />

      <Card>
        <SectionHeader title={lf.title} />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            setQuery(search);
          }}
        >
          <FilterBar>
            <FormField label={t.common.search} htmlFor="lf-search">
              <Input
                id="lf-search"
                value={search}
                placeholder={lf.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
              />
            </FormField>
            <FormField label={t.common.status} htmlFor="lf-status">
              <Select
                id="lf-status"
                value={status}
                placeholder={t.common.all}
                options={statusOptions}
                onChange={(e) => {
                  setPage(1);
                  setStatus(e.target.value);
                }}
              />
            </FormField>
            <FormField label={lf.categoryLabel} htmlFor="lf-category">
              <Select
                id="lf-category"
                value={category}
                placeholder={t.common.all}
                options={categoryOptions}
                onChange={(e) => {
                  setPage(1);
                  setCategory(e.target.value);
                }}
              />
            </FormField>
          </FilterBar>
        </form>

        {/* STABLE polite live region — always mounted; announces the settled
            result count by a text change (a11y M1). */}
        <div
          className="sr-only"
          aria-live="polite"
          aria-atomic="true"
          data-testid="lf-results-announce"
        >
          {resultsAnnouncement}
        </div>

        {showInitialLoading ? <LoadingState label={t.common.loading} /> : null}
        {showInitialError ? (
          <ErrorState
            title={t.states.errorTitle}
            message={error ?? ""}
            retryLabel={t.common.retry}
            onRetry={load}
          />
        ) : null}
        {!showInitialLoading && !showInitialError ? (
          <div
            className="op-results"
            ref={resultsRef}
            tabIndex={-1}
            aria-label={lf.title}
          >
            <div className="op-results__status" role="status" aria-live="polite">
              {backgroundRefreshing ? (
                <span className="op-results__searching">
                  <span className="spinner" aria-hidden="true" />
                  <span>{t.operations.updating}</span>
                </span>
              ) : null}
            </div>
            {rows.length === 0 ? (
              <EmptyState title={lf.empty} hint={lf.emptyHint} icon={PackageSearch} />
            ) : (
              <>
                <div
                  className="op-grid"
                  role="list"
                  aria-label={lf.title}
                  aria-busy={backgroundRefreshing}
                >
                  {rows.map((row) => (
                    <div role="listitem" key={row.id}>
                      {renderCard(row)}
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
            )}
          </div>
        ) : null}
      </Card>

      <CreateItemModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSaved={() => {
          setCreateOpen(false);
          notify(lf.created);
          reloadAfterAction();
        }}
      />
      <HandOverModal
        state={handOver}
        onClose={() => setHandOver(null)}
        onDone={(mode) => {
          setHandOver(null);
          notify(mode === "claim" ? lf.claimedMsg : lf.returnedMsg);
          reloadAfterAction();
        }}
      />
      <DisposeModal
        item={disposeItem}
        onClose={() => setDisposeItem(null)}
        onDone={() => {
          setDisposeItem(null);
          notify(lf.disposedMsg);
          reloadAfterAction();
        }}
      />
        </>
      )}
    </>
  );
}

/**
 * Register a found item. Room uses the async room-options picker (§7); an
 * optional linked guest ties it to a stay/guest for later handover.
 */
export function CreateItemModal({
  open,
  presetRoom,
  presetRoomLabel,
  onClose,
  onSaved,
}: {
  open: boolean;
  presetRoom?: number;
  presetRoomLabel?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const lf = t.operations.lf;
  const [form, setForm] = useState<LostFoundCreateBody>({ title: "" });
  const [guests, setGuests] = useState<Guest[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ title: "", description: "", category: "other", room: presetRoom ?? null });
      setError(null);
      listGuests({ page_size: 100 })
        .then((res) => setGuests(res.results))
        .catch(() => setGuests([]));
    }
  }, [open, presetRoom]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.title.trim()) return setError(lf.titleRequired);
    setBusy(true);
    setError(null);
    try {
      await createLostFoundItem(form);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const guestOptions = guests.map((g) => ({ value: String(g.id), label: g.full_name }));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: lf.categories[c] }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={lf.create}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="lf-create-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="lf-create-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={lf.titleLabel} htmlFor="lfc-title">
          <Input
            id="lfc-title"
            value={form.title}
            onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))}
          />
        </FormField>
        <FormField label={lf.description} htmlFor="lfc-desc">
          <Textarea
            id="lfc-desc"
            rows={2}
            value={form.description ?? ""}
            onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
          />
        </FormField>
        <div className="form-grid">
          <FormField label={lf.categoryLabel} htmlFor="lfc-category">
            <Select
              id="lfc-category"
              value={form.category ?? "other"}
              options={categoryOptions}
              onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}
            />
          </FormField>
          <FormField label={lf.foundLocation} htmlFor="lfc-floc">
            <Input
              id="lfc-floc"
              value={form.found_location ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, found_location: e.target.value }))}
            />
          </FormField>
          <FormField label={lf.storedLocation} htmlFor="lfc-sloc">
            <Input
              id="lfc-sloc"
              value={form.stored_location ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, stored_location: e.target.value }))}
            />
          </FormField>
          <FormField label={lf.guest} htmlFor="lfc-guest">
            <Select
              id="lfc-guest"
              value={form.guest ? String(form.guest) : ""}
              placeholder={lf.noGuest}
              options={guestOptions}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  guest: e.target.value ? Number(e.target.value) : null,
                }))
              }
            />
          </FormField>
        </div>
        <RoomOptionSelect
          id="lfc-room"
          label={lf.room}
          value={form.room ?? null}
          placeholder={lf.noRoom}
          searchPlaceholder={t.operations.roomSearchPlaceholder}
          loadMoreLabel={t.operations.loadMore}
          loadingLabel={t.common.loading}
          emptyLabel={t.operations.roomsEmpty}
          selectedLabel={presetRoomLabel}
          onChange={(next) => setForm((p) => ({ ...p, room: next }))}
        />
        <FormField label={lf.notes} htmlFor="lfc-notes">
          <Input
            id="lfc-notes"
            value={form.notes ?? ""}
            onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
          />
        </FormField>
      </form>
    </Modal>
  );
}

/**
 * Handover (claim / return). NORMAL categories require a recipient name plus a
 * phone OR a linked guest. SENSITIVE categories (money / jewelry / documents)
 * additionally require a proof type + reference — the proof fields are shown
 * ONLY for sensitive items. The phone + proof reference are entered here (for an
 * authorized user) and are never rendered on the card/list. A backend 422
 * `claim_proof_required` surfaces as a clear translated error.
 */
function HandOverModal({
  state,
  onClose,
  onDone,
}: {
  state: { item: LostFoundItemListItem; mode: HandOverMode } | null;
  onClose: () => void;
  onDone: (mode: HandOverMode) => void;
}) {
  const { t } = useI18n();
  const lf = t.operations.lf;
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [proofType, setProofType] = useState<LostFoundClaimProofType>("identity_last4");
  const [proofReference, setProofReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const item = state?.item ?? null;
  const sensitive = item ? isSensitiveCategory(item.category) : false;
  const hasLinkedGuest = item?.guest !== null && item?.guest !== undefined;

  useEffect(() => {
    if (state) {
      setName("");
      setPhone("");
      setProofType("identity_last4");
      setProofReference("");
      setError(null);
    }
  }, [state]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!state) return;
    // NORMAL: recipient name is always required; a phone is required unless the
    // item is tied to a linked guest (phone-OR-linked-guest).
    if (!name.trim()) return setError(t.operations.errors.claimantRequired);
    if (!phone.trim() && !hasLinkedGuest) return setError(t.operations.errors.claimantRequired);
    if (sensitive && (!proofType || !proofReference.trim())) {
      return setError(lf.proofRequired);
    }
    setBusy(true);
    setError(null);
    try {
      const body: ClaimBody = {
        claimed_by_name: name.trim(),
        claimed_by_phone: phone.trim(),
        ...(sensitive
          ? { claim_proof_type: proofType, claim_proof_reference: proofReference.trim() }
          : {}),
      };
      if (state.mode === "claim") await claimLostFoundItem(state.item.id, body);
      else await returnLostFoundItem(state.item.id, body);
      onDone(state.mode);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const isClaim = state?.mode === "claim";
  const proofOptions = PROOF_TYPES.map((p) => ({ value: p, label: lf.proofTypes[p] }));

  return (
    <Modal
      open={state !== null}
      onClose={onClose}
      title={isClaim ? lf.claimTitle : lf.returnTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="lf-handover-form" type="submit" loading={busy}>
            {isClaim ? lf.claim : lf.returnItem}
          </Button>
        </>
      }
    >
      <form id="lf-handover-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <p className="muted">{isClaim ? lf.claimHint : lf.returnHint}</p>
        {hasLinkedGuest ? (
          <Alert tone="info">
            {lf.linkedGuest}
            {item?.guest_name ? `: ${item.guest_name}` : ""}
          </Alert>
        ) : null}
        <div className="form-grid">
          <FormField label={lf.recipientName} htmlFor="lf-ho-name">
            <Input id="lf-ho-name" value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField label={lf.recipientPhone} htmlFor="lf-ho-phone">
            <Input
              id="lf-ho-phone"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </FormField>
        </div>
        <p className="muted small">{lf.handoverContactHint}</p>
        {sensitive ? (
          <>
            <Alert tone="warning">{lf.sensitiveHint}</Alert>
            <div className="form-grid">
              <FormField label={lf.proofTypeLabel} htmlFor="lf-ho-prooftype">
                <Select
                  id="lf-ho-prooftype"
                  value={proofType}
                  options={proofOptions}
                  onChange={(e) =>
                    setProofType(e.target.value as LostFoundClaimProofType)
                  }
                />
              </FormField>
              <FormField label={lf.proofReference} htmlFor="lf-ho-proofref">
                <Input
                  id="lf-ho-proofref"
                  value={proofReference}
                  onChange={(e) => setProofReference(e.target.value)}
                />
              </FormField>
            </div>
          </>
        ) : null}
      </form>
    </Modal>
  );
}

function DisposeModal({
  item,
  onClose,
  onDone,
}: {
  item: LostFoundItemListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const lf = t.operations.lf;
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (item) {
      setReason("");
      setError(null);
    }
  }, [item]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!item) return;
    if (!reason.trim()) return setError(t.errors.validation);
    setBusy(true);
    setError(null);
    try {
      await disposeLostFoundItem(item.id, reason.trim());
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={item !== null}
      onClose={onClose}
      title={lf.disposeTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="lf-dispose-form" type="submit" variant="danger" loading={busy}>
            {lf.dispose}
          </Button>
        </>
      }
    >
      <form id="lf-dispose-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={lf.disposeReason} htmlFor="lf-dispose-reason">
          <Input
            id="lf-dispose-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}
