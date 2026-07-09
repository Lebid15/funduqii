"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, Play, Plus, UserCheck, Wrench } from "lucide-react";

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
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import {
  assignMaintenanceRequest,
  cancelMaintenanceRequest,
  closeMaintenanceRequest,
  createMaintenanceRequest,
  listMaintenanceRequests,
  resolveMaintenanceRequest,
  setMaintenanceStatus,
  type MaintenanceCreateBody,
  type RoomNextStatus,
} from "@/lib/api/operations";
import { listRooms } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type {
  MaintenanceCategory,
  MaintenanceRequestListItem,
  OperationPriority,
  Room,
} from "@/lib/api/types";
import { formatDateTime, maintenanceStatusTone, operationPriorityTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useCurrentUser } from "@/lib/session/CurrentUserContext";

const PAGE_SIZE = 25;
const CATEGORIES: MaintenanceCategory[] = [
  "electrical",
  "plumbing",
  "hvac",
  "furniture",
  "cleaning_issue",
  "safety",
  "other",
];
const STATUSES = ["open", "assigned", "in_progress", "resolved", "closed", "cancelled"] as const;
const PRIORITIES: OperationPriority[] = ["low", "normal", "high", "urgent"];

export function MaintenanceTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const me = useCurrentUser();

  const [rows, setRows] = useState<MaintenanceRequestListItem[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [quickRoom, setQuickRoom] = useState(0);
  // Quick action: ?action=new opens the EXISTING request modal once — with
  // an optional preselected room (operational board deep-link).
  useQuickAction("new", (params) => {
    setQuickRoom(Number(params.get("room")) || 0);
    setCreateOpen(true);
  });
  const [closeReq, setCloseReq] = useState<MaintenanceRequestListItem | null>(null);
  const [cancelReq, setCancelReq] = useState<MaintenanceRequestListItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [reqs, roomList] = await Promise.all([
        listMaintenanceRequests({
          page,
          search: query || undefined,
          status: status || undefined,
          category: category || undefined,
          priority: priority || undefined,
        }),
        listRooms({ page_size: 100 }),
      ]);
      setRows(reqs.results);
      setCount(reqs.count);
      setRooms(roomList.results);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, query, status, category, priority, t]);

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

  const mt = t.operations.mt;
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: mt.status[s] }));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: mt.categories[c] }));
  const priorityOptions = PRIORITIES.map((p) => ({
    value: p,
    label: t.operations.priority[p],
  }));

  const columns: Column<MaintenanceRequestListItem>[] = [
    { key: "request_number", header: mt.requestNumber },
    { key: "title", header: mt.titleLabel },
    { key: "room_number", header: mt.room, render: (r) => r.room_number || "—" },
    { key: "category", header: mt.categoryLabel, render: (r) => mt.categories[r.category] },
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
        <Badge tone={maintenanceStatusTone(r.status)}>{mt.status[r.status]}</Badge>
      ),
    },
    {
      key: "reported_at",
      header: mt.reportedAt,
      render: (r) => formatDateTime(r.reported_at, locale),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => {
        const open = ["open", "assigned", "in_progress"].includes(r.status);
        if (r.status === "resolved") {
          return (
            <div className="table__actions">
              <Button size="sm" onClick={() => setCloseReq(r)}>
                {mt.close}
              </Button>
            </div>
          );
        }
        if (!open) return <span className="muted small">—</span>;
        return (
          <div className="table__actions">
            {!r.assigned_to && me ? (
              <Button
                size="sm"
                variant="secondary"
                icon={UserCheck}
                loading={busyId === r.id}
                onClick={() =>
                  run(r.id, () => assignMaintenanceRequest(r.id, me.id), mt.assignedMsg)
                }
              >
                {mt.assignToMe}
              </Button>
            ) : null}
            {r.status !== "in_progress" ? (
              <Button
                size="sm"
                variant="secondary"
                icon={Play}
                loading={busyId === r.id}
                onClick={() =>
                  run(r.id, () => setMaintenanceStatus(r.id, "in_progress"), mt.startedMsg)
                }
              >
                {mt.start}
              </Button>
            ) : null}
            <Button
              size="sm"
              icon={CheckCircle2}
              loading={busyId === r.id}
              onClick={() =>
                run(r.id, () => resolveMaintenanceRequest(r.id), mt.resolvedMsg)
              }
            >
              {mt.resolve}
            </Button>
            <Button size="sm" variant="danger" onClick={() => setCancelReq(r)}>
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
          title={mt.title}
          actions={
            <Button icon={Plus} onClick={() => setCreateOpen(true)}>
              {mt.create}
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
            <FormField label={t.common.search} htmlFor="mt-search">
              <Input
                id="mt-search"
                value={search}
                placeholder={mt.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
              />
            </FormField>
            <FormField label={t.common.status} htmlFor="mt-status">
              <Select
                id="mt-status"
                value={status}
                placeholder={t.common.all}
                options={statusOptions}
                onChange={(e) => {
                  setPage(1);
                  setStatus(e.target.value);
                }}
              />
            </FormField>
            <FormField label={mt.categoryLabel} htmlFor="mt-category">
              <Select
                id="mt-category"
                value={category}
                placeholder={t.common.all}
                options={categoryOptions}
                onChange={(e) => {
                  setPage(1);
                  setCategory(e.target.value);
                }}
              />
            </FormField>
            <FormField label={t.operations.priorityLabel} htmlFor="mt-priority">
              <Select
                id="mt-priority"
                value={priority}
                placeholder={t.common.all}
                options={priorityOptions}
                onChange={(e) => {
                  setPage(1);
                  setPriority(e.target.value);
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
            <EmptyState title={mt.empty} hint={mt.emptyHint} icon={Wrench} />
          ) : (
            <>
              <DataTable
                caption={mt.title}
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

      <CreateRequestModal
        open={createOpen}
        rooms={rooms}
        presetRoom={quickRoom || undefined}
        onClose={() => { setCreateOpen(false); setQuickRoom(0); }}
        onSaved={() => {
          setCreateOpen(false);
          setQuickRoom(0);
          notify(mt.created);
          load();
        }}
      />
      <CloseModal
        request={closeReq}
        onClose={() => setCloseReq(null)}
        onDone={() => {
          setCloseReq(null);
          notify(mt.closedMsg);
          load();
        }}
      />
      <CancelModal
        request={cancelReq}
        onClose={() => setCancelReq(null)}
        onDone={() => {
          setCancelReq(null);
          notify(mt.cancelledMsg);
          load();
        }}
      />
    </>
  );
}

export function CreateRequestModal({
  open,
  rooms,
  presetRoom,
  onClose,
  onSaved,
}: {
  open: boolean;
  rooms: Room[];
  presetRoom?: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const mt = t.operations.mt;
  const [form, setForm] = useState<MaintenanceCreateBody>({ title: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({
        title: "",
        description: "",
        category: "other",
        priority: "normal",
        room: presetRoom ?? null,
        affects_room_availability: false,
        room_block_status: "none",
      });
      setError(null);
    }
  }, [open, presetRoom]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.title.trim()) return setError(mt.titleRequired);
    setBusy(true);
    setError(null);
    try {
      await createMaintenanceRequest({
        ...form,
        room_block_status: form.affects_room_availability
          ? form.room_block_status === "none"
            ? "maintenance"
            : form.room_block_status
          : "none",
      });
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const roomOptions = rooms.map((r) => ({ value: String(r.id), label: r.number }));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: mt.categories[c] }));
  const priorityOptions = PRIORITIES.map((p) => ({
    value: p,
    label: t.operations.priority[p],
  }));
  const blockOptions = [
    { value: "maintenance", label: mt.blocks.maintenance },
    { value: "out_of_service", label: mt.blocks.out_of_service },
  ];

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={mt.create}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="mt-create-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="mt-create-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={mt.titleLabel} htmlFor="mtc-title">
          <Input
            id="mtc-title"
            value={form.title}
            onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))}
          />
        </FormField>
        <FormField label={mt.description} htmlFor="mtc-desc">
          <Textarea
            id="mtc-desc"
            rows={3}
            value={form.description ?? ""}
            onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
          />
        </FormField>
        <div className="form-grid">
          <FormField label={mt.categoryLabel} htmlFor="mtc-category">
            <Select
              id="mtc-category"
              value={form.category ?? "other"}
              options={categoryOptions}
              onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}
            />
          </FormField>
          <FormField label={t.operations.priorityLabel} htmlFor="mtc-priority">
            <Select
              id="mtc-priority"
              value={form.priority ?? "normal"}
              options={priorityOptions}
              onChange={(e) => setForm((p) => ({ ...p, priority: e.target.value }))}
            />
          </FormField>
          <FormField label={mt.room} htmlFor="mtc-room">
            <Select
              id="mtc-room"
              value={form.room ? String(form.room) : ""}
              placeholder={mt.noRoom}
              options={roomOptions}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  room: e.target.value ? Number(e.target.value) : null,
                }))
              }
            />
          </FormField>
        </div>
        <Switch
          id="mtc-affects"
          checked={form.affects_room_availability ?? false}
          onChange={(checked) =>
            setForm((p) => ({ ...p, affects_room_availability: checked }))
          }
          label={mt.affects}
        />
        {form.affects_room_availability ? (
          <FormField label={mt.blockLabel} htmlFor="mtc-block">
            <Select
              id="mtc-block"
              value={
                form.room_block_status === "out_of_service"
                  ? "out_of_service"
                  : "maintenance"
              }
              options={blockOptions}
              onChange={(e) =>
                setForm((p) => ({ ...p, room_block_status: e.target.value }))
              }
            />
          </FormField>
        ) : null}
        <FormField label={mt.internalNotes} htmlFor="mtc-inotes">
          <Input
            id="mtc-inotes"
            value={form.internal_notes ?? ""}
            onChange={(e) => setForm((p) => ({ ...p, internal_notes: e.target.value }))}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function CloseModal({
  request,
  onClose,
  onDone,
}: {
  request: MaintenanceRequestListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const mt = t.operations.mt;
  const [roomNext, setRoomNext] = useState<RoomNextStatus>("keep");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (request) {
      setRoomNext(request.room ? "dirty" : "keep");
      setNote("");
      setError(null);
    }
  }, [request]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!request) return;
    setBusy(true);
    setError(null);
    try {
      await closeMaintenanceRequest(request.id, roomNext, note);
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const nextOptions = [
    { value: "keep", label: mt.roomNext.keep },
    { value: "dirty", label: mt.roomNext.dirty },
    { value: "available", label: mt.roomNext.available },
  ];

  return (
    <Modal
      open={request !== null}
      onClose={onClose}
      title={mt.closeTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="mt-close-form" type="submit" loading={busy}>
            {mt.close}
          </Button>
        </>
      }
    >
      <form id="mt-close-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <p className="muted">{mt.closeHint}</p>
        {request?.room ? (
          <FormField label={mt.roomNextLabel} htmlFor="mt-close-next">
            <Select
              id="mt-close-next"
              value={roomNext}
              options={nextOptions}
              onChange={(e) => setRoomNext(e.target.value as RoomNextStatus)}
            />
          </FormField>
        ) : null}
        <FormField label={mt.resolutionNotes} htmlFor="mt-close-note">
          <Input
            id="mt-close-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function CancelModal({
  request,
  onClose,
  onDone,
}: {
  request: MaintenanceRequestListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const mt = t.operations.mt;
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (request) {
      setReason("");
      setError(null);
    }
  }, [request]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!request) return;
    if (!reason.trim()) return setError(t.errors.validation);
    setBusy(true);
    setError(null);
    try {
      await cancelMaintenanceRequest(request.id, reason.trim());
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={request !== null}
      onClose={onClose}
      title={mt.cancelTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.close}
          </Button>
          <Button form="mt-cancel-form" type="submit" variant="danger" loading={busy}>
            {t.common.cancel}
          </Button>
        </>
      }
    >
      <form id="mt-cancel-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={mt.cancelReason} htmlFor="mt-cancel-reason">
          <Input
            id="mt-cancel-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}
