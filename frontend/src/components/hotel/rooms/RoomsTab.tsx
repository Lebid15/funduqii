"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { BedDouble, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";

import {
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
  Pagination,
  SectionHeader,
  Select,
  Switch,
  useToast,
} from "@/components/ui";
import { cx } from "@/lib/utils";
import { deleteRoom, listFloors, listRoomTypes, listRooms } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type { Floor, Room, RoomStatus, RoomType } from "@/lib/api/types";
import { roomStatusLabel, roomStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { RoomFormModal } from "./RoomFormModal";
import { RoomStatusModal } from "./RoomStatusModal";

const PAGE_SIZE = 25;
const STATUSES: RoomStatus[] = [
  "available",
  "dirty",
  "cleaning",
  "maintenance",
  "out_of_service",
  "archived",
];

export function RoomsTab() {
  const { t } = useI18n();
  const { notify } = useToast();

  const [floors, setFloors] = useState<Floor[]>([]);
  const [types, setTypes] = useState<RoomType[]>([]);
  const [rows, setRows] = useState<Room[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [floor, setFloor] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Room | null>(null);
  const [statusTarget, setStatusTarget] = useState<Room | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Room | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [f, ty] = await Promise.all([listFloors(), listRoomTypes()]);
        setFloors(f.results);
        setTypes(ty.results);
      } catch {
        // Filters degrade gracefully; the rooms load surfaces errors.
      }
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listRooms({
        page,
        floor: floor ? Number(floor) : undefined,
        room_type: type ? Number(type) : undefined,
        status: status || undefined,
        search: query || undefined,
        include_archived: includeArchived ? "true" : undefined,
      });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, floor, type, status, query, includeArchived, t]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await deleteRoom(deleteTarget.id);
      notify(t.rooms.saved);
      setDeleteTarget(null);
      load();
    } catch (err) {
      notify(messageForError(err, t), "error");
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  function applySearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setQuery(search);
  }

  const floorOptions = floors.map((f) => ({ value: String(f.id), label: f.name }));
  const typeOptions = types.map((ty) => ({ value: String(ty.id), label: ty.name }));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: roomStatusLabel(s, t) }));

  return (
    <>
      <SectionHeader
        title={t.rooms.tabs.rooms}
        icon={BedDouble}
        actions={<Button icon={Plus} onClick={() => setCreating(true)}>{t.rooms.list.add}</Button>}
      />

      <Card>
        <form onSubmit={applySearch}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="room-search">
              <Input id="room-search" value={search} placeholder={t.rooms.list.searchPlaceholder} onChange={(e) => setSearch(e.target.value)} />
            </FormField>
            <FormField label={t.rooms.list.filterFloor} htmlFor="room-floor">
              <Select id="room-floor" value={floor} placeholder={t.common.all} options={floorOptions} onChange={(e) => { setPage(1); setFloor(e.target.value); }} />
            </FormField>
            <FormField label={t.rooms.list.filterType} htmlFor="room-type">
              <Select id="room-type" value={type} placeholder={t.common.all} options={typeOptions} onChange={(e) => { setPage(1); setType(e.target.value); }} />
            </FormField>
            <FormField label={t.rooms.list.filterStatus} htmlFor="room-status">
              <Select id="room-status" value={status} placeholder={t.common.all} options={statusOptions} onChange={(e) => { setPage(1); setStatus(e.target.value); }} />
            </FormField>
            <div className="filter-bar__actions cluster">
              <Switch id="room-archived" label={t.rooms.list.includeArchived} checked={includeArchived} onChange={(v) => { setPage(1); setIncludeArchived(v); }} />
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
            title={t.rooms.list.empty}
            hint={t.rooms.list.emptyHint}
            icon={BedDouble}
            action={<Button icon={Plus} onClick={() => setCreating(true)}>{t.rooms.list.add}</Button>}
          />
        ) : (
          <>
            <div className="room-grid">
              {rows.map((room) => (
                <article className={cx("room-card", `room-card--${room.status}`)} key={room.id}>
                  <div className="room-card__head">
                    <span className="room-card__number">{room.number}</span>
                    <Badge tone={roomStatusTone(room.status)}>{roomStatusLabel(room.status, t)}</Badge>
                  </div>
                  <div className="room-card__meta">
                    <span>{room.room_type_name}</span>
                    <span>{room.floor_name} · {t.rooms.list.capacity}: {room.base_capacity}–{room.max_capacity}</span>
                    {room.display_name ? <span>{room.display_name}</span> : null}
                  </div>
                  {room.status_note ? <span className="room-card__note">{room.status_note}</span> : null}
                  <div className="room-card__actions">
                    <Button variant="secondary" size="sm" icon={RefreshCw} onClick={() => setStatusTarget(room)}>{t.rooms.list.changeStatus}</Button>
                    <Button variant="ghost" size="sm" icon={Pencil} onClick={() => setEditing(room)}>{t.common.edit}</Button>
                    <Button variant="ghost" size="sm" icon={Trash2} onClick={() => setDeleteTarget(room)}>{t.common.delete}</Button>
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

      <RoomFormModal
        open={creating}
        floors={floors}
        types={types}
        onClose={() => setCreating(false)}
        onSaved={() => { setCreating(false); notify(t.rooms.saved); setPage(1); load(); }}
      />
      <RoomFormModal
        open={editing !== null}
        room={editing ?? undefined}
        floors={floors}
        types={types}
        onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); notify(t.rooms.saved); load(); }}
      />
      <RoomStatusModal
        open={statusTarget !== null}
        room={statusTarget ?? undefined}
        onClose={() => setStatusTarget(null)}
        onSaved={() => { setStatusTarget(null); notify(t.rooms.saved); load(); }}
      />
      <ConfirmDialog
        open={deleteTarget !== null}
        title={t.rooms.list.deleteTitle}
        body={t.rooms.list.deleteBody}
        confirmLabel={t.common.delete}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        busy={deleteBusy}
        onConfirm={confirmDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </>
  );
}


