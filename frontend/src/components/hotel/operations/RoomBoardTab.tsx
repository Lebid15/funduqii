"use client";

import { useCallback, useEffect, useState } from "react";
import { BedDouble, Brush, Wrench } from "lucide-react";

import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  Switch,
  useToast,
} from "@/components/ui";
import {
  createHousekeepingTask,
  listArrivalsNotReady,
  listHousekeepingTasks,
  listMaintenanceRequests,
} from "@/lib/api/operations";
import { changeRoomStatus, listRooms } from "@/lib/api/rooms";
import { listCurrentResidents } from "@/lib/api/stays";
import { messageForError } from "@/lib/api/errors";
import type {
  ArrivalNotReadyRow,
  HousekeepingStatus,
  HousekeepingTaskListItem,
  MaintenanceRequestListItem,
  PaginatedResponse,
  Room,
  RoomStatus,
} from "@/lib/api/types";
import { roomStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { CreateRequestModal } from "./MaintenanceTab";

const BOARD_STATUSES: RoomStatus[] = [
  "available",
  "dirty",
  "cleaning",
  "maintenance",
  "out_of_service",
  "archived",
];
const ACTIVE_HK: HousekeepingStatus[] = [
  "pending",
  "assigned",
  "in_progress",
  "awaiting_inspection",
];
const OPEN_MT = ["open", "assigned", "in_progress"] as const;
const MAX_PAGES = 20;

/** Drain every page of a paginated list (hard cap MAX_PAGES pages). */
async function fetchAllPages<T>(
  fetchPage: (page: number) => Promise<PaginatedResponse<T>>,
): Promise<T[]> {
  const all: T[] = [];
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const res = await fetchPage(page);
    all.push(...res.results);
    if (res.next === null || res.results.length === 0) break;
  }
  return all;
}

/** Cosmetic permission gate — every API re-checks server-side regardless. */
function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

/** Room status board: rooms grouped by their MANUAL operational status.
 * Occupancy is deliberately shown as an "in-house stay" badge derived from
 * stays — never as a room status (there is no `occupied`). All quick actions
 * call the controlled backend paths; nothing is decided client-side. */
