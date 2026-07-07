"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Pencil, Plus, Trash2, Users } from "lucide-react";

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
  Select,
  Switch,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import {
  createGuest,
  deleteGuest,
  listGuests,
  updateGuest,
  type GuestWriteBody,
} from "@/lib/api/guests";
import { messageForError } from "@/lib/api/errors";
import type { Guest } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

const PAGE_SIZE = 25;

export function GuestsPanel() {
  const { t } = useI18n();
  const { notify } = useToast();
  const [rows, setRows] = useState<Guest[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Guest | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Guest | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listGuests({
        page,
        search: query || undefined,
        is_active: showInactive ? undefined : "true",
      });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, query, showInactive, t]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  function applySearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setQuery(search);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await deleteGuest(deleteTarget.id);
      notify(t.guests.saved);
      setDeleteTarget(null);
      load();
    } catch (err) {
      notify(messageForError(err, t), "error");
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  const columns: Column<Guest>[] = [
    { key: "full_name", header: t.guests.list.name },
    { key: "phone", header: t.guests.list.phone, render: (r) => r.phone || "—" },
    {
      key: "document",
      header: t.guests.list.document,
      render: (r) => (r.document_number ? `${r.document_number}` : "—"),
    },
    { key: "nationality", header: t.guests.list.nationality, render: (r) => r.nationality || "—" },
    {
      key: "is_active",
      header: t.common.status,
      render: (r) => (
        <Badge tone={r.is_active ? "success" : "neutral"}>
          {r.is_active ? t.guests.active : t.guests.inactive}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => (
        <div className="table__actions">
          <Button variant="secondary" size="sm" icon={Pencil} onClick={() => setEditing(r)}>
            {t.common.edit}
          </Button>
          <Button variant="danger" size="sm" icon={Trash2} onClick={() => setDeleteTarget(r)}>
            {t.common.delete}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <Card>
        <form onSubmit={applySearch}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="guest-search">
              <Input id="guest-search" value={search} placeholder={t.guests.list.searchPlaceholder} onChange={(e) => setSearch(e.target.value)} />
            </FormField>
            <div className="filter-bar__actions cluster">
              <Switch id="guest-inactive" label={t.guests.list.showInactive} checked={showInactive} onChange={(v) => { setPage(1); setShowInactive(v); }} />
              <Button icon={Plus} onClick={() => setCreating(true)}>{t.guests.list.add}</Button>
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
            title={t.guests.list.empty}
            hint={t.guests.list.emptyHint}
            icon={Users}
            action={<Button icon={Plus} onClick={() => setCreating(true)}>{t.guests.list.add}</Button>}
          />
        ) : (
          <>
            <DataTable caption={t.guests.title} columns={columns} rows={rows} rowKey={(r) => r.id} />
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

      <GuestModal open={creating} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); notify(t.guests.saved); setPage(1); load(); }} />
      <GuestModal open={editing !== null} guest={editing ?? undefined} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); notify(t.guests.saved); load(); }} />
      <ConfirmDialog
        open={deleteTarget !== null}
        title={t.guests.deleteTitle}
        body={t.guests.deleteBody}
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

function GuestModal({
  open,
  guest,
  onClose,
  onSaved,
}: {
  open: boolean;
  guest?: Guest;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState<GuestWriteBody>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm({
      full_name: guest?.full_name ?? "",
      phone: guest?.phone ?? "",
      email: guest?.email ?? "",
      nationality: guest?.nationality ?? "",
      document_type: guest?.document_type ?? "",
      document_number: guest?.document_number ?? "",
      date_of_birth: guest?.date_of_birth ?? null,
      gender: guest?.gender ?? "",
      address: guest?.address ?? "",
      notes: guest?.notes ?? "",
      is_active: guest?.is_active ?? true,
    });
    setError(null);
  }, [open, guest]);

  function set<K extends keyof GuestWriteBody>(key: K, value: GuestWriteBody[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!form.full_name?.trim()) return setError(t.guests.form.nameRequired);
    const body: GuestWriteBody = {
      ...form,
      full_name: form.full_name.trim(),
      date_of_birth: form.date_of_birth || null,
    };
    setBusy(true);
    try {
      if (guest) await updateGuest(guest.id, body);
      else await createGuest(body);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const docOptions = (["", "national_id", "passport", "driving_license", "other"] as const).map((v) => ({
    value: v,
    label: v === "" ? t.guests.documentTypes.none : t.guests.documentTypes[v],
  }));
  const genderOptions = (["", "male", "female", "other", "unspecified"] as const).map((v) => ({
    value: v,
    label: v === "" ? t.guests.genders.none : t.guests.genders[v],
  }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={guest ? t.guests.form.editTitle : t.guests.form.createTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="guest-form" type="submit" loading={busy}>{t.common.save}</Button>
        </>
      }
    >
      <form id="guest-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.guests.form.fullName} htmlFor="g-name">
            <Input id="g-name" value={form.full_name ?? ""} required onChange={(e) => set("full_name", e.target.value)} />
          </FormField>
          <FormField label={t.guests.form.phone} htmlFor="g-phone">
            <Input id="g-phone" value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} />
          </FormField>
          <FormField label={t.guests.form.email} htmlFor="g-email">
            <Input id="g-email" type="email" value={form.email ?? ""} onChange={(e) => set("email", e.target.value)} />
          </FormField>
          <FormField label={t.guests.form.nationality} htmlFor="g-nat">
            <Input id="g-nat" value={form.nationality ?? ""} onChange={(e) => set("nationality", e.target.value)} />
          </FormField>
          <FormField label={t.guests.form.documentType} htmlFor="g-doctype">
            <Select id="g-doctype" value={form.document_type ?? ""} options={docOptions} onChange={(e) => set("document_type", e.target.value as GuestWriteBody["document_type"])} />
          </FormField>
          <FormField label={t.guests.form.documentNumber} htmlFor="g-docnum">
            <Input id="g-docnum" value={form.document_number ?? ""} onChange={(e) => set("document_number", e.target.value)} />
          </FormField>
          <FormField label={t.guests.form.dateOfBirth} htmlFor="g-dob">
            <Input id="g-dob" type="date" value={form.date_of_birth ?? ""} onChange={(e) => set("date_of_birth", e.target.value || null)} />
          </FormField>
          <FormField label={t.guests.form.gender} htmlFor="g-gender">
            <Select id="g-gender" value={form.gender ?? ""} options={genderOptions} onChange={(e) => set("gender", e.target.value as GuestWriteBody["gender"])} />
          </FormField>
        </div>
        <FormField label={t.guests.form.address} htmlFor="g-addr">
          <Input id="g-addr" value={form.address ?? ""} onChange={(e) => set("address", e.target.value)} />
        </FormField>
        <FormField label={t.guests.form.notes} htmlFor="g-notes">
          <Textarea id="g-notes" value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} />
        </FormField>
        <Switch id="g-active" label={t.guests.form.active} checked={form.is_active ?? true} onChange={(v) => set("is_active", v)} />
      </form>
    </Modal>
  );
}
