"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ArrowLeftRight, Plus, Printer, Send } from "lucide-react";

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
  PrintDocumentLayout,
  SectionHeader,
  Select,
  useToast,
  type Column,
} from "@/components/ui";
import {
  acceptHandover,
  cancelHandover,
  createHandover,
  getHandoverVoucher,
  listHandovers,
  listShifts,
  rejectHandover,
  submitHandover,
  type HandoverBody,
} from "@/lib/api/shifts";
import { listStaff } from "@/lib/api/staff";
import { messageForError } from "@/lib/api/errors";
import type {
  HandoverStatus,
  HandoverVoucher,
  ShiftHandoverListItem,
  ShiftListItem,
  StaffMemberListItem,
} from "@/lib/api/types";
import { formatDateTime, handoverStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { PrintModal } from "../finance/shared";

const PAGE_SIZE = 25;
const STATUSES: HandoverStatus[] = ["draft", "submitted", "accepted", "rejected", "cancelled"];

export function HandoversTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const h = t.shifts.ho;

  const [rows, setRows] = useState<ShiftHandoverListItem[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [acceptTarget, setAcceptTarget] = useState<ShiftHandoverListItem | null>(null);
  const [rejectTarget, setRejectTarget] = useState<ShiftHandoverListItem | null>(null);
  const [cancelTarget, setCancelTarget] = useState<ShiftHandoverListItem | null>(null);
  const [voucher, setVoucher] = useState<HandoverVoucher | null>(null);

  async function openVoucher(row: ShiftHandoverListItem) {
    try {
      setVoucher(await getHandoverVoucher(row.id));
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listHandovers({
        page,
        search: query || undefined,
        status: status || undefined,
      });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, query, status, t]);

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
  const statusOptions = STATUSES.map((s) => ({ value: s, label: t.shifts.hoStatus[s] }));

  const columns: Column<ShiftHandoverListItem>[] = [
    { key: "handover_number", header: h.number },
    { key: "from_shift_number", header: h.fromShift },
    { key: "to_user_name", header: h.toUser },
    {
      key: "status",
      header: t.common.status,
      render: (r) => (
        <Badge tone={handoverStatusTone(r.status)}>{t.shifts.hoStatus[r.status]}</Badge>
      ),
    },
    {
      key: "created_at",
      header: t.common.createdAt,
      render: (r) => formatDateTime(r.created_at, locale),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => (
        <div className="table__actions">
          <Button size="sm" variant="ghost" icon={Printer} onClick={() => openVoucher(r)}>
            {t.shifts.print.printVoucher}
          </Button>
          {r.status === "draft" ? (
            <>
              <Button
                size="sm"
                icon={Send}
                loading={busyId === r.id}
                onClick={() => run(r.id, () => submitHandover(r.id), h.submittedMsg)}
              >
                {h.submit}
              </Button>
              <Button size="sm" variant="danger" onClick={() => setCancelTarget(r)}>
                {t.common.cancel}
              </Button>
            </>
          ) : null}
          {r.status === "submitted" ? (
            <>
              <Button size="sm" onClick={() => setAcceptTarget(r)}>
                {h.accept}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setRejectTarget(r)}>
                {h.reject}
              </Button>
              <Button size="sm" variant="danger" onClick={() => setCancelTarget(r)}>
                {t.common.cancel}
              </Button>
            </>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <Card>
        <SectionHeader
          title={h.title}
          actions={
            <Button icon={Plus} onClick={() => setCreateOpen(true)}>
              {h.create}
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
            <FormField label={t.common.search} htmlFor="ho-search">
              <Input
                id="ho-search"
                value={search}
                placeholder={h.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
              />
            </FormField>
            <FormField label={t.common.status} htmlFor="ho-status">
              <Select
                id="ho-status"
                value={status}
                placeholder={t.common.all}
                options={statusOptions}
                onChange={(e) => {
                  setPage(1);
                  setStatus(e.target.value);
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
            <EmptyState title={h.empty} hint={h.emptyHint} icon={ArrowLeftRight} />
          ) : (
            <>
              <DataTable caption={h.title} columns={columns} rows={rows} rowKey={(r) => r.id} />
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

      <HandoverFormModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSaved={() => {
          setCreateOpen(false);
          notify(h.createdMsg);
          load();
        }}
      />
      <ConfirmDialog
        open={acceptTarget !== null}
        title={h.acceptTitle}
        body={h.acceptBody}
        confirmLabel={h.accept}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        onClose={() => setAcceptTarget(null)}
        onConfirm={async () => {
          if (!acceptTarget) return;
          try {
            await acceptHandover(acceptTarget.id);
            notify(h.acceptedMsg);
            load();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setAcceptTarget(null);
          }
        }}
      />
      <ReasonModal
        target={rejectTarget}
        title={h.rejectTitle}
        label={h.rejectReason}
        confirmLabel={h.reject}
        onClose={() => setRejectTarget(null)}
        onSubmit={async (id, reason) => {
          await rejectHandover(id, reason);
          notify(h.rejectedMsg);
          setRejectTarget(null);
          load();
        }}
      />
      <ReasonModal
        target={cancelTarget}
        title={h.cancelTitle}
        label={h.cancelReason}
        confirmLabel={t.common.cancel}
        onClose={() => setCancelTarget(null)}
        onSubmit={async (id, reason) => {
          await cancelHandover(id, reason);
          notify(h.cancelledMsg);
          setCancelTarget(null);
          load();
        }}
      />
      <HandoverVoucherPrintModal voucher={voucher} onClose={() => setVoucher(null)} />
    </>
  );
}

/** Print-friendly handover voucher (reprintable GET). */
function HandoverVoucherPrintModal({
  voucher,
  onClose,
}: {
  voucher: HandoverVoucher | null;
  onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const h = t.shifts.ho;
  const p = t.shifts.print;
  if (!voucher) return null;
  const ho = voucher.handover;
  const meta = [
    { label: t.common.status, value: t.shifts.hoStatus[ho.status] },
    { label: h.fromShift, value: ho.from_shift_number || "—" },
    { label: h.toUser, value: ho.to_user_name || "—" },
    ...(ho.submitted_at
      ? [{ label: p.submittedAt, value: formatDateTime(ho.submitted_at, locale) }]
      : []),
    ...(ho.accepted_at
      ? [{ label: p.acceptedAt, value: formatDateTime(ho.accepted_at, locale) }]
      : []),
  ];
  return (
    <PrintModal open={voucher !== null} title={p.voucherTitle} onClose={onClose}>
      <PrintDocumentLayout
        hotelName={voucher.hotel.hotel_name}
        hotelAddress={voucher.hotel.address}
        hotelPhone={voucher.hotel.phone}
        docTitle={p.voucherTitle}
        docNumber={ho.handover_number}
        meta={meta}
        signatureLabel={t.finance.print.signature}
      >
        <dl className="print-grid">
          <div>
            <dt>{h.summaryNotes}</dt>
            <dd>{ho.summary_notes || "—"}</dd>
          </div>
          <div>
            <dt>{h.pendingTasks}</dt>
            <dd>{ho.pending_tasks_notes || "—"}</dd>
          </div>
          <div>
            <dt>{h.cashNotes}</dt>
            <dd>{ho.cash_notes || "—"}</dd>
          </div>
          <div>
            <dt>{h.guestNotes}</dt>
            <dd>{ho.guest_notes || "—"}</dd>
          </div>
          <div>
            <dt>{h.maintenanceNotes}</dt>
            <dd>{ho.maintenance_notes || "—"}</dd>
          </div>
          <div>
            <dt>{h.lostFoundNotes}</dt>
            <dd>{ho.lost_found_notes || "—"}</dd>
          </div>
        </dl>
      </PrintDocumentLayout>
    </PrintModal>
  );
}

function ReasonModal({
  target,
  title,
  label,
  confirmLabel,
  onClose,
  onSubmit,
}: {
  target: ShiftHandoverListItem | null;
  title: string;
  label: string;
  confirmLabel: string;
  onClose: () => void;
  onSubmit: (id: number, reason: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (target) {
      setReason("");
      setError(null);
    }
  }, [target]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!target) return;
    if (!reason.trim()) return setError(t.errors.validation);
    setBusy(true);
    setError(null);
    try {
      await onSubmit(target.id, reason.trim());
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={target !== null}
      onClose={onClose}
      title={title}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.close}
          </Button>
          <Button form="ho-reason-form" type="submit" variant="danger" loading={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <form id="ho-reason-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={label} htmlFor="ho-reason">
          <Input id="ho-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}

export function HandoverFormModal({
  open,
  presetShift,
  onClose,
  onSaved,
}: {
  open: boolean;
  presetShift?: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const h = t.shifts.ho;
  const [shifts, setShifts] = useState<ShiftListItem[]>([]);
  const [staff, setStaff] = useState<StaffMemberListItem[]>([]);
  const [form, setForm] = useState<HandoverBody>({ from_shift: 0, to_user: 0 });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ from_shift: presetShift ?? 0, to_user: 0 });
      setError(null);
      listShifts({ status: "open" })
        .then((res) => setShifts(res.results))
        .catch(() => setShifts([]));
      listStaff({ is_active: "true" })
        .then((res) => setStaff(res.results))
        .catch(() => setStaff([]));
    }
  }, [open, presetShift]);

  function set<K extends keyof HandoverBody>(k: K, v: HandoverBody[K]) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.from_shift || !form.to_user) return setError(t.errors.validation);
    setBusy(true);
    setError(null);
    try {
      await createHandover(form);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const shiftOptions = shifts.map((s) => ({
    value: String(s.id),
    label: `${s.shift_number} — ${s.responsible_name}`,
  }));
  const staffOptions = staff.map((s) => ({
    value: String(s.user_id),
    label: `${s.full_name} (${s.email})`,
  }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={h.create}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="ho-create-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="ho-create-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={h.fromShift} htmlFor="hoc-shift">
            <Select
              id="hoc-shift"
              value={form.from_shift ? String(form.from_shift) : ""}
              placeholder={h.fromShift}
              options={shiftOptions}
              onChange={(e) => set("from_shift", Number(e.target.value))}
            />
          </FormField>
          <FormField label={h.toUser} htmlFor="hoc-user">
            <Select
              id="hoc-user"
              value={form.to_user ? String(form.to_user) : ""}
              placeholder={h.toUser}
              options={staffOptions}
              onChange={(e) => set("to_user", Number(e.target.value))}
            />
          </FormField>
        </div>
        <FormField label={h.summaryNotes} htmlFor="hoc-summary">
          <Input
            id="hoc-summary"
            value={form.summary_notes ?? ""}
            onChange={(e) => set("summary_notes", e.target.value)}
          />
        </FormField>
        <FormField label={h.pendingTasks} htmlFor="hoc-tasks">
          <Input
            id="hoc-tasks"
            value={form.pending_tasks_notes ?? ""}
            onChange={(e) => set("pending_tasks_notes", e.target.value)}
          />
        </FormField>
        <div className="form-grid">
          <FormField label={h.cashNotes} htmlFor="hoc-cash">
            <Input
              id="hoc-cash"
              value={form.cash_notes ?? ""}
              onChange={(e) => set("cash_notes", e.target.value)}
            />
          </FormField>
          <FormField label={h.guestNotes} htmlFor="hoc-guest">
            <Input
              id="hoc-guest"
              value={form.guest_notes ?? ""}
              onChange={(e) => set("guest_notes", e.target.value)}
            />
          </FormField>
          <FormField label={h.maintenanceNotes} htmlFor="hoc-maint">
            <Input
              id="hoc-maint"
              value={form.maintenance_notes ?? ""}
              onChange={(e) => set("maintenance_notes", e.target.value)}
            />
          </FormField>
          <FormField label={h.lostFoundNotes} htmlFor="hoc-lf">
            <Input
              id="hoc-lf"
              value={form.lost_found_notes ?? ""}
              onChange={(e) => set("lost_found_notes", e.target.value)}
            />
          </FormField>
        </div>
      </form>
    </Modal>
  );
}
