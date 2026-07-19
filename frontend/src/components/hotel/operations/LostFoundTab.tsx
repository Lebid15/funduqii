"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  Archive,
  BedDouble,
  Check,
  Clock,
  HandCoins,
  MapPin,
  Package,
  PackageSearch,
  Plus,
  ShieldCheck,
  Undo2,
  User,
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
  const can = useCan();

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
  const [busyId, setBusyId] = useState<number | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [handOver, setHandOver] = useState<{
    item: LostFoundItemListItem;
    mode: HandOverMode;
  } | null>(null);
  const [disposeItem, setDisposeItem] = useState<LostFoundItemListItem | null>(null);

  const load = useCallback(async () => {
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
      setRows(items.results);
      setCount(items.count);
      setStats({
        found: found.count,
        stored: stored.count,
        claimed: claimed.count,
        returned: returned.count,
      });
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, query, status, category, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(id: number, action: () => Promise<unknown>, msg: string) {
    setBusyId(id);
    try {
      await action();
      notify(msg);
      await load();
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
        ariaLabel={`${lf.title} ${row.item_number}`}
        moreLabel={t.operations.moreActions}
        badges={
          <>
            <Badge tone={lostFoundStatusTone(row.status)} variant="filled">
              {lf.status[row.status]}
            </Badge>
            <Badge tone="neutral">{lf.categories[row.category]}</Badge>
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
          {
            key: "storedLocation",
            label: lf.storedLocation,
            value: row.stored_location || "—",
            icon: Archive,
          },
          ...(row.guest_name
            ? [{ key: "guest", label: lf.guest, value: row.guest_name, icon: User }]
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
      <StatCards stats={statCards} loading={loading} ariaLabel={lf.title} />

      <Card>
        <SectionHeader
          title={lf.title}
          actions={
            can("lost_found.create") ? (
              <Button icon={Plus} onClick={() => setCreateOpen(true)}>
                {lf.create}
              </Button>
            ) : null
          }
        />
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
            <EmptyState title={lf.empty} hint={lf.emptyHint} icon={PackageSearch} />
          ) : (
            <>
              <div className="op-grid" role="list" aria-label={lf.title}>
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
          )
        ) : null}
      </Card>

      <CreateItemModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSaved={() => {
          setCreateOpen(false);
          notify(lf.created);
          load();
        }}
      />
      <HandOverModal
        state={handOver}
        onClose={() => setHandOver(null)}
        onDone={(mode) => {
          setHandOver(null);
          notify(mode === "claim" ? lf.claimedMsg : lf.returnedMsg);
          load();
        }}
      />
      <DisposeModal
        item={disposeItem}
        onClose={() => setDisposeItem(null)}
        onDone={() => {
          setDisposeItem(null);
          notify(lf.disposedMsg);
          load();
        }}
      />
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
