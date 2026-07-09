"use client";

import { useEffect, useState, type FormEvent } from "react";

import {
  Alert,
  Button,
  FormField,
  Input,
  Modal,
  Select,
} from "@/components/ui";
import { changeRoomStatus } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type { RoomStatus } from "@/lib/api/types";
import { roomStatusLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

const STATUSES: RoomStatus[] = [
  "available",
  "dirty",
  "cleaning",
  "maintenance",
  "out_of_service",
  "archived",
];

/** The minimal room shape the status modal needs — served by both the rooms
 * management tab (`Room`) and the operational board (`RoomBoardRoom`). */
export interface StatusModalRoom {
  id: number;
  status: RoomStatus;
  status_note?: string;
}

/** Central controlled room-status change (Phase 5 path: note required for
 * maintenance/out-of-service, every change logged server-side). */
export function RoomStatusModal({
  open,
  room,
  onClose,
  onSaved,
}: {
  open: boolean;
  room?: StatusModalRoom;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [status, setStatus] = useState<RoomStatus>("available");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !room) return;
    setStatus(room.status);
    setNote(room.status_note ?? "");
    setError(null);
  }, [open, room]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!room) return;
    setError(null);
    setBusy(true);
    try {
      await changeRoomStatus(room.id, status, note);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const statusOptions = STATUSES.map((s) => ({ value: s, label: roomStatusLabel(s, t) }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.rooms.list.changeStatusTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="status-form" type="submit" loading={busy}>{t.common.save}</Button>
        </>
      }
    >
      <form id="status-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={t.rooms.list.newStatus} htmlFor="status-sel">
          <Select id="status-sel" value={status} options={statusOptions} onChange={(e) => setStatus(e.target.value as RoomStatus)} />
        </FormField>
        <FormField label={t.rooms.list.statusNote} htmlFor="status-note" hint={t.rooms.list.statusNoteHint}>
          <Input id="status-note" value={note} onChange={(e) => setNote(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}
