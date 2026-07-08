"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Package, Pencil, Plus, Trash2 } from "lucide-react";

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
  Select,
  Switch,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import {
  createRoomType,
  deleteRoomType,
  listRoomTypes,
  updateRoomType,
  type RoomTypeWriteBody,
} from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type { RoomType } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

export function RoomTypesTab() {
  const { t } = useI18n();
  const { notify } = useToast();
  const [rows, setRows] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<RoomType | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<RoomType | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows((await listRoomTypes()).results);
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
      await deleteRoomType(deleteTarget.id);
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

  const columns: Column<RoomType>[] = [
    { key: "name", header: t.rooms.types.name },
    { key: "code", header: t.rooms.types.code },
    {
      key: "capacity",
      header: t.rooms.list.capacity,
      render: (row) => `${row.base_capacity}–${row.max_capacity}`,
    },
    { key: "room_count", header: t.rooms.types.roomCount },
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
        title={t.rooms.tabs.types}
        icon={Package}
        actions={<Button icon={Plus} onClick={() => setCreating(true)}>{t.rooms.types.add}</Button>}
      />

      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? (
        <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} />
      ) : null}
      {!loading && !error ? (
        rows.length === 0 ? (
          <EmptyState
            title={t.rooms.types.empty}
            hint={t.rooms.types.emptyHint}
            icon={Package}
            action={<Button icon={Plus} onClick={() => setCreating(true)}>{t.rooms.types.add}</Button>}
          />
        ) : (
          <DataTable caption={t.rooms.tabs.types} columns={columns} rows={rows} rowKey={(r) => r.id} />
        )
      ) : null}

      <RoomTypeModal open={creating} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); notify(t.rooms.saved); load(); }} />
      <RoomTypeModal open={editing !== null} roomType={editing ?? undefined} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); notify(t.rooms.saved); load(); }} />
      <ConfirmDialog
        open={deleteTarget !== null}
        title={t.rooms.types.deleteTitle}
        body={t.rooms.types.deleteBody}
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

