"use client";

import { useEffect, useState, type FormEvent } from "react";

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
 * Central add/edit room modal (owner UX round): the ROOM is deliberately
 * simple — number, floor, type, status, active. Capacity / price /
 * amenities / public visibility all come from the room TYPE, so they are
 * not on this form. The status travels the CONTROLLED endpoint
 * (rooms.status_update) with the note the backend requires for
 * maintenance / out-of-service. Only ACTIVE types are offered for new
 * rooms; an existing room keeps showing its current type even if disabled.
 */
export function RoomFormModal({
  open,
  room,
  floors,
  types,
  initialFloor,
  onClose,
  onSaved,
}: {
  open: boolean;
  room?: Room;
  floors: Floor[];
  types: RoomType[];
  /** Pre-selects a floor on CREATE (e.g. "add room to this floor"). */
  initialFloor?: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  const access = useHotelAccess();
  const canStatus =
    access === null || (!access.loading && access.can("rooms.status_update"));

  const [number, setNumber] = useState("");
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
    setFloor(
      room ? String(room.floor) : initialFloor ? String(initialFloor) : "",
    );
    setType(room ? String(room.room_type) : "");
    setStatus(room && room.status !== "archived" ? room.status : "available");
    setStatusNote(room?.status_note ?? "");
    setIsActive(room?.is_active ?? true);
    setError(null);
  }, [open, room, initialFloor]);

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
      floor: Number(floor),
      room_type: Number(type),
      is_active: isActive,
    };
    setBusy(true);
    try {
      if (room) {
        // EDIT: the room fields, then the status via its own CONTROLLED path.
        await updateRoom(room.id, body);
        if (canStatus && statusChanged) {
          await changeRoomStatus(room.id, status, statusNote);
        }
      } else {
        // CREATE: a non-available initial status travels write-only on the
        // SAME create request (backend requires rooms.status_update for it).
        if (canStatus && status !== "available") {
          body.initial_status = status;
          body.status_note = statusNote.trim();
        }
        await createRoom(body);
      }
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  // Only ACTIVE types are offered (owner rule) — plus the room's current
  // type when editing, so the select never shows an empty value.
  const typeOptions = types
    .filter((ty) => ty.is_active || (room && ty.id === room.room_type))
    .map((ty) => ({ value: String(ty.id), label: ty.name }));

  const statusOptions = SETTABLE_STATUSES.map((s) => ({
    value: s,
    label: roomStatusLabel(s, t),
  }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={room ? b.editRoom : b.addRoomTitle}
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
          <FormField label={t.rooms.list.floor} htmlFor="room-floor-sel">
            <Select
              id="room-floor-sel"
              value={floor}
              placeholder={t.rooms.list.selectFloor}
              options={floors.map((f) => ({ value: String(f.id), label: f.name }))}
              onChange={(e) => setFloor(e.target.value)}
            />
          </FormField>
          <FormField label={t.rooms.list.roomType} htmlFor="room-type-sel">
            <Select
              id="room-type-sel"
              value={type}
              placeholder={t.rooms.list.selectType}
              options={typeOptions}
              onChange={(e) => setType(e.target.value)}
            />
          </FormField>
          {canStatus ? (
            <FormField label={b.roomStatus} htmlFor="room-status-sel">
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
