"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { BedDouble, X } from "lucide-react";

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
  SectionHeader,
  Select,
  Switch,
  useToast,
} from "@/components/ui";
import { getOperationalBoard, listFloors, listRoomTypes } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type {
  Floor,
  RoomBoardRoom,
  RoomOperationalBoard as BoardData,
  RoomType,
} from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { FloorSummaryCards } from "./FloorSummaryCards";
import { RoomDetailsDrawer } from "./RoomDetailsDrawer";
import { RoomFloorGrid } from "./RoomFloorGrid";
import { RoomFormModal } from "./RoomFormModal";
import { RoomStatusModal } from "./RoomStatusModal";
import { RoomSummaryCards, type BoardStatusFilter } from "./RoomSummaryCards";

const ATTENTION = new Set(["dirty", "cleaning", "maintenance", "out_of_service"]);
const MAINT_OOS = new Set(["maintenance", "out_of_service"]);

/**
 * The rooms OPERATIONAL board (owner task): one read-only call feeds the
 * clickable summary cards, the clickable floor cards, the filter bar, and
 * the rooms grouped by floor — every displayed status is computed server-
 * side (occupied/reserved never stored). Filters combine: floor × status ×
 * type × text search × show-archived.
 */
export function RoomOperationalBoard() {
  const { t } = useI18n();
  const { notify } = useToast();
  const b = t.rooms.board;

  const [board, setBoard] = useState<BoardData | null>(null);
  const [floors, setFloors] = useState<Floor[]>([]);
  const [types, setTypes] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<BoardStatusFilter | null>(null);
  const [floorFilter, setFloorFilter] = useState<number | null>(null);
  const [typeFilter, setTypeFilter] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);

  const [details, setDetails] = useState<RoomBoardRoom | null>(null);
  const [statusTarget, setStatusTarget] = useState<RoomBoardRoom | null>(null);
  const [editTarget, setEditTarget] = useState<RoomBoardRoom | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getOperationalBoard();
      setBoard(data);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t is stable per locale
  }, []);

  useEffect(() => {
    load();
    // The floor/type lists feed the bulk modal + the type filter.
    Promise.all([listFloors(), listRoomTypes()])
      .then(([f, ty]) => {
        setFloors(f.results);
        setTypes(ty.results);
      })
      .catch(() => {
        // The board itself surfaces errors; these lists degrade gracefully.
      });
  }, [load]);

  const hasFilters =
    statusFilter !== null ||
    floorFilter !== null ||
    typeFilter !== "" ||
    query !== "" ||
    showArchived;

  function clearFilters() {
    setStatusFilter(null);
    setFloorFilter(null);
    setTypeFilter("");
    setSearch("");
    setQuery("");
    setShowArchived(false);
  }

  const filteredRooms = useMemo(() => {
    if (!board) return [];
    const needle = query.trim().toLowerCase();
    return board.rooms.filter((room) => {
      if (room.display_status === "archived" && !showArchived) return false;
      if (floorFilter !== null && room.floor !== floorFilter) return false;
      if (typeFilter && String(room.room_type) !== typeFilter) return false;
      if (statusFilter === "attention") {
        if (!ATTENTION.has(room.display_status)) return false;
      } else if (statusFilter === "maintenance_oos") {
        if (!MAINT_OOS.has(room.display_status)) return false;
      } else if (statusFilter && room.display_status !== statusFilter) {
        return false;
      }
      if (needle) {
        const haystack = [
          room.number,
          room.display_name,
          room.room_type_name,
          room.current_stay?.guest_name ?? "",
          room.next_reservation?.guest_name ?? "",
          room.next_reservation?.reservation_number ?? "",
        ]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      return true;
    });
  }, [board, statusFilter, floorFilter, typeFilter, query, showArchived]);

  function applySearch(event: FormEvent) {
    event.preventDefault();
    setQuery(search);
  }

  if (loading) return <LoadingState label={t.common.loading} />;
  if (error || !board) {
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={error ?? ""}
        retryLabel={t.common.retry}
        onRetry={load}
      />
    );
  }

  const activeFloor = board.floors.find((f) => f.id === floorFilter) ?? null;
  const noInventory = board.floors.length === 0 || types.length === 0;

  return (
    <div className="stack">
      {noInventory ? <Alert tone="warning">{b.setupHint}</Alert> : null}

      <RoomSummaryCards
        summary={board.summary}
        active={statusFilter}
        onToggle={setStatusFilter}
      />

      <section className="stack" aria-label={b.floorsOverview}>
        <SectionHeader title={b.floorsOverview} />
        <FloorSummaryCards
          floors={board.floors}
          active={floorFilter}
          onToggle={setFloorFilter}
        />
      </section>

      <Card>
        <form onSubmit={applySearch}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="board-search">
              <Input
                id="board-search"
                value={search}
                placeholder={b.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
                onBlur={() => setQuery(search)}
              />
            </FormField>
            <FormField label={t.rooms.list.filterFloor} htmlFor="board-floor">
              <Select
                id="board-floor"
                value={floorFilter === null ? "" : String(floorFilter)}
                placeholder={t.common.all}
                options={board.floors.map((f) => ({ value: String(f.id), label: f.name }))}
                onChange={(e) =>
                  setFloorFilter(e.target.value ? Number(e.target.value) : null)
                }
              />
            </FormField>
            <FormField label={t.rooms.list.filterType} htmlFor="board-type">
              <Select
                id="board-type"
                value={typeFilter}
                placeholder={t.common.all}
                options={types.map((ty) => ({ value: String(ty.id), label: ty.name }))}
                onChange={(e) => setTypeFilter(e.target.value)}
              />
            </FormField>
            <FormField label={t.rooms.list.filterStatus} htmlFor="board-status">
              <Select
                id="board-status"
                value={statusFilter ?? ""}
                placeholder={t.common.all}
                options={[
                  ...(
                    [
                      "available",
                      "occupied",
                      "reserved",
                      "dirty",
                      "cleaning",
                      "maintenance",
                      "out_of_service",
                      "attention",
                    ] as const
                  ).map((s) => ({ value: s, label: b.status[s] })),
                  { value: "maintenance_oos", label: b.maintOos },
                ]}
                onChange={(e) =>
                  setStatusFilter((e.target.value || null) as BoardStatusFilter | null)
                }
              />
            </FormField>
            <div className="filter-bar__actions cluster">
              <Switch
                id="board-archived"
                label={t.rooms.list.includeArchived}
                checked={showArchived}
                onChange={setShowArchived}
              />
              {hasFilters ? (
                <Button variant="ghost" size="sm" icon={X} onClick={clearFilters}>
                  {b.clearFilters}
                </Button>
              ) : null}
            </div>
          </FilterBar>
        </form>
        {activeFloor || statusFilter ? (
          <div className="cluster board-active-filters">
            {activeFloor ? (
              <span className="chip">
                {b.floorFilterChip.replace("{floor}", activeFloor.name)}
              </span>
            ) : null}
            {statusFilter ? (
              <span className="chip">
                {statusFilter === "maintenance_oos"
                  ? b.maintOos
                  : b.status[statusFilter]}
              </span>
            ) : null}
          </div>
        ) : null}
      </Card>

      {filteredRooms.length === 0 ? (
        <EmptyState
          title={hasFilters ? b.emptyFiltered : t.rooms.list.empty}
          hint={hasFilters ? undefined : t.rooms.list.emptyHint}
          icon={BedDouble}
          action={
            hasFilters ? (
              <Button variant="secondary" icon={X} onClick={clearFilters}>
                {b.clearFilters}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <RoomFloorGrid
          floors={board.floors.filter(
            (f) => floorFilter === null || f.id === floorFilter,
          )}
          rooms={filteredRooms}
          onDetails={setDetails}
          onEdit={(room) => setEditTarget(room)}
        />
      )}

      <RoomDetailsDrawer
        room={details}
        onClose={() => setDetails(null)}
        onChangeStatus={(room) => {
          setDetails(null);
          setStatusTarget(room);
        }}
      />
      <RoomStatusModal
        open={statusTarget !== null}
        room={
          statusTarget
            ? {
                id: statusTarget.id,
                status: statusTarget.operational_status,
                status_note: statusTarget.status_note,
              }
            : undefined
        }
        onClose={() => setStatusTarget(null)}
        onSaved={() => {
          setStatusTarget(null);
          notify(t.rooms.saved);
          load();
        }}
      />
      <RoomFormModal
        open={editTarget !== null}
        room={
          editTarget
            ? {
                id: editTarget.id,
                number: editTarget.number,
                display_name: editTarget.display_name,
                floor: editTarget.floor,
                floor_name: editTarget.floor_name,
                room_type: editTarget.room_type,
                room_type_name: editTarget.room_type_name,
                room_type_code: editTarget.room_type_code,
                base_capacity: editTarget.base_capacity,
                max_capacity: editTarget.max_capacity,
                status: editTarget.operational_status,
                status_note: editTarget.status_note,
                status_changed_at: editTarget.status_changed_at,
                status_changed_by: null,
                is_active: editTarget.is_active,
                created_at: "",
                updated_at: "",
              }
            : undefined
        }
        floors={floors}
        types={types}
        onClose={() => setEditTarget(null)}
        onSaved={() => {
          setEditTarget(null);
          notify(t.rooms.saved);
          load();
        }}
      />
    </div>
  );
}
