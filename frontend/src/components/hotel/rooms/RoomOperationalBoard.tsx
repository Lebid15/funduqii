"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { BedDouble, Building2, Package, Plus, Rows3, Settings, X } from "lucide-react";

import {
  Alert,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Icon,
  Input,
  LoadingState,
  Modal,
  Select,
  Switch,
  useToast,
} from "@/components/ui";
import {
  changeRoomStatus,
  getOperationalBoard,
  listFloors,
  listRoomTypes,
} from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type {
  Floor,
  RoomBoardRoom,
  RoomOperationalBoard as BoardData,
  RoomType,
} from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import { BulkRoomCreateModal } from "./BulkRoomCreateModal";
import { FloorsTab } from "./FloorsTab";
import { RoomDetailsDrawer } from "./RoomDetailsDrawer";
import { RoomFloorGrid } from "./RoomFloorGrid";
import { RoomFormModal } from "./RoomFormModal";
import { RoomStatusModal } from "./RoomStatusModal";
import { RoomSummaryCards, type BoardCardKey } from "./RoomSummaryCards";
import { RoomTypesTab } from "./RoomTypesTab";

const ATTENTION = new Set(["dirty", "cleaning", "maintenance", "out_of_service"]);
const OPERATIONAL_OPTIONS = [
  "available",
  "dirty",
  "cleaning",
  "maintenance",
  "out_of_service",
  "archived",
] as const;
const OCCUPANCY_OPTIONS = ["free", "occupied", "reserved"] as const;

/**
 * The unified /hotel/rooms workspace (owner rework): ONE page, no tabs. A
 * header action bar (add room / add multiple / a Settings menu for floors +
 * room types), exactly four summary cards, a search + filter row (floor ×
 * room_type × operational status × occupancy × show-archived), and the rooms
 * grouped into collapsible floor sections. Occupancy and operational status
 * are INDEPENDENT axes — every displayed value comes from the server.
 */
