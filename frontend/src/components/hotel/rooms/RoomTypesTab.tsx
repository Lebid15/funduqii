"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Package, Pencil, Plus, Power, Trash2, X } from "lucide-react";

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

/** The curated amenity catalog (owner spec) — stored as stable keys in the
 * EXISTING RoomType.amenities JSON field, displayed via i18n. */
export const AMENITY_KEYS = [
  "ac",
  "wifi",
  "tv",
  "private_bathroom",
  "fridge",
  "balcony",
  "view",
  "minibar",
  "safe",
  "desk",
  "heating",
  "kettle",
  "hair_dryer",
  "room_service",
  "single_bed",
  "double_bed",
  "twin_beds",
  "jacuzzi",
  "kitchenette",
  "soundproof",
  "no_smoking",
  "smoking",
  "family_friendly",
  "accessible",
] as const;

/** Auto-generate the next free short code — the backend requires a unique
 * per-hotel code but the owner wants it OFF the form. */
function nextCode(types: RoomType[]): string {
  const taken = new Set(types.map((ty) => ty.code.toUpperCase()));
  let n = types.length + 1;
  while (taken.has(`T${n}`)) n += 1;
  return `T${n}`;
}

/**
 * Room types tab (owner UX round): add button + list with edit /
 * enable-disable / safe delete (only unused types — the backend refuses
 * deleting used ones anyway). The form is the SIMPLIFIED one: name, ONE
 * capacity, price per night, amenity multi-select, description, active,
 * and show-on-public-site defaulting to ON. Code / bed type / public
 * name-price-description are hidden and preserved server-side.
 */