export function RoomBoardTab() {
  const { t } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const board = t.operations.board;

  const [rooms, setRooms] = useState<Room[]>([]);
  const [inHouseRooms, setInHouseRooms] = useState<Set<number>>(new Set());
  const [lastTaskByRoom, setLastTaskByRoom] = useState<Map<number, HousekeepingTaskListItem>>(
    new Map(),
  );
  const [openRequestByRoom, setOpenRequestByRoom] = useState<
    Map<number, MaintenanceRequestListItem>
  >(new Map());
  const [arrivals, setArrivals] = useState<ArrivalNotReadyRow[]>([]);
  const [arrivalsOnly, setArrivalsOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [requestRoom, setRequestRoom] = useState<Room | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [roomList, residents, taskLists, requestLists, arrivalRows] =
        await Promise.all([
          fetchAllPages((page) =>
            listRooms({ page, page_size: 100, include_archived: "true" }),
          ),
          listCurrentResidents(),
          Promise.all(
            ACTIVE_HK.map((status) =>
              fetchAllPages((page) =>
                listHousekeepingTasks({ page, status, ordering: "-requested_at" }),
              ),
            ),
          ),
          Promise.all(
            OPEN_MT.map((status) =>
              fetchAllPages((page) =>
                listMaintenanceRequests({ page, status, ordering: "-reported_at" }),
              ),
            ),
          ),
          listArrivalsNotReady(),
        ]);
      setRooms(roomList);
      setInHouseRooms(new Set(residents.results.map((s) => s.room)));
      const activeTasks = taskLists
        .flat()
        .sort((a, b) => b.requested_at.localeCompare(a.requested_at));
      const taskMap = new Map<number, HousekeepingTaskListItem>();
      for (const task of activeTasks) {
        if (task.room !== null && !taskMap.has(task.room)) taskMap.set(task.room, task);
      }
      setLastTaskByRoom(taskMap);
      const openRequests = requestLists
        .flat()
        .sort((a, b) => b.reported_at.localeCompare(a.reported_at));
      const requestMap = new Map<number, MaintenanceRequestListItem>();
      for (const request of openRequests) {
        if (request.room !== null && !requestMap.has(request.room)) {
          requestMap.set(request.room, request);
        }
      }
      setOpenRequestByRoom(requestMap);
      setArrivals(arrivalRows);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  async function quick(roomId: number, action: () => Promise<unknown>, msg: string) {
    setBusyId(roomId);
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

  if (loading) return <LoadingState label={t.common.loading} />;
  if (error)
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={error}
        retryLabel={t.common.retry}
        onRetry={load}
      />
    );
  if (rooms.length === 0)
    return <EmptyState title={board.empty} hint={board.emptyHint} icon={BedDouble} />;

  const arrivalRoomIds = new Set(arrivals.map((a) => a.room));
  const visibleRooms = arrivalsOnly
    ? rooms.filter((r) => arrivalRoomIds.has(r.id))
    : rooms;

  return (
    <>
      <p className="muted">{board.hint}</p>
      {arrivals.length > 0 ? (
        <div className="cluster">
          <Badge tone="danger">
            {board.arrivalsNotReadyCount}: {arrivals.length}
          </Badge>
          <Switch
            id="board-arrivals-only"
            checked={arrivalsOnly}
            onChange={setArrivalsOnly}
            label={board.arrivalsOnly}
          />
        </div>
      ) : null}
      <div className="board-grid board-grid--wide">
        {BOARD_STATUSES.map((statusKey) => {
          const group = visibleRooms.filter((r) => r.status === statusKey);
          return (
            <section
              key={statusKey}
              className="board-col"
              aria-label={t.rooms.status[statusKey]}
            >
              <header className="board-col__head">
                <span className="board-col__title">{t.rooms.status[statusKey]}</span>
                <Badge tone={roomStatusTone(statusKey)}>{group.length}</Badge>
              </header>
              <div className="board-col__body">
                {group.map((room) => {
                  const lastTask = lastTaskByRoom.get(room.id);
                  const openRequest = openRequestByRoom.get(room.id);
                  return (
                    <article key={room.id} className="board-card">
                      <div className="board-card__head">
                        <strong>{room.number}</strong>
                        {inHouseRooms.has(room.id) ? (
                          <Badge tone="success">{board.inHouse}</Badge>
                        ) : null}
                        {arrivalRoomIds.has(room.id) ? (
                          <Badge tone="danger">{board.arrivalNotReady}</Badge>
                        ) : null}
                      </div>
                      <span className="muted small">
                        {board.floor}: {room.floor_name} · {board.roomType}:{" "}
                        {room.room_type_name}
                      </span>
                      {lastTask ? (
                        <span className="muted small">
                          {lastTask.task_number} ·{" "}
                          {t.operations.hk.status[lastTask.status]}
                        </span>
                      ) : null}
                      {openRequest ? (
                        <span className="muted small">
                          {openRequest.request_number} ·{" "}
                          {t.operations.mt.status[openRequest.status]}
                        </span>
                      ) : null}
                      {statusKey !== "archived" ? (
                        <div className="cluster">
                          {can("housekeeping.create") ? (
                            <Button
                              size="sm"
                              variant="secondary"
                              icon={Brush}
                              loading={busyId === room.id}
                              onClick={() =>
                                quick(
                                  room.id,
                                  () => createHousekeepingTask({ room: room.id }),
                                  t.operations.hk.created,
                                )
                              }
                            >
                              {board.createTask}
                            </Button>
                          ) : null}
                          {can("maintenance.create") ? (
                            <Button
                              size="sm"
                              variant="secondary"
                              icon={Wrench}
                              onClick={() => setRequestRoom(room)}
                            >
                              {board.createRequest}
                            </Button>
                          ) : null}
                          {statusKey === "available" && can("rooms.status_update") ? (
                            <Button
                              size="sm"
                              variant="danger"
                              loading={busyId === room.id}
                              onClick={() =>
                                quick(
                                  room.id,
                                  () => changeRoomStatus(room.id, "dirty"),
                                  board.markedDirty,
                                )
                              }
                            >
                              {board.markDirty}
                            </Button>
                          ) : null}
                          {(statusKey === "dirty" || statusKey === "cleaning") &&
                          can("rooms.status_update") ? (
                            <Button
                              size="sm"
                              loading={busyId === room.id}
                              onClick={() =>
                                quick(
                                  room.id,
                                  () => changeRoomStatus(room.id, "available"),
                                  board.markedAvailable,
                                )
                              }
                            >
                              {board.markAvailable}
                            </Button>
                          ) : null}
                        </div>
                      ) : null}
                    </article>
                  );
                })}
                {group.length === 0 ? (
                  <p className="muted small">{board.columnEmpty}</p>
                ) : null}
              </div>
            </section>
          );
        })}
      </div>
      <CreateRequestModal
        open={requestRoom !== null}
        rooms={rooms.filter((r) => r.status !== "archived")}
        presetRoom={requestRoom?.id}
        onClose={() => setRequestRoom(null)}
        onSaved={() => {
          setRequestRoom(null);
          notify(t.operations.mt.created);
          load();
        }}
      />
    </>
  );
}
