"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  BedDouble,
  Brush,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  Layers,
  PackageSearch,
  PauseCircle,
  Play,
  Plus,
  PlaneLanding,
  SlidersHorizontal,
  Tag,
  Timer,
  UserCheck,
  Wrench,
  XCircle,
} from "lucide-react";

import { useQuickAction } from "@/lib/useQuickAction";

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
  Switch,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  approveInspection,
  assignHousekeepingTask,
  cancelHousekeepingTask,
  comeBackLaterHousekeepingTask,
  completeHousekeepingTask,
  createHousekeepingTask,
  listArrivalsNotReady,
  listHousekeepingTasks,
  rejectInspection,
  setHousekeepingStatus,
  updateHousekeepingTask,
  type HousekeepingCreateBody,
} from "@/lib/api/operations";
import { listCurrentResidents } from "@/lib/api/stays";
import { messageForError } from "@/lib/api/errors";
import type {
  HousekeepingServiceOutcome,
  HousekeepingTaskListItem,
  HousekeepingTaskType,
  OperationPriority,
  Stay,
} from "@/lib/api/types";
import {
  formatDate,
  formatDateTime,
  housekeepingStatusTone,
  operationPriorityTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { OperationCard, type OperationMenuItem } from "./OperationCard";
import { RoomOptionSelect } from "./RoomOptionSelect";
import { StatCards, type OperationStat } from "./StatCards";
import { AssignModal, formatDuration, useCan } from "./operationsShared";
import { CreateRequestModal } from "./MaintenanceTab";
import { CreateItemModal } from "./LostFoundTab";

const PAGE_SIZE = 25;
const TASK_TYPES: HousekeepingTaskType[] = [
  "checkout_cleaning",
  "daily_cleaning",
  "deep_cleaning",
  "inspection",
  "other",
];
const STATUSES = [
  "pending",
  "assigned",
  "in_progress",
  "awaiting_inspection",
  "completed",
  "cancelled",
] as const;
const PRIORITIES: OperationPriority[] = ["low", "normal", "high", "urgent"];
const SERVICE_OUTCOMES: HousekeepingServiceOutcome[] = [
  "cleaned",
  "guest_refused",
  "do_not_disturb",
  "no_access",
];

interface HkStats {
  needsCleaning: number | null;
  inCleaning: number | null;
  awaitingInspection: number | null;
  upcomingArrival: number | null;
}

/** A room preselected for a cross-tab create action (defect / found item). */
interface PresetRoom {
  id: number;
  label: string;
}

export function HousekeepingTab() {
  const { t } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const hk = t.operations.hk;

  const [rows, setRows] = useState<HousekeepingTaskListItem[]>([]);
  const [count, setCount] = useState(0);
  const [stats, setStats] = useState<HkStats>({
    needsCleaning: null,
    inCleaning: null,
    awaitingInspection: null,
    upcomingArrival: null,
  });
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [taskType, setTaskType] = useState("");
  const [priority, setPriority] = useState("");
  const [roomId, setRoomId] = useState<number | null>(null);
  const [date, setDate] = useState("");
  const [mineOnly, setMineOnly] = useState(false);
  const [ordering, setOrdering] = useState("");
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
  const [quickRoom, setQuickRoom] = useState(0);
  useQuickAction("new", (params) => {
    setQuickRoom(Number(params.get("room")) || 0);
    setCreateOpen(true);
  });
  const [completeTask, setCompleteTask] = useState<HousekeepingTaskListItem | null>(null);
  const [cancelTask, setCancelTask] = useState<HousekeepingTaskListItem | null>(null);
  const [assignTask, setAssignTask] = useState<HousekeepingTaskListItem | null>(null);
  const [rejectTask, setRejectTask] = useState<HousekeepingTaskListItem | null>(null);
  const [priorityTask, setPriorityTask] = useState<HousekeepingTaskListItem | null>(null);
  const [comeBackTask, setComeBackTask] = useState<HousekeepingTaskListItem | null>(null);
  const [defectRoom, setDefectRoom] = useState<PresetRoom | null>(null);
  const [foundRoom, setFoundRoom] = useState<PresetRoom | null>(null);

  const load = useCallback(async () => {
    const seq = (seqRef.current += 1);
    setLoading(true);
    setError(null);
    try {
      const [tasks, pending, inProgress, awaiting, arrivals] = await Promise.all([
        listHousekeepingTasks({
          page,
          search: query || undefined,
          status: status || undefined,
          task_type: taskType || undefined,
          priority: priority || undefined,
          room: roomId ?? undefined,
          date: date || undefined,
          mine: mineOnly ? "true" : undefined,
          ordering: ordering || undefined,
        }),
        listHousekeepingTasks({ status: "pending", page: 1 }),
        listHousekeepingTasks({ status: "in_progress", page: 1 }),
        listHousekeepingTasks({ status: "awaiting_inspection", page: 1 }),
        listArrivalsNotReady(),
      ]);
      if (seqRef.current !== seq) return;
      setRows(tasks.results);
      setCount(tasks.count);
      setStats({
        needsCleaning: pending.count,
        inCleaning: inProgress.count,
        awaitingInspection: awaiting.count,
        upcomingArrival: arrivals.length,
      });
      loadedOnceRef.current = true;
      setHasLoadedOnce(true);
    } catch (err) {
      if (seqRef.current !== seq) return;
      const message = messageForError(err, t);
      // BACKGROUND refetch failure — keep the cards, non-blocking toast; the full
      // ErrorState + retry is reserved for the initial load.
      if (loadedOnceRef.current) notify(message, "error");
      else setError(message);
    } finally {
      if (mountedRef.current && seqRef.current === seq) setLoading(false);
    }
  }, [page, query, status, taskType, priority, roomId, date, mineOnly, ordering, t, notify]);

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

  async function run(id: number, action: () => Promise<unknown>, successMessage: string) {
    setBusyId(id);
    try {
      await action();
      notify(successMessage);
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
  const statusOptions = STATUSES.map((s) => ({ value: s, label: hk.status[s] }));
  const typeOptions = TASK_TYPES.map((v) => ({ value: v, label: hk.types[v] }));
  const priorityOptions = PRIORITIES.map((p) => ({
    value: p,
    label: t.operations.priority[p],
  }));

  const statCards: OperationStat[] = [
    {
      key: "needsCleaning",
      label: hk.stats.needsCleaning,
      value: stats.needsCleaning,
      icon: Brush,
      tone: "warning",
      active: status === "pending",
      onFilter: () => applyStatusFilter("pending"),
    },
    {
      key: "inCleaning",
      label: hk.stats.inCleaning,
      value: stats.inCleaning,
      icon: Timer,
      tone: "primary",
      active: status === "in_progress",
      onFilter: () => applyStatusFilter("in_progress"),
    },
    {
      key: "awaitingInspection",
      label: hk.stats.awaitingInspection,
      value: stats.awaitingInspection,
      icon: ClipboardCheck,
      tone: "info",
      active: status === "awaiting_inspection",
      onFilter: () => applyStatusFilter("awaiting_inspection"),
    },
    {
      key: "upcomingArrival",
      label: hk.stats.upcomingArrival,
      value: stats.upcomingArrival,
      icon: PlaneLanding,
      tone: stats.upcomingArrival && stats.upcomingArrival > 0 ? "danger" : "neutral",
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

  // Cross-tab openers — extract the room context the create modals need.
  const openDefect = (row: HousekeepingTaskListItem) =>
    setDefectRoom({ id: row.room as number, label: row.room_number });
  const openFound = (row: HousekeepingTaskListItem) =>
    setFoundRoom({ id: row.room as number, label: row.room_number });

  return (
    <>
      <StatCards stats={statCards} loading={loading} ariaLabel={hk.title} />

      <Card>
        <SectionHeader
          title={hk.title}
          actions={
            can("housekeeping.create") ? (
              <Button icon={Plus} onClick={() => setCreateOpen(true)}>
                {hk.create}
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
            <FormField label={t.common.search} htmlFor="hk-search">
              <Input
                id="hk-search"
                value={search}
                placeholder={hk.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
              />
            </FormField>
            <FormField label={t.common.status} htmlFor="hk-status">
              <Select
                id="hk-status"
                value={status}
                placeholder={t.common.all}
                options={statusOptions}
                onChange={(e) => {
                  setPage(1);
                  setStatus(e.target.value);
                }}
              />
            </FormField>
            <FormField label={t.operations.priorityLabel} htmlFor="hk-priority">
              <Select
                id="hk-priority"
                value={priority}
                placeholder={t.common.all}
                options={priorityOptions}
                onChange={(e) => {
                  setPage(1);
                  setPriority(e.target.value);
                }}
              />
            </FormField>
            <FormField label={hk.typeFilter} htmlFor="hk-type">
              <Select
                id="hk-type"
                value={taskType}
                placeholder={t.common.all}
                options={typeOptions}
                onChange={(e) => {
                  setPage(1);
                  setTaskType(e.target.value);
                }}
              />
            </FormField>
            <RoomOptionSelect
              id="hk-room"
              label={hk.room}
              value={roomId}
              placeholder={t.common.all}
              searchPlaceholder={t.operations.roomSearchPlaceholder}
              loadMoreLabel={t.operations.loadMore}
              loadingLabel={t.common.loading}
              emptyLabel={t.operations.roomsEmpty}
              onChange={(next) => {
                setPage(1);
                setRoomId(next);
              }}
            />
            <FormField label={hk.dateFilter} htmlFor="hk-date">
              <Input
                id="hk-date"
                type="date"
                value={date}
                onChange={(e) => {
                  setPage(1);
                  setDate(e.target.value);
                }}
              />
            </FormField>
            <FormField label={hk.orderingPriority} htmlFor="hk-ordering">
              <Select
                id="hk-ordering"
                value={ordering}
                placeholder={t.common.all}
                options={[{ value: "priority", label: hk.priorityLabel }]}
                onChange={(e) => {
                  setPage(1);
                  setOrdering(e.target.value);
                }}
              />
            </FormField>
            <Switch
              id="hk-mine"
              checked={mineOnly}
              onChange={(v) => {
                setPage(1);
                setMineOnly(v);
              }}
              label={hk.mineOnly}
            />
          </FilterBar>
        </form>

        {/* STABLE polite live region — always mounted; announces the settled
            result count by a text change (a11y M1). */}
        <div
          className="sr-only"
          aria-live="polite"
          aria-atomic="true"
          data-testid="hk-results-announce"
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
            aria-label={hk.title}
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
              <EmptyState title={hk.empty} hint={hk.emptyHint} icon={Brush} />
            ) : (
              <>
                <div
                  className="op-grid"
                  role="list"
                  aria-label={hk.title}
                  aria-busy={backgroundRefreshing}
                >
                  {rows.map((row) => (
                    <div role="listitem" key={row.id}>
                      <HkCard
                        row={row}
                        can={can}
                        busyId={busyId}
                        run={run}
                        onAssign={setAssignTask}
                        onComplete={setCompleteTask}
                        onCancel={setCancelTask}
                        onReject={setRejectTask}
                        onEditPriority={setPriorityTask}
                        onComeBack={setComeBackTask}
                        onReportDefect={openDefect}
                        onRegisterFound={openFound}
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

      <CreateTaskModal
        open={createOpen}
        initialRoom={quickRoom}
        onClose={() => {
          setCreateOpen(false);
          setQuickRoom(0);
        }}
        onSaved={() => {
          setCreateOpen(false);
          setQuickRoom(0);
          notify(hk.created);
          reloadAfterAction();
        }}
      />
      <CompleteModal
        task={completeTask}
        onClose={() => setCompleteTask(null)}
        onDone={() => {
          setCompleteTask(null);
          notify(hk.completedMsg);
          reloadAfterAction();
        }}
      />
      <ComeBackLaterModal
        task={comeBackTask}
        onClose={() => setComeBackTask(null)}
        onDone={() => {
          setComeBackTask(null);
          notify(hk.comeBackLaterMsg);
          reloadAfterAction();
        }}
      />
      <CancelModal
        task={cancelTask}
        onClose={() => setCancelTask(null)}
        onDone={() => {
          setCancelTask(null);
          notify(hk.cancelledMsg);
          reloadAfterAction();
        }}
      />
      <AssignModal
        open={assignTask !== null}
        labels={{
          title: hk.assignTitle,
          staffMember: hk.assignTo,
          assignToMe: hk.assignMe,
          unassign: hk.unassign,
          unassigned: hk.unassigned,
        }}
        currentAssignee={assignTask?.assigned_to ?? null}
        allowUnassign={Boolean(assignTask?.assigned_to)}
        onClose={() => setAssignTask(null)}
        onAssign={async (userId) => {
          if (!assignTask) return;
          await assignHousekeepingTask(assignTask.id, userId);
          setAssignTask(null);
          notify(userId === null ? t.operations.saved : hk.assignedMsg);
          reloadAfterAction();
        }}
      />
      <RejectInspectionModal
        task={rejectTask}
        onClose={() => setRejectTask(null)}
        onDone={() => {
          setRejectTask(null);
          notify(t.operations.saved);
          reloadAfterAction();
        }}
      />
      <PriorityModal
        task={priorityTask}
        onClose={() => setPriorityTask(null)}
        onDone={() => {
          setPriorityTask(null);
          notify(t.operations.saved);
          reloadAfterAction();
        }}
      />
      <CreateRequestModal
        open={defectRoom !== null}
        presetRoom={defectRoom?.id}
        presetRoomLabel={defectRoom?.label}
        onClose={() => setDefectRoom(null)}
        onSaved={() => {
          setDefectRoom(null);
          notify(t.operations.mt.created);
          reloadAfterAction();
        }}
      />
      <CreateItemModal
        open={foundRoom !== null}
        presetRoom={foundRoom?.id}
        presetRoomLabel={foundRoom?.label}
        onClose={() => setFoundRoom(null)}
        onSaved={() => {
          setFoundRoom(null);
          notify(t.operations.lf.created);
          reloadAfterAction();
        }}
      />
    </>
  );
}

/**
 * One cleaning task as a card. Presentational + props-driven: all permission and
 * action wiring lives in the parent (passed as callbacks), and the parent's
 * async `run` handles the reload + focus restoration. Extracted from an inline
 * render function into a real component so the a11y-M1 ref plumbing in the parent
 * is never traced as a "ref access during render" (mirrors the GuestCard shape).
 */
function HkCard({
  row,
  can,
  busyId,
  run,
  onAssign,
  onComplete,
  onCancel,
  onReject,
  onEditPriority,
  onComeBack,
  onReportDefect,
  onRegisterFound,
}: {
  row: HousekeepingTaskListItem;
  can: (...codes: string[]) => boolean;
  busyId: number | null;
  run: (id: number, action: () => Promise<unknown>, successMessage: string) => void;
  onAssign: (row: HousekeepingTaskListItem) => void;
  onComplete: (row: HousekeepingTaskListItem) => void;
  onCancel: (row: HousekeepingTaskListItem) => void;
  onReject: (row: HousekeepingTaskListItem) => void;
  onEditPriority: (row: HousekeepingTaskListItem) => void;
  onComeBack: (row: HousekeepingTaskListItem) => void;
  onReportDefect: (row: HousekeepingTaskListItem) => void;
  onRegisterFound: (row: HousekeepingTaskListItem) => void;
}) {
  const { t, locale } = useI18n();
  const hk = t.operations.hk;

  const active = ["pending", "assigned", "in_progress"].includes(row.status);
  const canStart = can("housekeeping.status_update");
  const canAssign = can("housekeeping.assign");

  // ONE primary action, computed from state + permission (§4).
  let primary: React.ComponentProps<typeof OperationCard>["primary"] = null;
  let primaryKind = "";
  if (row.status === "pending" || row.status === "assigned") {
    if (!row.assigned_to && canAssign) {
      primaryKind = "assign";
      primary = { label: hk.assign, icon: UserCheck, onClick: () => onAssign(row) };
    } else if (canStart) {
      primaryKind = "start";
      primary = {
        label: hk.start,
        icon: Play,
        loading: busyId === row.id,
        onClick: () =>
          run(row.id, () => setHousekeepingStatus(row.id, "in_progress"), hk.startedMsg),
      };
    } else if (canAssign) {
      primaryKind = "assign";
      primary = { label: hk.reassign, icon: UserCheck, onClick: () => onAssign(row) };
    }
  } else if (row.status === "in_progress" && canStart) {
    primaryKind = "complete";
    primary = {
      label: hk.complete,
      icon: CheckCircle2,
      onClick: () => onComplete(row),
    };
  } else if (row.status === "awaiting_inspection" && can("housekeeping.inspect")) {
    primaryKind = "approve";
    primary = {
      label: hk.approveInspection,
      icon: ClipboardCheck,
      loading: busyId === row.id,
      onClick: () => run(row.id, () => approveInspection(row.id), t.operations.saved),
    };
  }

  const menu: OperationMenuItem[] = [];
  if ((row.status === "pending" || row.status === "assigned") && canStart && primaryKind !== "start") {
    menu.push({
      key: "start",
      label: hk.start,
      icon: Play,
      onSelect: () =>
        run(row.id, () => setHousekeepingStatus(row.id, "in_progress"), hk.startedMsg),
    });
  }
  if (active && canAssign && primaryKind !== "assign") {
    menu.push({
      key: "assign",
      label: row.assigned_to ? hk.reassign : hk.assign,
      icon: UserCheck,
      onSelect: () => onAssign(row),
    });
  }
  if (row.status === "in_progress" && canStart) {
    menu.push({
      key: "comeBack",
      label: hk.comeBackLater,
      icon: PauseCircle,
      onSelect: () => onComeBack(row),
    });
  }
  if (row.status === "awaiting_inspection" && can("housekeeping.inspect")) {
    menu.push({
      key: "reject",
      label: hk.rejectInspection,
      icon: XCircle,
      danger: true,
      onSelect: () => onReject(row),
    });
  }
  if (active && can("housekeeping.update")) {
    menu.push({
      key: "priority",
      label: hk.editPriority,
      icon: SlidersHorizontal,
      onSelect: () => onEditPriority(row),
    });
  }
  if (active && row.room !== null && can("maintenance.create")) {
    menu.push({
      key: "defect",
      label: hk.reportDefect,
      icon: Wrench,
      onSelect: () => onReportDefect(row),
    });
  }
  if (active && row.room !== null && can("lost_found.create")) {
    menu.push({
      key: "found",
      label: hk.registerFound,
      icon: PackageSearch,
      onSelect: () => onRegisterFound(row),
    });
  }
  if (active && can("housekeeping.cancel")) {
    menu.push({
      key: "cancel",
      label: t.common.cancel,
      icon: XCircle,
      danger: true,
      onSelect: () => onCancel(row),
    });
  }

  const duration = formatDuration(row.started_at, row.completed_at, locale);

  return (
    <OperationCard
      accent={operationPriorityTone(row.priority)}
      number={row.task_number}
      title={<bdi dir="ltr">{row.room_number || "—"}</bdi>}
      ariaLabel={`${hk.title} ${row.task_number}`}
      moreLabel={t.operations.moreActions}
      badges={
        <>
          <Badge tone={housekeepingStatusTone(row.status)} variant="filled">
            {hk.status[row.status]}
          </Badge>
          <Badge tone={operationPriorityTone(row.priority)}>
            {t.operations.priority[row.priority]}
          </Badge>
          {row.is_occupied ? (
            <Badge tone="info" icon={BedDouble}>
              {hk.occupied}
            </Badge>
          ) : null}
          {row.upcoming_arrival.has_upcoming ? (
            <Badge tone="warning" variant="outline" icon={PlaneLanding}>
              {row.upcoming_arrival.arrival_date
                ? `${hk.arrivalSoon} · ${formatDate(row.upcoming_arrival.arrival_date, locale)}`
                : hk.arrivalSoon}
            </Badge>
          ) : null}
          {row.status === "completed" && row.service_outcome ? (
            <Badge tone="neutral">{hk.serviceOutcome[row.service_outcome]}</Badge>
          ) : null}
        </>
      }
      facts={[
        { key: "type", label: hk.typeLabel, value: hk.types[row.task_type], icon: Brush },
        { key: "unit", label: hk.unitType, value: row.room_type_name || "—", icon: Tag },
        {
          key: "floor",
          label: hk.floor,
          value: row.floor_name || row.floor_number || "—",
          icon: Layers,
        },
        {
          key: "assignee",
          label: hk.assignee,
          value: row.assigned_to_name || hk.unassigned,
          icon: UserCheck,
        },
        {
          key: "requested",
          label: hk.requestedAt,
          value: formatDateTime(row.requested_at, locale),
          icon: Clock,
        },
        ...(row.started_at
          ? [
              {
                key: "duration",
                label: hk.duration,
                value: duration ?? "—",
                icon: Timer,
              },
            ]
          : []),
      ]}
      primary={primary}
      menu={menu}
    />
  );
}

function CreateTaskModal({
  open,
  initialRoom = 0,
  onClose,
  onSaved,
}: {
  open: boolean;
  initialRoom?: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const hk = t.operations.hk;
  const [form, setForm] = useState<HousekeepingCreateBody>({ room: 0 });
  const [stays, setStays] = useState<Stay[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({
        room: initialRoom || 0,
        task_type: "daily_cleaning",
        priority: "normal",
        notes: "",
      });
      setError(null);
      listCurrentResidents()
        .then((res) => setStays(res.results))
        .catch(() => setStays([]));
    }
  }, [open, initialRoom]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.room) return setError(hk.roomRequired);
    setBusy(true);
    setError(null);
    try {
      await createHousekeepingTask(form);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const stayOptions = stays.map((s) => ({
    value: String(s.id),
    label: `${s.room_number} — ${s.primary_guest_name}`,
  }));
  const typeOptions = TASK_TYPES.map((v) => ({ value: v, label: hk.types[v] }));
  const priorityOptions = PRIORITIES.map((p) => ({
    value: p,
    label: t.operations.priority[p],
  }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={hk.create}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="hk-create-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="hk-create-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <RoomOptionSelect
          id="hkc-room"
          label={hk.room}
          value={form.room || null}
          placeholder={hk.roomRequired}
          searchPlaceholder={t.operations.roomSearchPlaceholder}
          loadMoreLabel={t.operations.loadMore}
          loadingLabel={t.common.loading}
          emptyLabel={t.operations.roomsEmpty}
          onChange={(next) => setForm((p) => ({ ...p, room: next ?? 0 }))}
        />
        <div className="form-grid">
          <FormField label={hk.stay} htmlFor="hkc-stay">
            <Select
              id="hkc-stay"
              value={form.stay ? String(form.stay) : ""}
              placeholder={hk.noStay}
              options={stayOptions}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  stay: e.target.value ? Number(e.target.value) : null,
                }))
              }
            />
          </FormField>
          <FormField label={hk.typeLabel} htmlFor="hkc-type">
            <Select
              id="hkc-type"
              value={form.task_type ?? "daily_cleaning"}
              options={typeOptions}
              onChange={(e) => setForm((p) => ({ ...p, task_type: e.target.value }))}
            />
          </FormField>
          <FormField label={t.operations.priorityLabel} htmlFor="hkc-priority">
            <Select
              id="hkc-priority"
              value={form.priority ?? "normal"}
              options={priorityOptions}
              onChange={(e) => setForm((p) => ({ ...p, priority: e.target.value }))}
            />
          </FormField>
        </div>
        <FormField label={hk.notes} htmlFor="hkc-notes">
          <Input
            id="hkc-notes"
            value={form.notes ?? ""}
            onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
          />
        </FormField>
        <FormField label={hk.internalNotes} htmlFor="hkc-inotes">
          <Input
            id="hkc-inotes"
            value={form.internal_notes ?? ""}
            onChange={(e) => setForm((p) => ({ ...p, internal_notes: e.target.value }))}
          />
        </FormField>
      </form>
    </Modal>
  );
}

/**
 * Completion is state-aware (§4). An OCCUPIED room records a mandatory service
 * result and NEVER offers "mark available"; a VACANT (checkout) room's normal
 * completion may release it through the server guard — there is no free
 * mark-available control anywhere.
 */
function CompleteModal({
  task,
  onClose,
  onDone,
}: {
  task: HousekeepingTaskListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const hk = t.operations.hk;
  const occupied = task?.is_occupied ?? false;
  const [outcome, setOutcome] = useState<HousekeepingServiceOutcome>("cleaned");
  const [markAvailable, setMarkAvailable] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (task) {
      setOutcome("cleaned");
      setMarkAvailable(false);
      setNote("");
      setError(null);
    }
  }, [task]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!task) return;
    setBusy(true);
    setError(null);
    try {
      if (occupied) {
        await completeHousekeepingTask(task.id, false, note, outcome);
      } else {
        await completeHousekeepingTask(task.id, markAvailable, note);
      }
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const outcomeOptions = SERVICE_OUTCOMES.map((o) => ({
    value: o,
    label: hk.serviceOutcome[o],
  }));
  const afterOptions = [
    { value: "keep", label: hk.afterCompleteKeep },
    { value: "available", label: hk.afterCompleteAvailable },
  ];

  return (
    <Modal
      open={task !== null}
      onClose={onClose}
      title={hk.completeTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="hk-complete-form" type="submit" loading={busy}>
            {hk.complete}
          </Button>
        </>
      }
    >
      <form id="hk-complete-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        {occupied ? (
          <>
            <Alert tone="info">{hk.completeOccupiedHint}</Alert>
            <FormField label={hk.serviceOutcomeLabel} htmlFor="hk-complete-outcome">
              <Select
                id="hk-complete-outcome"
                value={outcome}
                options={outcomeOptions}
                onChange={(e) =>
                  setOutcome(e.target.value as HousekeepingServiceOutcome)
                }
              />
            </FormField>
          </>
        ) : (
          <>
            <p className="muted">{hk.completeVacantHint}</p>
            <FormField label={hk.afterComplete} htmlFor="hk-complete-after">
              <Select
                id="hk-complete-after"
                value={markAvailable ? "available" : "keep"}
                options={afterOptions}
                onChange={(e) => setMarkAvailable(e.target.value === "available")}
              />
            </FormField>
          </>
        )}
        <FormField label={hk.notes} htmlFor="hk-complete-note">
          <Input
            id="hk-complete-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function ComeBackLaterModal({
  task,
  onClose,
  onDone,
}: {
  task: HousekeepingTaskListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const hk = t.operations.hk;
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (task) {
      setNote("");
      setError(null);
    }
  }, [task]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!task) return;
    setBusy(true);
    setError(null);
    try {
      await comeBackLaterHousekeepingTask(task.id, { note: note.trim() || undefined });
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={task !== null}
      onClose={onClose}
      title={hk.comeBackLaterTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="hk-comeback-form" type="submit" loading={busy}>
            {hk.comeBackLater}
          </Button>
        </>
      }
    >
      <form id="hk-comeback-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <p className="muted">{hk.comeBackLaterHint}</p>
        <FormField label={hk.notes} htmlFor="hk-comeback-note">
          <Textarea
            id="hk-comeback-note"
            rows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function CancelModal({
  task,
  onClose,
  onDone,
}: {
  task: HousekeepingTaskListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const hk = t.operations.hk;
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (task) {
      setReason("");
      setError(null);
    }
  }, [task]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!task) return;
    if (!reason.trim()) return setError(t.errors.validation);
    setBusy(true);
    setError(null);
    try {
      await cancelHousekeepingTask(task.id, reason.trim());
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={task !== null}
      onClose={onClose}
      title={hk.cancelTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.close}
          </Button>
          <Button form="hk-cancel-form" type="submit" variant="danger" loading={busy}>
            {t.common.cancel}
          </Button>
        </>
      }
    >
      <form id="hk-cancel-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={hk.cancelReason} htmlFor="hk-cancel-reason">
          <Input
            id="hk-cancel-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function RejectInspectionModal({
  task,
  onClose,
  onDone,
}: {
  task: HousekeepingTaskListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const hk = t.operations.hk;
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (task) {
      setReason("");
      setError(null);
    }
  }, [task]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!task) return;
    if (!reason.trim()) return setError(t.operations.errors.inspectionReasonRequired);
    setBusy(true);
    setError(null);
    try {
      await rejectInspection(task.id, reason.trim());
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={task !== null}
      onClose={onClose}
      title={hk.rejectInspection}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.close}
          </Button>
          <Button form="hk-reject-form" type="submit" variant="danger" loading={busy}>
            {hk.rejectInspection}
          </Button>
        </>
      }
    >
      <form id="hk-reject-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={hk.rejectReason} htmlFor="hk-reject-reason">
          <Input
            id="hk-reject-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function PriorityModal({
  task,
  onClose,
  onDone,
}: {
  task: HousekeepingTaskListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const hk = t.operations.hk;
  const [priority, setPriority] = useState<OperationPriority>("normal");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (task) {
      setPriority(task.priority);
      setError(null);
    }
  }, [task]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!task) return;
    setBusy(true);
    setError(null);
    try {
      await updateHousekeepingTask(task.id, { priority });
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const priorityOptions = PRIORITIES.map((p) => ({
    value: p,
    label: t.operations.priority[p],
  }));

  return (
    <Modal
      open={task !== null}
      onClose={onClose}
      title={hk.editPriority}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="hk-priority-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="hk-priority-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={t.operations.priorityLabel} htmlFor="hk-priority-select">
          <Select
            id="hk-priority-select"
            value={priority}
            options={priorityOptions}
            onChange={(e) => setPriority(e.target.value as OperationPriority)}
          />
        </FormField>
      </form>
    </Modal>
  );
}
