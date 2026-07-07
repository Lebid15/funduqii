"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Building2, Pencil, Plus, Trash2 } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  SectionHeader,
  Switch,
  useToast,
  type Column,
} from "@/components/ui";
import {
  createFloor,
  deleteFloor,
  listFloors,
  updateFloor,
  type FloorWriteBody,
} from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type { Floor } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

export function FloorsTab() {
  const { t } = useI18n();
  const { notify } = useToast();
  const [rows, setRows] = useState<Floor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Floor | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Floor | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows((await listFloors()).results);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await deleteFloor(deleteTarget.id);
      notify(t.rooms.saved);
      setDeleteTarget(null);
      load();
    } catch (err) {
      notify(messageForError(err, t), "error");
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  const columns: Column<Floor>[] = [
    { key: "name", header: t.rooms.floors.name },
    { key: "number", header: t.rooms.floors.number },
    { key: "room_count", header: t.rooms.floors.roomCount },
    {
      key: "is_active",
      header: t.common.status,
      render: (row) => (
        <Badge tone={row.is_active ? "success" : "neutral"}>
          {row.is_active ? t.plans.active : t.plans.inactive}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (row) => (
        <div className="table__actions">
          <Button variant="secondary" size="sm" icon={Pencil} onClick={() => setEditing(row)}>
            {t.common.edit}
          </Button>
          <Button variant="danger" size="sm" icon={Trash2} onClick={() => setDeleteTarget(row)}>
            {t.common.delete}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <SectionHeader
        title={t.rooms.tabs.floors}
        icon={Building2}
        actions={
          <Button icon={Plus} onClick={() => setCreating(true)}>
            {t.rooms.floors.add}
          </Button>
        }
      />

      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? (
        <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} />
      ) : null}
      {!loading && !error ? (
        rows.length === 0 ? (
          <EmptyState
            title={t.rooms.floors.empty}
            hint={t.rooms.floors.emptyHint}
            icon={Building2}
            action={<Button icon={Plus} onClick={() => setCreating(true)}>{t.rooms.floors.add}</Button>}
          />
        ) : (
          <DataTable caption={t.rooms.tabs.floors} columns={columns} rows={rows} rowKey={(r) => r.id} />
        )
      ) : null}

      <FloorModal
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={() => {
          setCreating(false);
          notify(t.rooms.saved);
          load();
        }}
      />
      <FloorModal
        open={editing !== null}
        floor={editing ?? undefined}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          notify(t.rooms.saved);
          load();
        }}
      />
      <ConfirmDialog
        open={deleteTarget !== null}
        title={t.rooms.floors.deleteTitle}
        body={t.rooms.floors.deleteBody}
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

function FloorModal({
  open,
  floor,
  onClose,
  onSaved,
}: {
  open: boolean;
  floor?: Floor;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [number, setNumber] = useState("");
  const [description, setDescription] = useState("");
  const [sortOrder, setSortOrder] = useState("0");
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(floor?.name ?? "");
    setNumber(floor?.number ?? "");
    setDescription(floor?.description ?? "");
    setSortOrder(String(floor?.sort_order ?? 0));
    setIsActive(floor?.is_active ?? true);
    setError(null);
  }, [open, floor]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!name.trim()) return setError(t.rooms.floors.nameRequired);
    const body: FloorWriteBody = {
      name: name.trim(),
      number: number.trim(),
      description: description.trim(),
      sort_order: Number(sortOrder) || 0,
      is_active: isActive,
    };
    setBusy(true);
    try {
      if (floor) await updateFloor(floor.id, body);
      else await createFloor(body);
      onSaved();
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
      title={floor ? t.rooms.floors.editTitle : t.rooms.floors.createTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="floor-form" type="submit" loading={busy}>{t.common.save}</Button>
        </>
      }
    >
      <form id="floor-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.rooms.floors.name} htmlFor="floor-name">
            <Input id="floor-name" value={name} required onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField label={t.rooms.floors.number} htmlFor="floor-number">
            <Input id="floor-number" value={number} onChange={(e) => setNumber(e.target.value)} />
          </FormField>
          <FormField label={t.rooms.floors.sortOrder} htmlFor="floor-order">
            <Input id="floor-order" type="number" min="0" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} />
          </FormField>
        </div>
        <FormField label={t.rooms.floors.description} htmlFor="floor-desc">
          <Input id="floor-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
        </FormField>
        <Switch id="floor-active" label={t.rooms.floors.active} checked={isActive} onChange={setIsActive} />
      </form>
    </Modal>
  );
}
