"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Archive, PackageSearch, Plus } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
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
  type Column,
} from "@/components/ui";
import {
  claimLostFoundItem,
  closeLostFoundItem,
  createLostFoundItem,
  disposeLostFoundItem,
  listLostFoundItems,
  returnLostFoundItem,
  setLostFoundStatus,
  type LostFoundCreateBody,
} from "@/lib/api/operations";
import { listGuests } from "@/lib/api/guests";
import { listRooms } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type {
  Guest,
  LostFoundCategory,
  LostFoundItemListItem,
  Room,
} from "@/lib/api/types";
import { formatDateTime, lostFoundStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

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

type HandOverMode = "claim" | "return";

export function LostFoundTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const lf = t.operations.lf;

  const [rows, setRows] = useState<LostFoundItemListItem[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [count, setCount] = useState(0);
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
  const [closeItem, setCloseItem] = useState<LostFoundItemListItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [items, roomList] = await Promise.all([
        listLostFoundItems({
          page,
          search: query || undefined,
          status: status || undefined,
          category: category || undefined,
        }),
        listRooms({ page_size: 100 }),
      ]);
      setRows(items.results);
      setCount(items.count);
      setRooms(roomList.results);
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

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: lf.status[s] }));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: lf.categories[c] }));

  const columns: Column<LostFoundItemListItem>[] = [
    { key: "item_number", header: lf.itemNumber },
    { key: "title", header: lf.titleLabel },
    { key: "category", header: lf.categoryLabel, render: (r) => lf.categories[r.category] },
    {
      key: "status",
      header: t.common.status,
      render: (r) => (
        <Badge tone={lostFoundStatusTone(r.status)}>{lf.status[r.status]}</Badge>
      ),
    },
    {
      key: "found_at",
      header: lf.foundAt,
      render: (r) => formatDateTime(r.found_at, locale),
    },
    {
      key: "found_location",
      header: lf.foundLocation,
      render: (r) => r.found_location || r.room_number || "—",
    },
    {
      key: "guest_name",
      header: lf.guest,
      render: (r) => r.guest_name || "—",
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => {
        if (r.status === "returned" || r.status === "disposed") {
          return (
            <div className="table__actions">
              <Button size="sm" variant="secondary" onClick={() => setCloseItem(r)}>
                {lf.close}
              </Button>
            </div>
          );
        }
        if (r.status === "claimed") {
          return (
            <div className="table__actions">
              <Button size="sm" onClick={() => setHandOver({ item: r, mode: "return" })}>
                {lf.returnItem}
              </Button>
            </div>
          );
        }
        if (r.status === "found" || r.status === "stored") {
          return (
            <div className="table__actions">
              {r.status === "found" ? (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={Archive}
                  loading={busyId === r.id}
                  onClick={() =>
                    run(r.id, () => setLostFoundStatus(r.id, "stored"), lf.storedMsg)
                  }
                >
                  {lf.store}
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setHandOver({ item: r, mode: "claim" })}
              >
                {lf.claim}
              </Button>
              <Button size="sm" onClick={() => setHandOver({ item: r, mode: "return" })}>
                {lf.returnItem}
              </Button>
              <Button size="sm" variant="danger" onClick={() => setDisposeItem(r)}>
                {lf.dispose}
              </Button>
            </div>
          );
        }
        return <span className="muted small">—</span>;
      },
    },
  ];

  return (
    <>
      <Card>
        <SectionHeader
          title={lf.title}
          actions={
            <Button icon={Plus} onClick={() => setCreateOpen(true)}>
              {lf.create}
            </Button>
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
              <DataTable
                caption={lf.title}
                columns={columns}
                rows={rows}
                rowKey={(r) => r.id}
              />
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
        rooms={rooms}
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
      <ConfirmDialog
        open={closeItem !== null}
        title={lf.close}
        body={lf.closedMsg}
        confirmLabel={lf.close}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        onClose={() => setCloseItem(null)}
        onConfirm={async () => {
          if (!closeItem) return;
          try {
            await closeLostFoundItem(closeItem.id);
            notify(lf.closedMsg);
            load();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setCloseItem(null);
          }
        }}
      />
    </>
  );
}

function CreateItemModal({
  open,
  rooms,
  onClose,
  onSaved,
}: {
  open: boolean;
  rooms: Room[];
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
      setForm({ title: "", description: "", category: "other" });
      setError(null);
      listGuests({ page_size: 100 })
        .then((res) => setGuests(res.results))
        .catch(() => setGuests([]));
    }
  }, [open]);

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

  const roomOptions = rooms.map((r) => ({ value: String(r.id), label: r.number }));
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
              onChange={(e) =>
                setForm((p) => ({ ...p, stored_location: e.target.value }))
              }
            />
          </FormField>
          <FormField label={lf.room} htmlFor="lfc-room">
            <Select
              id="lfc-room"
              value={form.room ? String(form.room) : ""}
              placeholder={lf.noRoom}
              options={roomOptions}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  room: e.target.value ? Number(e.target.value) : null,
                }))
              }
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
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (state) {
      setName("");
      setPhone("");
      setError(null);
    }
  }, [state]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!state) return;
    setBusy(true);
    setError(null);
    try {
      const body = { claimed_by_name: name.trim(), claimed_by_phone: phone.trim() };
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
        <div className="form-grid">
          <FormField label={lf.claimedBy} htmlFor="lf-ho-name">
            <Input id="lf-ho-name" value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField label={lf.claimedByPhone} htmlFor="lf-ho-phone">
            <Input
              id="lf-ho-phone"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </FormField>
        </div>
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
