"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Package, Pencil, Plus, Power, Trash2, X } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  ConfirmDialog,
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
import { formatCapacity, formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { AmenityChips } from "./AmenityChips";

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

/** Mutually-exclusive amenity pairs (owner spec): a room type cannot be both
 * smoking and non-smoking. Selecting one auto-deselects the other and hides it
 * from the picker; a leftover conflict (e.g. legacy data) is flagged inline. */
const AMENITY_CONFLICTS: Record<string, string> = {
  smoking: "no_smoking",
  no_smoking: "smoking",
};

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
export function RoomTypesTab({
  embedded = false,
  currency = "",
}: { embedded?: boolean; currency?: string } = {}) {
  const { t, locale } = useI18n();
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

  const addButton = (
    <Button icon={Plus} onClick={() => setCreating(true)}>
      {b.addRoomType}
    </Button>
  );

  function renderCard(row: RoomType) {
    return (
      <div
        key={row.id}
        role="listitem"
        className={`rt-card${row.is_active ? "" : " rt-card--inactive"}`}
      >
        <div className="rt-card__main">
          <span className="rt-card__name">{row.name}</span>
          {row.description ? (
            <span className="rt-card__desc">{row.description}</span>
          ) : null}
          {/* Full amenity list: the wide (xl) management modal has no per-item
           * drawer, so a "+N" here would be a dead end — the chips wrap
           * cleanly (flex-wrap) with no horizontal scroll at any breakpoint. */}
          <AmenityChips amenities={row.amenities} />
        </div>
        <div className="rt-card__stats">
          <div className="rt-stat">
            <span className="rt-stat__label">{b.capacity}</span>
            <span className="rt-stat__value">
              {formatCapacity(row.base_capacity, row.max_capacity, t, locale)}
            </span>
          </div>
          <div className="rt-stat">
            <span className="rt-stat__label">{b.pricePerNight}</span>
            <span className="rt-stat__value">
              {row.base_rate ? formatMoney(row.base_rate, currency, locale) : "—"}
            </span>
          </div>
          <div className="rt-stat">
            <span className="rt-stat__label">{t.rooms.types.roomCount}</span>
            <span className="rt-stat__value">{row.room_count}</span>
          </div>
        </div>
        <div className="rt-card__aside">
          <Badge tone={row.is_active ? "success" : "neutral"}>
            {row.is_active ? t.plans.active : t.plans.inactive}
          </Badge>
          <div className="rt-card__actions">
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
        </div>
      </div>
    );
  }

  return (
    <>
      {embedded ? (
        <div className="rt-toolbar">
          <p className="rt-toolbar__hint">{b.roomTypesHint}</p>
          {addButton}
        </div>
      ) : (
        <SectionHeader title={t.rooms.tabs.types} icon={Package} actions={addButton} />
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
            action={addButton}
          />
        ) : (
          <div role="list" aria-label={t.rooms.tabs.types} className="rt-list">
            {rows.map(renderCard)}
          </div>
        )
      ) : null}

      <RoomTypeModal
        open={creating}
        types={rows}
        currency={currency}
        onClose={() => setCreating(false)}
        onSaved={() => { setCreating(false); notify(t.rooms.saved); load(); }}
      />
      <RoomTypeModal
        open={editing !== null}
        roomType={editing ?? undefined}
        types={rows}
        currency={currency}
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

interface TypeFieldErrors {
  name?: string;
  capacity?: string;
  rate?: string;
  amenities?: string;
}

function RoomTypeModal({
  open,
  roomType,
  types,
  currency,
  onClose,
  onSaved,
}: {
  open: boolean;
  roomType?: RoomType;
  types: RoomType[];
  currency: string;
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
  const [fieldErrors, setFieldErrors] = useState<TypeFieldErrors>({});
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
    setFieldErrors({});
  }, [open, roomType]);

  function addAmenity(key: string) {
    if (!key || amenities.includes(key)) return;
    // Selecting one side of a mutually-exclusive pair deselects the other so
    // the two can never coexist (smoking vs non-smoking).
    const conflict = AMENITY_CONFLICTS[key];
    setAmenities((prev) => [...prev.filter((a) => a !== conflict), key]);
    setFieldErrors((prev) => ({ ...prev, amenities: undefined }));
  }
  function removeAmenity(key: string) {
    setAmenities((prev) => prev.filter((a) => a !== key));
    setFieldErrors((prev) => ({ ...prev, amenities: undefined }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    // Per-field validation — each message is tied to its own control.
    const errs: TypeFieldErrors = {};
    if (!name.trim()) errs.name = b.nameRequired;
    const capNum = Number(capacity);
    if (!Number.isFinite(capNum) || capNum < 1) errs.capacity = b.capacityInvalid;
    if (rate.trim() && (!Number.isFinite(Number(rate)) || Number(rate) < 0)) {
      errs.rate = b.rateInvalid;
    }
    if (amenities.includes("smoking") && amenities.includes("no_smoking")) {
      errs.amenities = b.amenityConflict;
    }
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs);
      return;
    }
    setFieldErrors({});
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

  // Hide already-chosen amenities AND any option that conflicts with a chosen
  // one, so the picker can never offer a contradictory pair.
  const available = AMENITY_KEYS.filter(
    (key) =>
      !amenities.includes(key) &&
      !(AMENITY_CONFLICTS[key] && amenities.includes(AMENITY_CONFLICTS[key])),
  );
  const priceLabel = currency ? `${b.pricePerNight} — ${currency}` : b.pricePerNight;

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
          <FormField label={b.roomTypeName} htmlFor="type-name" error={fieldErrors.name}>
            <Input
              id="type-name"
              value={name}
              placeholder={b.typeNamePlaceholder}
              required
              invalid={!!fieldErrors.name}
              onChange={(e) => {
                setName(e.target.value);
                if (fieldErrors.name) setFieldErrors((p) => ({ ...p, name: undefined }));
              }}
            />
          </FormField>
          <FormField
            label={b.capacity}
            htmlFor="type-capacity"
            hint={b.capacityHint}
            error={fieldErrors.capacity}
          >
            <Input
              id="type-capacity"
              type="number"
              min="1"
              step="1"
              inputMode="numeric"
              value={capacity}
              invalid={!!fieldErrors.capacity}
              onChange={(e) => {
                setCapacity(e.target.value);
                if (fieldErrors.capacity) {
                  setFieldErrors((p) => ({ ...p, capacity: undefined }));
                }
              }}
            />
          </FormField>
          <FormField label={priceLabel} htmlFor="type-rate" error={fieldErrors.rate}>
            <Input
              id="type-rate"
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={rate}
              invalid={!!fieldErrors.rate}
              onChange={(e) => {
                setRate(e.target.value);
                if (fieldErrors.rate) setFieldErrors((p) => ({ ...p, rate: undefined }));
              }}
            />
          </FormField>
          <FormField
            label={b.amenitiesLabel}
            htmlFor="type-amenity-picker"
            error={fieldErrors.amenities}
          >
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