export function RoomOperationalBoard({
  refreshSignal = 0,
}: {
  refreshSignal?: number;
}) {
  const { t } = useI18n();
  const { notify } = useToast();
  const b = t.rooms.board;
  const p = t.rooms.page;

  const access = useHotelAccess();
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
  const canCreate = can("rooms.create");
  const canManageInventory = can("rooms.create", "rooms.update", "rooms.delete");

  const [board, setBoard] = useState<BoardData | null>(null);
  const [floors, setFloors] = useState<Floor[]>([]);
  const [types, setTypes] = useState<RoomType[]>([]);
  const [inventoryError, setInventoryError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters — two independent status axes plus the structural ones.
  const [operationalFilter, setOperationalFilter] = useState("");
  const [occupancyFilter, setOccupancyFilter] = useState("");
  const [availableNowOnly, setAvailableNowOnly] = useState(false);
  const [floorFilter, setFloorFilter] = useState<number | null>(null);
  const [typeFilter, setTypeFilter] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);

  const [details, setDetails] = useState<RoomBoardRoom | null>(null);
  const [statusTarget, setStatusTarget] = useState<RoomBoardRoom | null>(null);
  const [editTarget, setEditTarget] = useState<RoomBoardRoom | null>(null);
  const [creating, setCreating] = useState(false);
  const [createFloorId, setCreateFloorId] = useState<number | undefined>(undefined);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [manageFloorsOpen, setManageFloorsOpen] = useState(false);
  const [roomTypesOpen, setRoomTypesOpen] = useState(false);
  const [archiveTarget, setArchiveTarget] = useState<RoomBoardRoom | null>(null);
  const [archiveBusy, setArchiveBusy] = useState(false);

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

  const loadInventory = useCallback(() => {
    Promise.all([listFloors(), listRoomTypes()])
      .then(([f, ty]) => {
        setFloors(f.results);
        setTypes(ty.results);
        setInventoryError(false);
      })
      .catch(() => {
        // The board still renders from its own call; flag a soft error so the
        // create/bulk forms' empty option lists are explained, not silent.
        setInventoryError(true);
      });
  }, []);

  useEffect(() => {
    load();
    loadInventory();
  }, [load, loadInventory]);

  const refreshAll = useCallback(() => {
    load();
    loadInventory();
  }, [load, loadInventory]);

  // The page pulses `refreshSignal` when the operator returns to this tab
  // (visibilitychange). Refetch the board + inventory WITHOUT remounting — the
  // active filters, search and open modals all survive. Real increments only
  // (the initial value must not refetch on mount).
  const lastRefreshSignal = useRef(refreshSignal);
  useEffect(() => {
    if (refreshSignal !== lastRefreshSignal.current) {
      lastRefreshSignal.current = refreshSignal;
      refreshAll();
    }
  }, [refreshSignal, refreshAll]);

  const hasFilters =
    operationalFilter !== "" ||
    occupancyFilter !== "" ||
    availableNowOnly ||
    floorFilter !== null ||
    typeFilter !== "" ||
    query !== "" ||
    showArchived;

  function clearFilters() {
    setOperationalFilter("");
    setOccupancyFilter("");
    setAvailableNowOnly(false);
    setFloorFilter(null);
    setTypeFilter("");
    setSearch("");
    setQuery("");
    setShowArchived(false);
  }

  // The four cards drive the underlying (mutually exclusive) quick filters.
  const activeCard: BoardCardKey | null = availableNowOnly
    ? "available"
    : occupancyFilter === "occupied"
      ? "occupied"
      : operationalFilter === "attention"
        ? "attention"
        : null;

  function onCard(key: BoardCardKey | "total") {
    if (key === "total") {
      setAvailableNowOnly(false);
      setOccupancyFilter("");
      setOperationalFilter("");
      return;
    }
    if (key === "available") {
      const next = !availableNowOnly;
      setAvailableNowOnly(next);
      if (next) {
        setOccupancyFilter("");
        setOperationalFilter("");
      }
      return;
    }
    if (key === "occupied") {
      setOccupancyFilter(occupancyFilter === "occupied" ? "" : "occupied");
      setAvailableNowOnly(false);
      setOperationalFilter("");
      return;
    }
    // attention
    setOperationalFilter(operationalFilter === "attention" ? "" : "attention");
    setAvailableNowOnly(false);
    setOccupancyFilter("");
  }

  const filteredRooms = useMemo(() => {
    if (!board) return [];
    const needle = query.trim().toLowerCase();
    const includeArchived = showArchived || operationalFilter === "archived";
    return board.rooms.filter((room) => {
      const archived = room.operational_status === "archived";
      if (archived && !includeArchived) return false;
      if (floorFilter !== null && room.floor !== floorFilter) return false;
      if (typeFilter && String(room.room_type) !== typeFilter) return false;
      if (availableNowOnly && !room.available_now) return false;
      if (occupancyFilter && room.occupancy_status !== occupancyFilter) return false;
      if (operationalFilter === "attention") {
        if (!ATTENTION.has(room.operational_status)) return false;
      } else if (operationalFilter && room.operational_status !== operationalFilter) {
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
  }, [
    board,
    operationalFilter,
    occupancyFilter,
    availableNowOnly,
    floorFilter,
    typeFilter,
    query,
    showArchived,
  ]);

  function applySearch(event: FormEvent) {
    event.preventDefault();
    setQuery(search);
  }

  function openCreate(floorId?: number) {
    setCreateFloorId(floorId);
    setCreating(true);
  }

  async function confirmArchive() {
    if (!archiveTarget) return;
    setArchiveBusy(true);
    try {
      // Archive = a plain status change to "archived" (gated by
      // rooms.status_update, no note required). Records, stays, reservations
      // and history are preserved — the room is only hidden from active
      // operations and can be restored anytime via Change status.
      await changeRoomStatus(archiveTarget.id, "archived", "");
      notify(t.rooms.saved);
      setArchiveTarget(null);
      refreshAll();
    } catch (err) {
      notify(messageForError(err, t), "error");
      setArchiveTarget(null);
    } finally {
      setArchiveBusy(false);
    }
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

  // The setup hint is ONLY about having zero floors — the room-type list can
  // fail to load (soft error) without meaning the hotel has no inventory.
  const noInventory = board.floors.length === 0;
  const floorsToShow =
    floorFilter === null
      ? board.floors
      : board.floors.filter((f) => f.id === floorFilter);
  const showFilteredEmpty = hasFilters && filteredRooms.length === 0;

  const operationalOptions = [
    ...OPERATIONAL_OPTIONS.map((s) => ({ value: s, label: b.status[s] })),
    { value: "attention", label: b.status.attention },
  ];
  const occupancyOptions = OCCUPANCY_OPTIONS.map((s) => ({
    value: s,
    label: t.rooms.occupancy[s],
  }));
  // Room-type filter options are derived from the BOARD (rooms carry
  // room_type + room_type_name), so the filter still works even when the
  // inventory call failed.
  const typeFilterOptions = (() => {
    const seen = new Map<number, string>();
    for (const room of board.rooms) {
      if (!seen.has(room.room_type)) seen.set(room.room_type, room.room_type_name);
    }
    return [...seen.entries()].map(([id, name]) => ({
      value: String(id),
      label: name,
    }));
  })();

  return (
    <div className="stack">
      {/* Header action bar (the page H1 lives in the PageHeader above). */}
      <div className="rooms-toolbar">
        <div className="rooms-toolbar__actions cluster">
          {canCreate ? (
            <>
              <Button icon={Plus} onClick={() => openCreate()}>
                {p.addRoom}
              </Button>
              <Button variant="secondary" icon={Rows3} onClick={() => setBulkOpen(true)}>
                {p.addMultiple}
              </Button>
            </>
          ) : null}
          {canManageInventory ? (
            <SettingsMenu
              label={p.settings}
              items={[
                {
                  key: "floors",
                  label: p.manageFloors,
                  icon: Building2,
                  onSelect: () => setManageFloorsOpen(true),
                },
                {
                  key: "types",
                  label: p.roomTypes,
                  icon: Package,
                  onSelect: () => setRoomTypesOpen(true),
                },
              ]}
            />
          ) : null}
        </div>
      </div>

      {noInventory ? <Alert tone="warning">{b.setupHint}</Alert> : null}
      {inventoryError ? <Alert tone="warning">{p.inventoryError}</Alert> : null}

      <RoomSummaryCards summary={board.summary} active={activeCard} onSelect={onCard} />

      <Card>
        <form onSubmit={applySearch} aria-label={p.filters}>
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
                options={typeFilterOptions}
                onChange={(e) => setTypeFilter(e.target.value)}
              />
            </FormField>
            <FormField label={t.rooms.list.filterStatus} htmlFor="board-status">
              <Select
                id="board-status"
                value={operationalFilter}
                placeholder={t.common.all}
                options={operationalOptions}
                onChange={(e) => {
                  setOperationalFilter(e.target.value);
                  setAvailableNowOnly(false);
                }}
              />
            </FormField>
            <FormField label={p.filterOccupancy} htmlFor="board-occupancy">
              <Select
                id="board-occupancy"
                value={occupancyFilter}
                placeholder={t.common.all}
                options={occupancyOptions}
                onChange={(e) => {
                  setOccupancyFilter(e.target.value);
                  setAvailableNowOnly(false);
                }}
              />
            </FormField>
            <div className="filter-bar__actions cluster">
              <Switch
                id="board-archived"
                label={p.showArchived}
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
      </Card>

      {board.floors.length === 0 ? (
        <EmptyState title={t.rooms.list.empty} hint={t.rooms.list.emptyHint} icon={BedDouble} />
      ) : showFilteredEmpty ? (
        <EmptyState
          title={b.emptyFiltered}
          icon={BedDouble}
          action={
            <Button variant="secondary" icon={X} onClick={clearFilters}>
              {b.clearFilters}
            </Button>
          }
        />
      ) : (
        <RoomFloorGrid
          floors={floorsToShow}
          rooms={filteredRooms}
          currency={board.currency}
          canCreate={canCreate}
          hasFilters={hasFilters}
          onDetails={setDetails}
          onEdit={(room) => setEditTarget(room)}
          onArchive={(room) => setArchiveTarget(room)}
          onChangeStatus={(room) => setStatusTarget(room)}
          onAddRoomToFloor={(floorId) => openCreate(floorId)}
        />
      )}

      <RoomDetailsDrawer
        room={details}
        currency={board.currency}
        onClose={() => setDetails(null)}
        onChangeStatus={(room) => {
          setDetails(null);
          setStatusTarget(room);
        }}
      />
      <ConfirmDialog
        open={archiveTarget !== null}
        title={p.archiveRoomTitle}
        body={
          archiveTarget
            ? p.archiveRoomBody.replace("{number}", archiveTarget.number)
            : ""
        }
        confirmLabel={p.archiveRoom}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        busy={archiveBusy}
        onConfirm={confirmArchive}
        onClose={() => setArchiveTarget(null)}
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
        open={creating}
        floors={floors}
        types={types}
        initialFloor={createFloorId}
        onClose={() => {
          setCreating(false);
          setCreateFloorId(undefined);
        }}
        onSaved={() => {
          setCreating(false);
          setCreateFloorId(undefined);
          notify(t.rooms.saved);
          refreshAll();
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
          refreshAll();
        }}
      />
      <BulkRoomCreateModal
        open={bulkOpen}
        floors={floors}
        types={types}
        onClose={() => setBulkOpen(false)}
        onCreated={refreshAll}
      />
      <Modal
        open={manageFloorsOpen}
        onClose={() => {
          setManageFloorsOpen(false);
          refreshAll();
        }}
        title={p.manageFloors}
        closeLabel={t.common.close}
      >
        <FloorsTab embedded />
      </Modal>
      <Modal
        open={roomTypesOpen}
        onClose={() => {
          setRoomTypesOpen(false);
          refreshAll();
        }}
        title={p.roomTypes}
        closeLabel={t.common.close}
        size="xl"
      >
        <RoomTypesTab embedded currency={board.currency} />
      </Modal>
    </div>
  );
}

/** A quiet Settings disclosure menu (owner spec): the two admin entries live
 * here so they stay discoverable but never crowd the action bar — identical on
 * desktop and mobile. Closes on outside click / Escape. */
function SettingsMenu({
  label,
  items,
}: {
  label: string;
  items: Array<{
    key: string;
    label: string;
    icon: typeof Building2;
    onSelect: () => void;
  }>;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  // Focus the first item when the menu opens (keyboard-first).
  useEffect(() => {
    if (open) itemRefs.current[0]?.focus();
  }, [open]);

  function focusItem(index: number) {
    const count = items.length;
    const next = ((index % count) + count) % count;
    itemRefs.current[next]?.focus();
  }

  function closeAndReturnFocus() {
    setOpen(false);
    buttonRef.current?.focus();
  }

  function onListKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const current = itemRefs.current.findIndex(
      (el) => el === document.activeElement,
    );
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusItem(current + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusItem(current - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusItem(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusItem(items.length - 1);
    } else if (event.key === "Escape" || event.key === "Tab") {
      closeAndReturnFocus();
    }
  }

  return (
    <div className="settings-menu" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="btn btn--secondary settings-menu__button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <Icon icon={Settings} size="sm" />
        <span>{label}</span>
      </button>
      {open ? (
        <div
          className="settings-menu__list"
          role="menu"
          aria-label={label}
          onKeyDown={onListKeyDown}
        >
          {items.map((item, index) => (
            <button
              key={item.key}
              ref={(el) => {
                itemRefs.current[index] = el;
              }}
              type="button"
              role="menuitem"
              className="settings-menu__item"
              onClick={() => {
                item.onSelect();
                closeAndReturnFocus();
              }}
            >
              <Icon icon={item.icon} size="sm" />
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