function RoomTypeModal({
  open,
  roomType,
  onClose,
  onSaved,
}: {
  open: boolean;
  roomType?: RoomType;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [baseCapacity, setBaseCapacity] = useState("1");
  const [maxCapacity, setMaxCapacity] = useState("1");
  const [bedType, setBedType] = useState("");
  const [amenities, setAmenities] = useState("");
  const [baseRate, setBaseRate] = useState("");
  const [description, setDescription] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [publicVisible, setPublicVisible] = useState(false);
  const [publicName, setPublicName] = useState("");
  const [publicDescription, setPublicDescription] = useState("");
  const [publicBasePrice, setPublicBasePrice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(roomType?.name ?? "");
    setCode(roomType?.code ?? "");
    setBaseCapacity(String(roomType?.base_capacity ?? 1));
    setMaxCapacity(String(roomType?.max_capacity ?? 1));
    setBedType(roomType?.bed_type ?? "");
    setAmenities((roomType?.amenities ?? []).join(", "));
    setBaseRate(roomType?.base_rate ?? "");
    setDescription(roomType?.description ?? "");
    setIsActive(roomType?.is_active ?? true);
    setPublicVisible(roomType?.public_is_visible ?? false);
    setPublicName(roomType?.public_name ?? "");
    setPublicDescription(roomType?.public_description ?? "");
    setPublicBasePrice(roomType?.public_base_price ?? "");
    setError(null);
  }, [open, roomType]);

  const bedOptions = [
    { value: "", label: t.rooms.bedTypes.none },
    { value: "single", label: t.rooms.bedTypes.single },
    { value: "double", label: t.rooms.bedTypes.double },
    { value: "twin", label: t.rooms.bedTypes.twin },
    { value: "king", label: t.rooms.bedTypes.king },
    { value: "queen", label: t.rooms.bedTypes.queen },
    { value: "suite", label: t.rooms.bedTypes.suite },
  ];

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const body: RoomTypeWriteBody = {
      name: name.trim(),
      code: code.trim(),
      base_capacity: Number(baseCapacity) || 1,
      max_capacity: Number(maxCapacity) || 1,
      bed_type: bedType,
      amenities: amenities.split(",").map((a) => a.trim()).filter(Boolean),
      base_rate: baseRate === "" ? null : baseRate,
      description: description.trim(),
      is_active: isActive,
      public_is_visible: publicVisible,
      public_name: publicName.trim(),
      public_description: publicDescription.trim(),
      public_base_price: publicBasePrice === "" ? null : publicBasePrice,
    };
    setBusy(true);
    try {
      if (roomType) await updateRoomType(roomType.id, body);
      else await createRoomType(body);
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
      title={roomType ? t.rooms.types.editTitle : t.rooms.types.createTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="type-form" type="submit" loading={busy}>{t.common.save}</Button>
        </>
      }
    >
      <form id="type-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.rooms.types.name} htmlFor="type-name">
            <Input id="type-name" value={name} required onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField label={t.rooms.types.code} htmlFor="type-code">
            <Input id="type-code" value={code} required onChange={(e) => setCode(e.target.value.toUpperCase())} />
          </FormField>
          <FormField label={t.rooms.types.baseCapacity} htmlFor="type-base">
            <Input id="type-base" type="number" min="1" value={baseCapacity} onChange={(e) => setBaseCapacity(e.target.value)} />
          </FormField>
          <FormField label={t.rooms.types.maxCapacity} htmlFor="type-max">
            <Input id="type-max" type="number" min="1" value={maxCapacity} onChange={(e) => setMaxCapacity(e.target.value)} />
          </FormField>
          <FormField label={t.rooms.types.bedType} htmlFor="type-bed">
            <Select id="type-bed" value={bedType} options={bedOptions} onChange={(e) => setBedType(e.target.value)} />
          </FormField>
          <FormField label={t.rooms.types.baseRate} htmlFor="type-rate" hint={t.rooms.types.baseRateHint}>
            <Input id="type-rate" type="number" min="0" step="0.01" value={baseRate} onChange={(e) => setBaseRate(e.target.value)} />
          </FormField>
        </div>
        <FormField label={t.rooms.types.amenities} htmlFor="type-amenities" hint={t.rooms.types.amenitiesHint}>
          <Input id="type-amenities" value={amenities} onChange={(e) => setAmenities(e.target.value)} />
        </FormField>
        <FormField label={t.rooms.types.description} htmlFor="type-desc">
          <Textarea id="type-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
        </FormField>
        <Switch id="type-active" label={t.rooms.types.active} checked={isActive} onChange={setIsActive} />

        {/* Phase 15 — what the public website shows for this type. */}
        <Switch
          id="type-public-visible"
          label={t.rooms.types.publicVisible}
          checked={publicVisible}
          onChange={setPublicVisible}
        />
        {publicVisible ? (
          <>
            <div className="form-grid">
              <FormField label={t.rooms.types.publicName} htmlFor="type-public-name" hint={t.rooms.types.publicNameHint}>
                <Input id="type-public-name" value={publicName} onChange={(e) => setPublicName(e.target.value)} />
              </FormField>
              <FormField label={t.rooms.types.publicPrice} htmlFor="type-public-price" hint={t.rooms.types.publicPriceHint}>
                <Input id="type-public-price" type="number" min="0" step="0.01" value={publicBasePrice} onChange={(e) => setPublicBasePrice(e.target.value)} />
              </FormField>
            </div>
            <FormField label={t.rooms.types.publicDescription} htmlFor="type-public-desc">
              <Textarea id="type-public-desc" value={publicDescription} onChange={(e) => setPublicDescription(e.target.value)} />
            </FormField>
          </>
        ) : null}
      </form>
    </Modal>
  );
}
