"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  BedDouble,
  CheckCircle2,
  CircleSlash,
  Clock,
  Hammer,
  Play,
  Plus,
  Tag,
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
  assignMaintenanceRequest,
  cancelMaintenanceRequest,
  closeMaintenanceRequest,
  createMaintenanceRequest,
  getOperationsOverview,
  listMaintenanceRequests,
  resolveMaintenanceRequest,
  setMaintenanceStatus,
  type MaintenanceCreateBody,
  type RoomNextStatus,
} from "@/lib/api/operations";
import { listStaff } from "@/lib/api/staff";
import { messageForError } from "@/lib/api/errors";
import type {
  MaintenanceCategory,
  MaintenanceRequestListItem,
  OperationPriority,
} from "@/lib/api/types";
import { formatDateTime, maintenanceStatusTone, operationPriorityTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { OperationCard, type OperationMenuItem } from "./OperationCard";
import { RoomOptionSelect } from "./RoomOptionSelect";
import { StatCards, type OperationStat } from "./StatCards";
import { AssignModal, useCan } from "./operationsShared";

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

interface MtStats {
  open: number | null;
  inRepair: number | null;
  awaitingClose: number | null;
  blockingRooms: number | null;
}

export function MaintenanceTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const mt = t.operations.mt;

  const [rows, setRows] = useState<MaintenanceRequestListItem[]>([]);
  const [count, setCount] = useState(0);
  const [stats, setStats] = useState<MtStats>({
    open: null,
    inRepair: null,
    awaitingClose: null,
    blockingRooms: null,
  });
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
  useQuickAction("new", (params) => {
    setQuickRoom(Number(params.get("room")) || 0);
    setCreateOpen(true);
  });
  const [closeReq, setCloseReq] = useState<MaintenanceRequestListItem | null>(null);
  const [cancelReq, setCancelReq] = useState<MaintenanceRequestListItem | null>(null);
  const [assignReq, setAssignReq] = useState<MaintenanceRequestListItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [reqs, open, inRepair, resolved, overview] = await Promise.all([
        listMaintenanceRequests({
          page,
          search: query || undefined,
          status: status || undefined,
          category: category || undefined,
          priority: priority || undefined,
        }),
        listMaintenanceRequests({ status: "open", page: 1 }),
        listMaintenanceRequests({ status: "in_progress", page: 1 }),
        listMaintenanceRequests({ status: "resolved", page: 1 }),
        getOperationsOverview(),
      ]);
      setRows(reqs.results);
      setCount(reqs.count);
      setStats({
        open: open.count,
        inRepair: inRepair.count,
        awaitingClose: resolved.count,
        blockingRooms: overview.rooms_under_maintenance,
      });
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

  function applyStatusFilter(next: string) {
    setPage(1);
    setStatus((current) => (current === next ? "" : next));
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: mt.status[s] }));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: mt.categories[c] }));
  const priorityOptions = PRIORITIES.map((p) => ({
    value: p,
    label: t.operations.priority[p],
  }));

  const statCards: OperationStat[] = [
    {
      key: "open",
      label: mt.stats.new,
      value: stats.open,
      icon: Wrench,
      tone: "warning",
      active: status === "open",
      onFilter: () => applyStatusFilter("open"),
    },
    {
      key: "inRepair",
      label: mt.stats.inRepair,
      value: stats.inRepair,
      icon: Hammer,
      tone: "primary",
      active: status === "in_progress",
      onFilter: () => applyStatusFilter("in_progress"),
    },
    {
      key: "blockingRooms",
      label: mt.stats.blockingRooms,
      value: stats.blockingRooms,
      icon: CircleSlash,
      tone: stats.blockingRooms && stats.blockingRooms > 0 ? "danger" : "neutral",
    },
    {
      key: "awaitingClose",
      label: mt.stats.awaitingClose,
      value: stats.awaitingClose,
      icon: CheckCircle2,
      tone: "info",
      active: status === "resolved",
      onFilter: () => applyStatusFilter("resolved"),
    },
  ];

  function renderCard(row: MaintenanceRequestListItem) {
    const active = ["open", "assigned", "in_progress"].includes(row.status);
    const canStatus = can("maintenance.status_update");

    let primary: React.ComponentProps<typeof OperationCard>["primary"] = null;
    if ((row.status === "open" || row.status === "assigned") && canStatus) {
      primary = {
        label: mt.start,
        icon: Play,
        loading: busyId === row.id,
        onClick: () =>
          run(row.id, () => setMaintenanceStatus(row.id, "in_progress"), mt.startedMsg),
      };
    } else if (row.status === "in_progress" && canStatus) {
      primary = {
        label: mt.resolve,
        icon: CheckCircle2,
        loading: busyId === row.id,
        onClick: () => run(row.id, () => resolveMaintenanceRequest(row.id), mt.resolvedMsg),
      };
    } else if (row.status === "resolved" && can("maintenance.close")) {
      primary = { label: mt.close, icon: CheckCircle2, onClick: () => setCloseReq(row) };
    }

    const menu: OperationMenuItem[] = [];
    if (active && can("maintenance.assign")) {
      menu.push({
        key: "assign",
        label: row.assigned_to ? mt.reassign : mt.assign,
        icon: UserCheck,
        onSelect: () => setAssignReq(row),
      });
    }
    if (active && can("maintenance.cancel")) {
      menu.push({
        key: "cancel",
        label: t.common.cancel,
        icon: XCircle,
        danger: true,
        onSelect: () => setCancelReq(row),
      });
    }

    const blocking = row.affects_room_availability;
    const blockLabel =
      blocking && row.room_block_status !== "none"
        ? `${mt.blocksRoom} · ${mt.blocks[row.room_block_status as "maintenance" | "out_of_service"]}`
        : mt.blocksRoom;

    return (
      <OperationCard
        accent={blocking ? "danger" : operationPriorityTone(row.priority)}
        number={row.request_number}
        title={row.title}
        ariaLabel={`${mt.title} ${row.request_number}`}
        moreLabel={t.operations.moreActions}
        badges={
          <>
            <Badge tone={maintenanceStatusTone(row.status)} variant="filled">
              {mt.status[row.status]}
            </Badge>
            <Badge tone={operationPriorityTone(row.priority)}>
              {t.operations.priority[row.priority]}
            </Badge>
            {blocking ? (
              <Badge tone="danger" variant="outline" icon={CircleSlash}>
                {blockLabel}
              </Badge>
            ) : null}
          </>
        }
        facts={[
          {
            key: "location",
            label: mt.room,
            value: row.room_number ? (
              <bdi dir="ltr">{row.room_number}</bdi>
            ) : (
              mt.commonArea
            ),
            icon: BedDouble,
          },
          {
            key: "category",
            label: mt.categoryLabel,
            value: mt.categories[row.category],
            icon: Tag,
          },
          {
            key: "assignee",
            label: mt.assignee,
            value: row.assigned_to_name || mt.unassigned,
            icon: UserCheck,
          },
          {
            key: "reported",
            label: mt.reportedAt,
            value: formatDateTime(row.reported_at, locale),
            icon: Clock,
          },
          ...(row.resolved_at
            ? [
                {
                  key: "resolved",
                  label: mt.resolvedAt,
                  value: formatDateTime(row.resolved_at, locale),
                  icon: CheckCircle2,
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
      <StatCards stats={statCards} loading={loading} ariaLabel={mt.title} />

      <Card>
        <SectionHeader
          title={mt.title}
          actions={
            can("maintenance.create") ? (
              <Button icon={Plus} onClick={() => setCreateOpen(true)}>
                {mt.create}
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
              <div className="op-grid" role="list" aria-label={mt.title}>
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

      <CreateRequestModal
        open={createOpen}
        presetRoom={quickRoom || undefined}
        onClose={() => {
          setCreateOpen(false);
          setQuickRoom(0);
        }}
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
      <AssignModal
        open={assignReq !== null}
        labels={{
          title: mt.assignTitle,
          staffMember: mt.assignTo,
          assignToMe: mt.assignMe,
          unassign: mt.unassign,
          unassigned: mt.unassigned,
        }}
        currentAssignee={assignReq?.assigned_to ?? null}
        allowUnassign={Boolean(assignReq?.assigned_to)}
        onClose={() => setAssignReq(null)}
        onAssign={async (userId) => {
          if (!assignReq) return;
          await assignMaintenanceRequest(assignReq.id, userId);
          setAssignReq(null);
          notify(userId === null ? t.operations.saved : mt.assignedMsg);
          load();
        }}
      />
    </>
  );
}

/**
 * Create a maintenance request. The room uses the async room-options picker
 * (§7). A FULL assignee Select is offered (not just assign-to-me); creating
 * WITH an assignee requires the assign permission server-side, and a 403 is
 * surfaced here as a clear, translated error.
 */
export function CreateRequestModal({
  open,
  presetRoom,
  presetRoomLabel,
  onClose,
  onSaved,
}: {
  open: boolean;
  presetRoom?: number;
  /** Known label for the preset room so it shows before the options fetch. */
  presetRoomLabel?: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const mt = t.operations.mt;
  const [form, setForm] = useState<MaintenanceCreateBody>({ title: "" });
  const [staffOptions, setStaffOptions] = useState<{ value: string; label: string }[]>([]);
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
        assigned_to: null,
      });
      setError(null);
      listStaff({ page_size: 100 })
        .then((res) =>
          setStaffOptions(
            res.results
              .filter((member) => member.is_active)
              .map((member) => ({ value: String(member.user_id), label: member.full_name })),
          ),
        )
        .catch(() => setStaffOptions([]));
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
        </div>
        <RoomOptionSelect
          id="mtc-room"
          label={mt.room}
          value={form.room ?? null}
          placeholder={mt.noRoom}
          searchPlaceholder={t.operations.roomSearchPlaceholder}
          loadMoreLabel={t.operations.loadMore}
          loadingLabel={t.common.loading}
          emptyLabel={t.operations.roomsEmpty}
          selectedLabel={presetRoomLabel}
          onChange={(next) => setForm((p) => ({ ...p, room: next }))}
        />
        <FormField label={mt.assignTo} htmlFor="mtc-assignee">
          <Select
            id="mtc-assignee"
            value={form.assigned_to ? String(form.assigned_to) : ""}
            placeholder={mt.unassigned}
            options={staffOptions}
            onChange={(e) =>
              setForm((p) => ({
                ...p,
                assigned_to: e.target.value ? Number(e.target.value) : null,
              }))
            }
          />
        </FormField>
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
