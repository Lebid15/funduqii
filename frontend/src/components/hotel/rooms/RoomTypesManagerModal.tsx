"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Pencil, Plus, Power, Trash2 } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  FormField,
  Input,
  Modal,
  Switch,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  createRoomType,
  deleteRoomType,
  updateRoomType,
  type RoomTypeWriteBody,
} from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type { RoomType } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** Auto-suggest the next free short code (`T1`, `T2`, …) — the backend
 * requires a per-hotel-unique code; the field stays editable. */
function nextCode(types: RoomType[]): string {
  const taken = new Set(types.map((ty) => ty.code.toUpperCase()));
  let n = types.length + 1;
  while (taken.has(`T${n}`)) n += 1;
  return `T${n}`;
}

/**
 * Room-types manager (owner UX round): one modal that both ADDS a type
 * (name/capacity/base rate/description/active — existing create API) and
 * MANAGES the current catalog (edit inline, enable/disable, delete). The
 * backend refuses deleting a type that has rooms (ResourceInUse) — the
 * modal surfaces that clearly and offers disabling instead.
 */
export function RoomTypesManagerModal({
  open,
  types,
  onClose,
  onChanged,
}: {
  open: boolean;
  types: RoomType[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  const { notify } = useToast();

  const [editing, setEditing] = useState<RoomType | null>(null);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [baseCapacity, setBaseCapacity] = useState("2");
  const [maxCapacity, setMaxCapacity] = useState("2");
  const [baseRate, setBaseRate] = useState("");
  const [description, setDescription] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rowBusy, setRowBusy] = useState<number | null>(null);

  function resetForm(target: RoomType | null) {
    setEditing(target);
    setName(target?.name ?? "");
    setCode(target?.code ?? nextCode(types));
    setBaseCapacity(String(target?.base_capacity ?? 2));
    setMaxCapacity(String(target?.max_capacity ?? 2));
    setBaseRate(target?.base_rate ?? "");
    setDescription(target?.description ?? "");
    setIsActive(target?.is_active ?? true);
    setError(null);
  }

  useEffect(() => {
    if (!open) return;
    resetForm(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset on open
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!name.trim() || !code.trim()) {
      setError(t.errors.validation);
      return;
    }
    const base = Number(baseCapacity) || 1;
    const max = Math.max(base, Number(maxCapacity) || base);
    const body: RoomTypeWriteBody = {
      name: name.trim(),
      code: code.trim(),
      base_capacity: base,
      max_capacity: max,
      base_rate: baseRate.trim() ? baseRate.trim() : null,
      description: description.trim(),
      is_active: isActive,
    };
    setBusy(true);
    try {
      if (editing) await updateRoomType(editing.id, body);
      else await createRoomType(body);
      notify(t.rooms.saved);
      onChanged();
      resetForm(null);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(target: RoomType) {
    setRowBusy(target.id);
    try {
      await updateRoomType(target.id, { is_active: !target.is_active });
      notify(t.rooms.saved);
      onChanged();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setRowBusy(null);
    }
  }

  async function remove(target: RoomType) {
    setRowBusy(target.id);
    setError(null);
    try {
      await deleteRoomType(target.id);
      notify(t.rooms.saved);
      onChanged();
    } catch (err) {
      // The backend blocks deleting a used type — say it plainly.
      setError(`${target.name}: ${messageForError(err, t)} — ${b.typeInUseHint}`);
    } finally {
      setRowBusy(null);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={b.roomTypes}
      closeLabel={t.common.close}
      footer={
        <Button variant="secondary" onClick={onClose}>
          {t.common.close}
        </Button>
      }
    >
      <div className="stack">
        <p className="muted">{b.roomTypesHint}</p>
        {error ? <Alert tone="error">{error}</Alert> : null}

        <form className="stack" onSubmit={submit} noValidate>
          <strong>{editing ? t.common.edit : b.addNewType}</strong>
          <div className="form-grid">
            <FormField label={b.typeName} htmlFor="rt-name">
              <Input
                id="rt-name"
                value={name}
                placeholder={b.typeNamePlaceholder}
                required
                onChange={(e) => setName(e.target.value)}
              />
            </FormField>
            <FormField label={b.typeCode} htmlFor="rt-code">
              <Input
                id="rt-code"
                value={code}
                required
                onChange={(e) => setCode(e.target.value)}
              />
            </FormField>
            <FormField label={b.defaultCapacity} htmlFor="rt-base">
              <Input
                id="rt-base"
                value={baseCapacity}
                inputMode="numeric"
                onChange={(e) => setBaseCapacity(e.target.value)}
              />
            </FormField>
            <FormField label={b.maxCapacity} htmlFor="rt-max">
              <Input
                id="rt-max"
                value={maxCapacity}
                inputMode="numeric"
                onChange={(e) => setMaxCapacity(e.target.value)}
              />
            </FormField>
            <FormField label={b.basePrice} htmlFor="rt-rate">
              <Input
                id="rt-rate"
                value={baseRate}
                inputMode="decimal"
                onChange={(e) => setBaseRate(e.target.value)}
              />
            </FormField>
          </div>
          <FormField label={b.typeDescription} htmlFor="rt-desc">
            <Textarea
              id="rt-desc"
              value={description}
              rows={2}
              onChange={(e) => setDescription(e.target.value)}
            />
          </FormField>
          <div className="cluster">
            <Switch
              id="rt-active"
              label={b.typeActive}
              checked={isActive}
              onChange={setIsActive}
            />
            <Button type="submit" icon={Plus} loading={busy}>
              {editing ? t.common.save : b.addTypeAction}
            </Button>
            {editing ? (
              <Button variant="ghost" onClick={() => resetForm(null)} disabled={busy}>
                {t.common.cancel}
              </Button>
            ) : null}
          </div>
        </form>

        <div className="stack">
          {types.map((ty) => (
            <div key={ty.id} className="type-row">
              <span className="type-row__main">
                <strong>{ty.name}</strong>
                <span className="muted">
                  {b.capacity}: {ty.base_capacity}–{ty.max_capacity}
                  {ty.base_rate ? ` · ${b.basePrice}: ${ty.base_rate}` : ""}
                  {` · ${ty.code}`}
                </span>
              </span>
              <Badge tone={ty.is_active ? "success" : "neutral"}>
                {ty.is_active ? b.typeActive : b.typeInactive}
              </Badge>
              <span className="cluster">
                <Button
                  variant="ghost"
                  size="sm"
                  icon={Pencil}
                  onClick={() => resetForm(ty)}
                  disabled={rowBusy === ty.id}
                >
                  {t.common.edit}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={Power}
                  onClick={() => toggleActive(ty)}
                  disabled={rowBusy === ty.id}
                >
                  {ty.is_active ? b.disableAction : b.enableAction}
                </Button>
                {ty.room_count === 0 ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={Trash2}
                    onClick={() => remove(ty)}
                    disabled={rowBusy === ty.id}
                  >
                    {t.common.delete}
                  </Button>
                ) : null}
              </span>
            </div>
          ))}
          {types.length === 0 ? <p className="muted">{b.noTypesYet}</p> : null}
        </div>
      </div>
    </Modal>
  );
}
