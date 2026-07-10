"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  Alert,
  Button,
  FormField,
  Input,
  Modal,
  Select,
  Switch,
} from "@/components/ui";
import { changeRoomStatus, createRoom, updateRoom, type RoomWriteBody } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type { Floor, Room, RoomStatus, RoomType } from "@/lib/api/types";
import { roomStatusLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

/** Operational statuses that may be SET here (archived stays on the status
 * modal path; occupied/reserved are computed and never stored). */
const SETTABLE_STATUSES: RoomStatus[] = [
  "available",
  "dirty",
  "cleaning",
  "maintenance",
  "out_of_service",
];
const NOTE_REQUIRED: RoomStatus[] = ["maintenance", "out_of_service"];

/**
 * Central add/edit room modal (owner UX round): number/floor/type/display
 * name/active are the STORED room fields; capacity and price are shown
 * read-only from the selected room type (no per-room backend fields exist —
 * deliberately not invented); the initial/edited status goes through the
 * CONTROLLED status endpoint (rooms.status_update) after saving, with the
 * note the backend requires for maintenance / out-of-service.
 */
export function RoomFormModal({
  open,
  room,
  floors,
  types,
  onClose,
  onSaved,
}: {
  open: boolean;
  room?: Room;
  floors: Floor[];
  types: RoomType[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  const access = useHotelAccess();
  const canStatus =
    access === null || (!access.loading && access.can("rooms.status_update"));

  const [number, setNumber] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [floor, setFloor] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState<RoomStatus>("available");
  const [statusNote, setStatusNote] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setNumber(room?.number ?? "");
    setDisplayName(room?.display_name ?? "");
    setFloor(room ? String(room.floor) : "");
    setType(room ? String(room.room_type) : "");
    setStatus(room && room.status !== "archived" ? room.status : "available");
    setStatusNote(room?.status_note ?? "");
    setIsActive(room?.is_active ?? true);
    setError(null);
  }, [open, room]);

  const selectedType = useMemo(
    () => types.find((ty) => String(ty.id) === type) ?? null,
    [types, type],
  );
  const statusChanged = status !== (room?.status ?? "available");
  const noteMissing =
    canStatus &&
    statusChanged &&
    NOTE_REQUIRED.includes(status) &&
    !statusNote.trim();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!number.trim() || !floor || !type) {
      setError(t.errors.validation);
      return;
    }
    if (noteMissing) {
      setError(t.rooms.list.statusNoteHint);
      return;
    }
    const body: RoomWriteBody = {
      number: number.trim(),
      display_name: displayName.trim(),
      floor: Number(floor),
      room_type: Number(type),
      is_active: isActive,
    };
    setBusy(true);
    try {
      const saved = room ? await updateRoom(room.id, body) : await createRoom(body);
      // The status travels its own CONTROLLED path (log + note rule).
      if (canStatus && statusChanged) {
        await changeRoomStatus(saved.id, status, statusNote);
      }
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const statusOptions = SETTABLE_STATUSES.map((s) => ({
    value: s,
    label: roomStatusLabel(s, t),
  }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={room ? t.rooms.list.editTitle : b.addRoomTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="room-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="room-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={b.roomNumber} htmlFor="room-number">
            <Input
              id="room-number"
              value={number}
              placeholder={b.roomNumberPlaceholder}
              required
              onChange={(e) => setNumber(e.target.value)}
            />
          </FormField>
          <FormField label={t.rooms.list.displayName} htmlFor="room-display">
            <Input
              id="room-display"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </FormField>
          <FormField label={t.rooms.list.floor} htmlFor="room-floor-sel">
            <Select
              id="room-floor-sel"
              value={floor}
              placeholder={t.rooms.list.selectFloor}
              options={floors.map((f) => ({ value: String(f.id), label: f.name }))}
              onChange={(e) => setFloor(e.target.value)}
            />
          </FormField>
          <FormField label={b.unitType} htmlFor="room-type-sel">
            <Select
              id="room-type-sel"
              value={type}
              placeholder={t.rooms.list.selectType}
              options={types.map((ty) => ({ value: String(ty.id), label: ty.name }))}
              onChange={(e) => setType(e.target.value)}
            />
          </FormField>
          {canStatus ? (
            <FormField label={b.unitStatus} htmlFor="room-status-sel">
              <Select
                id="room-status-sel"
                value={status}
                options={statusOptions}
                onChange={(e) => setStatus(e.target.value as RoomStatus)}
              />
            </FormField>
          ) : null}
          {canStatus && NOTE_REQUIRED.includes(status) ? (
            <FormField
              label={t.rooms.list.statusNote}
              htmlFor="room-status-note"
              hint={t.rooms.list.statusNoteHint}
            >
              <Input
                id="room-status-note"
                value={statusNote}
                onChange={(e) => setStatusNote(e.target.value)}
              />
            </FormField>
          ) : null}
        </div>
        {selectedType ? (
          <p className="muted">
            {b.capacity}: {selectedType.base_capacity}–{selectedType.max_capacity}
            {selectedType.base_rate
              ? ` · ${b.pricePerNight}: ${selectedType.base_rate}`
              : ""}{" "}
            — {b.fromTypeHint}
          </p>
        ) : null}
        <Switch
          id="room-active"
          label={t.rooms.floors.active}
          checked={isActive}
          onChange={setIsActive}
        />
      </form>
    </Modal>
  );
}
