"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ArrowDown,
  ArrowUp,
  KeyRound,
  Link2,
  Mail,
  Pencil,
  Plus,
  ShieldCheck,
  Trash2,
  Users,
} from "lucide-react";

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
  PasswordInput,
  SectionHeader,
  Select,
  Switch,
  useToast,
  type Column,
} from "@/components/ui";
import {
  changeStaffEmail,
  createStaffMember,
  deactivateStaffMember,
  deleteStaffMember,
  demoteStaffMember,
  linkExistingUser,
  listStaff,
  promoteStaffMember,
  reactivateStaffMember,
  resetStaffPassword,
  updateStaffMember,
  type LinkExistingBody,
  type StaffCreateBody,
  type StaffUpdateBody,
} from "@/lib/api/staff";
import { messageForError } from "@/lib/api/errors";
import type { StaffMemberListItem } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useCurrentUser } from "@/lib/session/CurrentUserContext";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

const PAGE_SIZE = 25;

/** Cosmetic permission gate (APIs still enforce). Null access = platform
 * console context, where these tabs never render — treat as permitted. */
function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

export function StaffListTab({
  onOpenPermissions,
}: {
  onOpenPermissions: (membershipId: number) => void;
}) {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const me = useCurrentUser();
  const s = t.staff.list;

  const [rows, setRows] = useState<StaffMemberListItem[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [isActive, setIsActive] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [editRow, setEditRow] = useState<StaffMemberListItem | null>(null);
  const [deactivateRow, setDeactivateRow] = useState<StaffMemberListItem | null>(null);
  const [reactivateRow, setReactivateRow] = useState<StaffMemberListItem | null>(null);
  const [resetRow, setResetRow] = useState<StaffMemberListItem | null>(null);
  const [promoteRow, setPromoteRow] = useState<StaffMemberListItem | null>(null);
  const [demoteRow, setDemoteRow] = useState<StaffMemberListItem | null>(null);
  const [emailRow, setEmailRow] = useState<StaffMemberListItem | null>(null);
  const [deleteRow, setDeleteRow] = useState<StaffMemberListItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listStaff({
        page,
        search: query || undefined,
        is_active: isActive || undefined,
      });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, query, isActive, t]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const statusOptions = [
    { value: "true", label: s.active },
    { value: "false", label: s.inactive },
  ];

  const columns: Column<StaffMemberListItem>[] = [
    { key: "full_name", header: s.name },
    { key: "email", header: s.email },
    { key: "job_title", header: s.jobTitle, render: (r) => r.job_title || "—" },
    {
      key: "membership_type",
      header: s.typeLabel,
      render: (r) => (
        <Badge tone={r.is_manager ? "primary" : "neutral"}>
          {r.is_manager ? s.manager : s.staffType}
        </Badge>
      ),
    },
    {
      key: "is_active",
      header: t.common.status,
      render: (r) => (
        <Badge tone={r.is_active ? "success" : "danger"}>
          {r.is_active ? s.active : s.inactive}
        </Badge>
      ),
    },
    {
      key: "permission_count",
      header: s.permissionCount,
      render: (r) => (r.is_manager ? "—" : r.permission_count),
    },
    {
      key: "created_at",
      header: t.common.createdAt,
      render: (r) => formatDate(r.created_at, locale),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => {
        const isSelf = me?.id === r.user_id;
        return (
          <div className="table__actions">
            <Button size="sm" variant="secondary" icon={Pencil} onClick={() => setEditRow(r)}>
              {s.edit}
            </Button>
            {!r.is_manager ? (
              <Button
                size="sm"
                variant="secondary"
                icon={ShieldCheck}
                onClick={() => onOpenPermissions(r.id)}
              >
                {s.permissions}
              </Button>
            ) : null}
            {!r.is_manager && !isSelf && can("staff.manage_managers") ? (
              <Button
                size="sm"
                variant="secondary"
                icon={ArrowUp}
                onClick={() => setPromoteRow(r)}
              >
                {s.promote}
              </Button>
            ) : null}
            {r.is_manager && !r.is_primary_manager && !isSelf && can("staff.manage_managers") ? (
              <Button
                size="sm"
                variant="secondary"
                icon={ArrowDown}
                onClick={() => setDemoteRow(r)}
              >
                {s.demote}
              </Button>
            ) : null}
            {!isSelf && can("staff.change_email") ? (
              <Button size="sm" variant="secondary" icon={Mail} onClick={() => setEmailRow(r)}>
                {s.changeEmail}
              </Button>
            ) : null}
            <Button size="sm" variant="secondary" icon={KeyRound} onClick={() => setResetRow(r)}>
              {s.resetPassword}
            </Button>
            {!r.is_primary_manager ? (
              r.is_active ? (
                <Button size="sm" variant="danger" onClick={() => setDeactivateRow(r)}>
                  {s.deactivate}
                </Button>
              ) : (
                <Button size="sm" onClick={() => setReactivateRow(r)}>
                  {s.reactivate}
                </Button>
              )
            ) : null}
            {!r.is_primary_manager && !isSelf && can("staff.delete") ? (
              <Button size="sm" variant="danger" icon={Trash2} onClick={() => setDeleteRow(r)}>
                {s.delete}
              </Button>
            ) : null}
          </div>
        );
      },
    },
  ];

  return (
    <>
      <Card>
        <SectionHeader
          title={s.title}
          actions={
            <>
              <Button variant="secondary" icon={Link2} onClick={() => setLinkOpen(true)}>
                {s.link}
              </Button>
              <Button icon={Plus} onClick={() => setCreateOpen(true)}>
                {s.add}
              </Button>
            </>
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
            <FormField label={t.common.search} htmlFor="st-search">
              <Input
                id="st-search"
                value={search}
                placeholder={s.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
              />
            </FormField>
            <FormField label={t.common.status} htmlFor="st-status">
              <Select
                id="st-status"
                value={isActive}
                placeholder={t.common.all}
                options={statusOptions}
                onChange={(e) => {
                  setPage(1);
                  setIsActive(e.target.value);
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
            <EmptyState title={s.empty} hint={s.emptyHint} icon={Users} />
          ) : (
            <>
              <DataTable caption={s.title} columns={columns} rows={rows} rowKey={(r) => r.id} />
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

      <CreateStaffModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSaved={(id) => {
          setCreateOpen(false);
          notify(s.createdMsg);
          load();
          onOpenPermissions(id);
        }}
      />
      <LinkUserModal
        open={linkOpen}
        onClose={() => setLinkOpen(false)}
        onSaved={(id) => {
          setLinkOpen(false);
          notify(s.linkedMsg);
          load();
          onOpenPermissions(id);
        }}
      />
      <EditStaffModal
        row={editRow}
        onClose={() => setEditRow(null)}
        onSaved={() => {
          setEditRow(null);
          notify(s.updatedMsg);
          load();
        }}
      />
      <DeactivateModal
        row={deactivateRow}
        onClose={() => setDeactivateRow(null)}
        onDone={() => {
          setDeactivateRow(null);
          notify(s.deactivatedMsg);
          load();
        }}
      />
      <ConfirmDialog
        open={reactivateRow !== null}
        title={s.reactivate}
        body={reactivateRow?.full_name ?? ""}
        confirmLabel={s.reactivate}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        onClose={() => setReactivateRow(null)}
        onConfirm={async () => {
          if (!reactivateRow) return;
          try {
            await reactivateStaffMember(reactivateRow.id);
            notify(s.reactivatedMsg);
            load();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setReactivateRow(null);
          }
        }}
      />
      <ResetPasswordModal
        row={resetRow}
        onClose={() => setResetRow(null)}
        onDone={() => {
          setResetRow(null);
          notify(s.resetDoneMsg);
        }}
      />
      <ConfirmDialog
        open={promoteRow !== null}
        title={s.promoteTitle}
        body={s.promoteConfirm.replace("{name}", promoteRow?.full_name ?? "")}
        confirmLabel={s.promote}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        onClose={() => setPromoteRow(null)}
        onConfirm={async () => {
          if (!promoteRow) return;
          try {
            await promoteStaffMember(promoteRow.id);
            notify(s.promotedMsg);
            load();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setPromoteRow(null);
          }
        }}
      />
      <ConfirmDialog
        open={demoteRow !== null}
        title={s.demoteTitle}
        body={s.demoteConfirm.replace("{name}", demoteRow?.full_name ?? "")}
        confirmLabel={s.demote}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        onClose={() => setDemoteRow(null)}
        onConfirm={async () => {
          if (!demoteRow) return;
          try {
            await demoteStaffMember(demoteRow.id);
            notify(s.demotedMsg);
            load();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setDemoteRow(null);
          }
        }}
      />
      <ChangeEmailModal
        row={emailRow}
        onClose={() => setEmailRow(null)}
        onDone={() => {
          setEmailRow(null);
          notify(s.emailChangedMsg);
          load();
        }}
      />
      <DeleteModal
        row={deleteRow}
        onClose={() => setDeleteRow(null)}
        onDone={(msg) => {
          setDeleteRow(null);
          notify(msg);
          load();
        }}
      />
    </>
  );
}

function CreateStaffModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: (membershipId: number) => void;
}) {
  const { t } = useI18n();
  const f = t.staff.form;
  const [form, setForm] = useState<StaffCreateBody>({
    full_name: "",
    email: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({
        full_name: "",
        email: "",
        password: "",
        phone: "",
        job_title: "",
        staff_code: "",
        notes: "",
      });
      setError(null);
    }
  }, [open]);

  function set<K extends keyof StaffCreateBody>(k: K, v: StaffCreateBody[K]) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.full_name.trim()) return setError(f.nameRequired);
    if (!form.email.trim()) return setError(f.emailRequired);
    if ((form.password ?? "").length < 8) return setError(f.passwordRequired);
    setBusy(true);
    setError(null);
    try {
      const created = await createStaffMember(form);
      onSaved(created.id);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={f.createTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-create-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="staff-create-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={f.fullName} htmlFor="sc-name">
            <Input id="sc-name" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} />
          </FormField>
          <FormField label={f.email} htmlFor="sc-email">
            <Input id="sc-email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
          </FormField>
          <FormField label={f.phone} htmlFor="sc-phone">
            <Input id="sc-phone" value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} />
          </FormField>
          <FormField label={f.tempPassword} htmlFor="sc-pass" hint={f.tempPasswordHint}>
            <PasswordInput
              id="sc-pass"
              value={form.password}
              showLabel={t.auth.showPassword}
              hideLabel={t.auth.hidePassword}
              onChange={(e) => set("password", e.target.value)}
            />
          </FormField>
          <FormField label={f.jobTitle} htmlFor="sc-title" hint={f.jobTitleHint}>
            <Input id="sc-title" value={form.job_title ?? ""} onChange={(e) => set("job_title", e.target.value)} />
          </FormField>
          <FormField label={f.staffCode} htmlFor="sc-code">
            <Input id="sc-code" value={form.staff_code ?? ""} onChange={(e) => set("staff_code", e.target.value)} />
          </FormField>
        </div>
        <FormField label={f.notes} htmlFor="sc-notes">
          <Input id="sc-notes" value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} />
        </FormField>
        <p className="muted small">{f.initialPermissionsHint}</p>
      </form>
    </Modal>
  );
}

function LinkUserModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: (membershipId: number) => void;
}) {
  const { t } = useI18n();
  const f = t.staff.form;
  const [form, setForm] = useState<LinkExistingBody>({ email: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ email: "", job_title: "", staff_code: "", notes: "" });
      setError(null);
    }
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.email.trim()) return setError(f.emailRequired);
    setBusy(true);
    setError(null);
    try {
      const linked = await linkExistingUser(form);
      onSaved(linked.id);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={f.linkTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-link-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="staff-link-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={f.email} htmlFor="sl-email">
          <Input
            id="sl-email"
            type="email"
            value={form.email}
            onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
          />
        </FormField>
        <div className="form-grid">
          <FormField label={f.jobTitle} htmlFor="sl-title" hint={f.jobTitleHint}>
            <Input
              id="sl-title"
              value={form.job_title ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, job_title: e.target.value }))}
            />
          </FormField>
          <FormField label={f.staffCode} htmlFor="sl-code">
            <Input
              id="sl-code"
              value={form.staff_code ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, staff_code: e.target.value }))}
            />
          </FormField>
        </div>
      </form>
    </Modal>
  );
}

function EditStaffModal({
  row,
  onClose,
  onSaved,
}: {
  row: StaffMemberListItem | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const f = t.staff.form;
  const [form, setForm] = useState<StaffUpdateBody>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (row) {
      setForm({
        full_name: row.full_name,
        phone: row.phone,
        job_title: row.job_title,
        staff_code: row.staff_code,
      });
      setError(null);
    }
  }, [row]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!row) return;
    if (!form.full_name?.trim()) return setError(f.nameRequired);
    setBusy(true);
    setError(null);
    try {
      await updateStaffMember(row.id, form);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={row !== null}
      onClose={onClose}
      title={f.editTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-edit-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="staff-edit-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={f.fullName} htmlFor="se-name">
            <Input
              id="se-name"
              value={form.full_name ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, full_name: e.target.value }))}
            />
          </FormField>
          <FormField label={f.phone} htmlFor="se-phone">
            <Input
              id="se-phone"
              value={form.phone ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, phone: e.target.value }))}
            />
          </FormField>
          <FormField label={f.jobTitle} htmlFor="se-title" hint={f.jobTitleHint}>
            <Input
              id="se-title"
              value={form.job_title ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, job_title: e.target.value }))}
            />
          </FormField>
          <FormField label={f.staffCode} htmlFor="se-code">
            <Input
              id="se-code"
              value={form.staff_code ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, staff_code: e.target.value }))}
            />
          </FormField>
        </div>
        <FormField label={f.notes} htmlFor="se-notes">
          <Input
            id="se-notes"
            value={form.notes ?? ""}
            onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function DeactivateModal({
  row,
  onClose,
  onDone,
}: {
  row: StaffMemberListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const s = t.staff.list;
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (row) {
      setReason("");
      setError(null);
    }
  }, [row]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!row) return;
    setBusy(true);
    setError(null);
    try {
      await deactivateStaffMember(row.id, reason.trim());
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={row !== null}
      onClose={onClose}
      title={s.deactivateTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-deactivate-form" type="submit" variant="danger" loading={busy}>
            {s.deactivate}
          </Button>
        </>
      }
    >
      <form id="staff-deactivate-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="warning">{s.deactivateWarning}</Alert>
        <FormField label={s.deactivateReason} htmlFor="sd-reason">
          <Input id="sd-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}

function ResetPasswordModal({
  row,
  onClose,
  onDone,
}: {
  row: StaffMemberListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const s = t.staff.list;
  const f = t.staff.form;
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (row) {
      setPassword("");
      setError(null);
    }
  }, [row]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!row) return;
    if (password.length < 8) return setError(f.passwordRequired);
    setBusy(true);
    setError(null);
    try {
      await resetStaffPassword(row.id, password);
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={row !== null}
      onClose={onClose}
      title={s.resetTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-reset-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="staff-reset-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="warning">{s.resetHint}</Alert>
        <FormField label={s.newPassword} htmlFor="sr-pass">
          <PasswordInput
            id="sr-pass"
            value={password}
            showLabel={t.auth.showPassword}
            hideLabel={t.auth.hidePassword}
            onChange={(e) => setPassword(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function ChangeEmailModal({
  row,
  onClose,
  onDone,
}: {
  row: StaffMemberListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const s = t.staff.list;
  const f = t.staff.form;
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (row) {
      setEmail(row.email);
      setError(null);
    }
  }, [row]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!row) return;
    if (!email.trim()) return setError(f.emailRequired);
    setBusy(true);
    setError(null);
    try {
      await changeStaffEmail(row.id, email.trim());
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={row !== null}
      onClose={onClose}
      title={s.changeEmailTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-email-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="staff-email-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={s.changeEmailLabel} htmlFor="sce-email">
          <Input
            id="sce-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function DeleteModal({
  row,
  onClose,
  onDone,
}: {
  row: StaffMemberListItem | null;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const { t } = useI18n();
  const s = t.staff.list;
  const [deleteUser, setDeleteUser] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (row) {
      setDeleteUser(false);
      setError(null);
    }
  }, [row]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!row) return;
    setBusy(true);
    setError(null);
    try {
      const result = await deleteStaffMember(row.id, deleteUser);
      onDone(result.user_deleted !== null ? s.deletedWithUserMsg : s.deletedMsg);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={row !== null}
      onClose={onClose}
      title={s.deleteTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-delete-form" type="submit" variant="danger" loading={busy}>
            {s.deleteConfirm}
          </Button>
        </>
      }
    >
      <form id="staff-delete-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="warning">{s.deleteWarning}</Alert>
        <Switch
          id="sd-delete-user"
          checked={deleteUser}
          onChange={setDeleteUser}
          label={s.deleteUserLabel}
        />
      </form>
    </Modal>
  );
}