export function RoomTypesTab({ embedded = false }: { embedded?: boolean } = {}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  const { notify } = useToast();
  const [rows, setRows] = useState<RoomType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<RoomType | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<RoomType | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [rowBusy, setRowBusy] = useState<number | null>(null);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t is stable per locale
  }, []);

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
      // The backend blocks deleting a used type — say it plainly.
      notify(`${b.typeInUseMessage} — ${messageForError(err, t)}`, "error");
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  async function toggleActive(target: RoomType) {
    setRowBusy(target.id);
    try {
      await updateRoomType(target.id, { is_active: !target.is_active });
      notify(t.rooms.saved);
      load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setRowBusy(null);
    }
  }

  const columns: Column<RoomType>[] = [
    { key: "name", header: b.roomTypeName },
    {
      key: "capacity",
      header: b.capacity,
      render: (row) => String(row.base_capacity),
    },
    {
      key: "base_rate",
      header: b.pricePerNight,
      render: (row) => row.base_rate ?? "—",
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
          <Button
            variant="ghost"
            size="sm"
            icon={Power}
            disabled={rowBusy === row.id}
            onClick={() => toggleActive(row)}
          >
            {row.is_active ? b.disableType : b.enableType}
          </Button>
          {row.room_count === 0 ? (
            <Button variant="danger" size="sm" icon={Trash2} onClick={() => setDeleteTarget(row)}>
              {t.common.delete}
            </Button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <>
      {embedded ? (
        <div className="cluster cluster--end">
          <Button icon={Plus} onClick={() => setCreating(true)}>{b.addRoomType}</Button>
        </div>
      ) : (
        <SectionHeader
          title={t.rooms.tabs.types}
          icon={Package}
          actions={<Button icon={Plus} onClick={() => setCreating(true)}>{b.addRoomType}</Button>}
        />
      )}

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
            action={<Button icon={Plus} onClick={() => setCreating(true)}>{b.addRoomType}</Button>}
          />
        ) : (
          <DataTable caption={t.rooms.tabs.types} columns={columns} rows={rows} rowKey={(r) => r.id} />
        )
      ) : null}

      <RoomTypeModal
        open={creating}
        types={rows}
        onClose={() => setCreating(false)}
        onSaved={() => { setCreating(false); notify(t.rooms.saved); load(); }}
      />
      <RoomTypeModal
        open={editing !== null}
        roomType={editing ?? undefined}
        types={rows}
        onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); notify(t.rooms.saved); load(); }}
      />
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
  types,
  onClose,
  onSaved,
}: {
  open: boolean;
  roomType?: RoomType;
  types: RoomType[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  const amenityLabels = b.amenity as Record<string, string>;
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState("2");
  const [rate, setRate] = useState("");
  const [amenities, setAmenities] = useState<string[]>([]);
  const [description, setDescription] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [publicVisible, setPublicVisible] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(roomType?.name ?? "");
    setCapacity(String(roomType?.base_capacity ?? 2));
    setRate(roomType?.base_rate ?? "");
    setAmenities(roomType?.amenities ?? []);
    setDescription(roomType?.description ?? "");
    setIsActive(roomType?.is_active ?? true);
    // Owner default: new types are publicly visible unless switched off.
    setPublicVisible(roomType ? roomType.public_is_visible : true);
    setError(null);
  }, [open, roomType]);

  function addAmenity(key: string) {
    if (!key || amenities.includes(key)) return;
    setAmenities((prev) => [...prev, key]);
  }
  function removeAmenity(key: string) {
    setAmenities((prev) => prev.filter((a) => a !== key));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError(t.errors.validation);
      return;
    }
    const cap = Math.max(1, Number(capacity) || 1);
    const body: RoomTypeWriteBody = {
      name: name.trim(),
      // ONE capacity field (owner spec) — base and max stay in sync.
      base_capacity: cap,
      max_capacity: cap,
      base_rate: rate.trim() ? rate.trim() : null,
      amenities,
      description: description.trim(),
      is_active: isActive,
      public_is_visible: publicVisible,
    };
    // The backend requires a unique code — generated silently on create,
    // untouched on edit (owner: no code field on the form).
    if (!roomType) body.code = nextCode(types);
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

  const available = AMENITY_KEYS.filter((key) => !amenities.includes(key));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={roomType ? b.editRoomType : b.addRoomType}
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
          <FormField label={b.roomTypeName} htmlFor="type-name">
            <Input
              id="type-name"
              value={name}
              placeholder={b.typeNamePlaceholder}
              required
              onChange={(e) => setName(e.target.value)}
            />
          </FormField>
          <FormField label={b.capacity} htmlFor="type-capacity">
            <Input
              id="type-capacity"
              type="number"
              min="1"
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
            />
          </FormField>
          <FormField label={b.pricePerNight} htmlFor="type-rate">
            <Input
              id="type-rate"
              type="number"
              min="0"
              step="0.01"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
            />
          </FormField>
          <FormField label={b.amenitiesLabel} htmlFor="type-amenity-picker">
            <Select
              id="type-amenity-picker"
              value=""
              placeholder={b.selectAmenity}
              options={available.map((key) => ({
                value: key,
                label: amenityLabels[key] ?? key,
              }))}
              onChange={(e) => addAmenity(e.target.value)}
            />
          </FormField>
        </div>
        {amenities.length > 0 ? (
          <div className="cluster">
            {amenities.map((key) => (
              <span key={key} className="chip chip--removable">
                {amenityLabels[key] ?? key}
                <button
                  type="button"
                  className="chip__remove"
                  aria-label={`${t.common.delete} ${amenityLabels[key] ?? key}`}
                  onClick={() => removeAmenity(key)}
                >
                  <X size={12} />
                </button>
              </span>
            ))}
          </div>
        ) : null}
        <FormField label={b.typeDescription} htmlFor="type-desc">
          <Textarea
            id="type-desc"
            value={description}
            rows={2}
            onChange={(e) => setDescription(e.target.value)}
          />
        </FormField>
        <Switch id="type-active" label={b.typeActive} checked={isActive} onChange={setIsActive} />
        <Switch
          id="type-public"
          label={b.showOnPublicSite}
          checked={publicVisible}
          onChange={setPublicVisible}
        />
      </form>
    </Modal>
  );
}
