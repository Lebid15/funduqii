"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Brush, Play, Plus, UserCheck } from "lucide-react";

import { useQuickAction } from "@/lib/useQuickAction";

import {
  Alert,
  Badge,
  Button,
  Card,
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
  Switch,
  useToast,
  type Column,
} from "@/components/ui";
import {
  assignHousekeepingTask,
  cancelHousekeepingTask,
  completeHousekeepingTask,
  createHousekeepingTask,
  listHousekeepingTasks,
  setHousekeepingStatus,
  type HousekeepingCreateBody,
} from "@/lib/api/operations";
import { listRooms } from "@/lib/api/rooms";
import { listCurrentResidents } from "@/lib/api/stays";
import { messageForError } from "@/lib/api/errors";
import type {
  HousekeepingTaskListItem,
  HousekeepingTaskType,
  OperationPriority,
  Room,
  Stay,
} from "@/lib/api/types";
import { formatDateTime, housekeepingStatusTone, operationPriorityTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useCurrentUser } from "@/lib/session/CurrentUserContext";

const PAGE_SIZE = 25;
const TASK_TYPES: HousekeepingTaskType[] = [
  "checkout_cleaning",
  "daily_cleaning",
  "deep_cleaning",
  "inspection",
  "other",
];
const STATUSES = ["pending", "assigned", "in_progress", "completed", "cancelled"] as const;
const PRIORITIES: OperationPriority[] = ["low", "normal", "high", "urgent"];

export function HousekeepingTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const me = useCurrentUser();

  const [rows, setRows] = useState<HousekeepingTaskListItem[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [room, setRoom] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [quickRoom, setQuickRoom] = useState(0);
  // Quick action: ?action=new opens the EXISTING task modal once — with an
  // optional preselected room (operational board deep-link).
  useQuickAction("new", (params) => {
    setQuickRoom(Number(params.get("room")) || 0);
    setCreateOpen(true);
  });
  const [completeTask, setCompleteTask] = useState<HousekeepingTaskListItem | null>(null);
  const [cancelTask, setCancelTask] = useState<HousekeepingTaskListItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tasks, roomList] = await Promise.all([
        listHousekeepingTasks({
          page,
          search: query || undefined,
          status: status || undefined,
          priority: priority || undefined,
          room: room ? Number(room) : undefined,
        }),
        listRooms({ page_size: 100 }),
      ]);
      setRows(tasks.results);
      setCount(tasks.count);
      setRooms(roomList.results);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, query, status, priority, room, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(
    id: number,
    action: () => Promise<unknown>,
    successMessage: string,
  ) {
    setBusyId(id);
    try {
      await action();
      notify(successMessage);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusyId(null);
    }
  }

  const hk = t.operations.hk;
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const roomOptions = rooms.map((r) => ({ value: String(r.id), label: r.number }));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: hk.status[s] }));
  const priorityOptions = PRIORITIES.map((p) => ({
    value: p,
    label: t.operations.priority[p],
  }));

  const columns: Column<HousekeepingTaskListItem>[] = [
    { key: "task_number", header: hk.taskNumber },
    { key: "room_number", header: hk.room, render: (r) => r.room_number || "—" },
    { key: "task_type", header: hk.typeLabel, render: (r) => hk.types[r.task_type] },
    {
      key: "priority",
      header: t.operations.priorityLabel,
      render: (r) => (
        <Badge tone={operationPriorityTone(r.priority)}>
          {t.operations.priority[r.priority]}
        </Badge>
      ),
    },
    {
      key: "status",
      header: t.common.status,
      render: (r) => (
        <Badge tone={housekeepingStatusTone(r.status)}>{hk.status[r.status]}</Badge>
      ),
    },
    {
      key: "assigned_to_name",
      header: hk.assignee,
      render: (r) => r.assigned_to_name || hk.unassigned,
    },
    {
      key: "requested_at",
      header: hk.requestedAt,
      render: (r) => formatDateTime(r.requested_at, locale),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => {
        const active = ["pending", "assigned", "in_progress"].includes(r.status);
        if (!active) return <span className="muted small">—</span>;
        return (
          <div className="table__actions">
            {!r.assigned_to && me ? (
              <Button
                size="sm"
                variant="secondary"
                icon={UserCheck}
                loading={busyId === r.id}
                onClick={() =>
                  run(r.id, () => assignHousekeepingTask(r.id, me.id), hk.assignedMsg)
                }
              >
                {hk.assignToMe}
              </Button>
            ) : null}
            {r.status !== "in_progress" ? (
              <Button
                size="sm"
                variant="secondary"
                icon={Play}
                loading={busyId === r.id}
                onClick={() =>
                  run(
                    r.id,
                    () => setHousekeepingStatus(r.id, "in_progress"),
                    hk.startedMsg,
                  )
                }
              >
                {hk.start}
              </Button>
            ) : null}
            <Button size="sm" onClick={() => setCompleteTask(r)}>
              {hk.complete}
            </Button>
            <Button size="sm" variant="danger" onClick={() => setCancelTask(r)}>
              {t.common.cancel}
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <>
      <Card>
        <SectionHeader
          title={hk.title}
          actions={
            <Button icon={Plus} onClick={() => setCreateOpen(true)}>
              {hk.create}
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
            <FormField label={hk.room} htmlFor="hk-room">
              <Select
                id="hk-room"
                value={room}
                placeholder={t.common.all}
                options={roomOptions}
                onChange={(e) => {
                  setPage(1);
                  setRoom(e.target.value);
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
            <EmptyState title={hk.empty} hint={hk.emptyHint} icon={Brush} />
          ) : (
            <>
              <DataTable
                caption={hk.title}
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

      <CreateTaskModal
        open={createOpen}
        rooms={rooms}
        initialRoom={quickRoom}
        onClose={() => { setCreateOpen(false); setQuickRoom(0); }}
        onSaved={() => {
          setCreateOpen(false);
          setQuickRoom(0);
          notify(hk.created);
          load();
        }}
      />
      <CompleteModal
        task={completeTask}
        onClose={() => setCompleteTask(null)}
        onDone={() => {
          setCompleteTask(null);
          notify(hk.completedMsg);
          load();
        }}
      />
      <CancelModal
        task={cancelTask}
        onClose={() => setCancelTask(null)}
        onDone={() => {
          setCancelTask(null);
          notify(hk.cancelledMsg);
          load();
        }}
      />
    </>
  );
}

function CreateTaskModal({
  open,
  rooms,
  initialRoom = 0,
  onClose,
  onSaved,
}: {
  open: boolean;
  rooms: Room[];
  /** Optional preselected room (operational board deep-link). */
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
      setForm({ room: initialRoom || 0, task_type: "daily_cleaning", priority: "normal", notes: "" });
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

  const roomOptions = rooms.map((r) => ({ value: String(r.id), label: r.number }));
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
        <div className="form-grid">
          <FormField label={hk.room} htmlFor="hkc-room">
            <Select
              id="hkc-room"
              value={form.room ? String(form.room) : ""}
              placeholder={hk.roomRequired}
              options={roomOptions}
              onChange={(e) => setForm((p) => ({ ...p, room: Number(e.target.value) }))}
            />
          </FormField>
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
  const [markAvailable, setMarkAvailable] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (task) {
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
      await completeHousekeepingTask(task.id, markAvailable, note);
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
        <p className="muted">{hk.completeHint}</p>
        <Switch
          id="hk-mark-available"
          checked={markAvailable}
          onChange={setMarkAvailable}
          label={markAvailable ? hk.markAvailable : hk.keepDirty}
        />
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
