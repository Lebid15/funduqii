"use client";

import { useEffect, useMemo, useState } from "react";

import {
  Alert,
  Button,
  FormField,
  Input,
  Modal,
  Select,
  Switch,
} from "@/components/ui";
import {
  changeRoomStatus,
  createRoom,
  getOperationalBoard,
} from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type { Floor, RoomStatus, RoomType } from "@/lib/api/types";
import { roomStatusLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

const MAX_RANGE = 100;
const SETTABLE_STATUSES: RoomStatus[] = [
  "available",
  "dirty",
  "cleaning",
  "maintenance",
  "out_of_service",
];
const NOTE_REQUIRED: RoomStatus[] = ["maintenance", "out_of_service"];

interface BulkResult {
  created: string[];
  failed: Array<{ number: string; reason: string }>;
}

/**
 * Bulk room creation (owner spec): floor + type + a numeric range (optional
 * prefix / display-name base) with capacity & price shown from the type,
 * an optional initial status (controlled endpoint, note when required), an
 * explicit PREVIEW with duplicates called out and auto-skipped, a 100-room
 * cap, then sequential `createRoom` calls (no new backend) with live
 * progress and an honest created/failed summary.
 */
export function BulkRoomCreateModal({
  open,
  floors,
  types,
  onClose,
  onCreated,
}: {
  open: boolean;
  floors: Floor[];
  types: RoomType[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  const access = useHotelAccess();
  const canStatus =
    access === null || (!access.loading && access.can("rooms.status_update"));

  const [existing, setExisting] = useState<Set<string>>(new Set());
  const [floor, setFloor] = useState("");
  const [type, setType] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [prefix, setPrefix] = useState("");
  const [nameBase, setNameBase] = useState("");
  const [status, setStatus] = useState<RoomStatus>("available");
  const [statusNote, setStatusNote] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [result, setResult] = useState<BulkResult | null>(null);

  useEffect(() => {
    if (!open) return;
    setFloor("");
    setType("");
    setFrom("");
    setTo("");
    setPrefix("");
    setNameBase("");
    setStatus("available");
    setStatusNote("");
    setIsActive(true);
    setError(null);
    setProgress("");
    setResult(null);
    // Existing numbers (incl. archived) for the duplicate preview — one
    // read-only call.
    getOperationalBoard()
      .then((board) => setExisting(new Set(board.rooms.map((r) => r.number))))
      .catch(() => setExisting(new Set()));
  }, [open]);

  const rangeEntered = from.trim() !== "" && to.trim() !== "";
  const rangeValid =
    rangeEntered &&
    Number.isInteger(Number(from)) &&
    Number.isInteger(Number(to)) &&
    Number(from) <= Number(to);
  const rangeTooBig = rangeValid && Number(to) - Number(from) + 1 > MAX_RANGE;

  const numbers = useMemo(() => {
    if (!rangeValid || rangeTooBig) return [];
    const list: string[] = [];
    for (let n = Number(from); n <= Number(to); n += 1) {
      list.push(`${prefix.trim()}${n}`);
    }
    return list;
  }, [rangeValid, rangeTooBig, from, to, prefix]);

  const duplicates = numbers.filter((n) => existing.has(n));
  const fresh = numbers.filter((n) => !existing.has(n));
  const selectedType = types.find((ty) => String(ty.id) === type) ?? null;
  const noteMissing =
    canStatus &&
    status !== "available" &&
    NOTE_REQUIRED.includes(status) &&
    !statusNote.trim();

  async function run() {
    if (!floor || !type || fresh.length === 0) {
      setError(t.errors.validation);
      return;
    }
    if (noteMissing) {
      setError(t.rooms.list.statusNoteHint);
      return;
    }
    setError(null);
    setBusy(true);
    const created: string[] = [];
    const failed: Array<{ number: string; reason: string }> = [];
    for (let i = 0; i < fresh.length; i += 1) {
      const number = fresh[i];
      setProgress(
        b.bulkProgress
          .replace("{done}", String(i + 1))
          .replace("{total}", String(fresh.length)),
      );
      try {
        const room = await createRoom({
          number,
          display_name: nameBase.trim() ? `${nameBase.trim()} ${number}` : "",
          floor: Number(floor),
          room_type: Number(type),
          is_active: isActive,
        });
        // Optional initial status through the CONTROLLED endpoint.
        if (canStatus && status !== "available") {
          await changeRoomStatus(room.id, status, statusNote);
        }
        created.push(number);
      } catch (err) {
        failed.push({ number, reason: messageForError(err, t) });
      }
    }
    setBusy(false);
    setProgress("");
    setResult({ created, failed });
    if (created.length > 0) onCreated();
  }

  const floorOptions = floors.map((f) => ({ value: String(f.id), label: f.name }));
  const typeOptions = types.map((ty) => ({ value: String(ty.id), label: ty.name }));
  const statusOptions = SETTABLE_STATUSES.map((s) => ({
    value: s,
    label: roomStatusLabel(s, t),
  }));

  return (
    <Modal
      open={open}
      onClose={busy ? () => undefined : onClose}
      title={b.addRoomRange}
      closeLabel={t.common.close}
      footer={
        result ? (
          <Button variant="secondary" onClick={onClose}>{t.common.close}</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              {t.common.cancel}
            </Button>
            <Button
              onClick={run}
              loading={busy}
              disabled={busy || fresh.length === 0 || !floor || !type}
            >
              {b.bulkConfirm.replace("{count}", String(fresh.length))}
            </Button>
          </>
        )
      }
    >
      {result ? (
        <div className="stack">
          {result.created.length > 0 ? (
            <Alert tone="success">
              {b.bulkCreated.replace("{count}", String(result.created.length))}
            </Alert>
          ) : null}
          {result.failed.length > 0 ? (
            <Alert tone="error">
              {b.bulkFailed.replace("{count}", String(result.failed.length))}
            </Alert>
          ) : null}
          {result.failed.length > 0 ? (
            <ul className="room-op-bulk-list">
              {result.failed.map((f) => (
                <li key={f.number}>
                  <strong>{f.number}</strong> — {f.reason}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <div className="stack">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="form-grid">
            <FormField label={t.rooms.list.floor} htmlFor="bulk-floor">
              <Select
                id="bulk-floor"
                value={floor}
                placeholder={t.rooms.list.selectFloor}
                options={floorOptions}
                onChange={(e) => setFloor(e.target.value)}
              />
            </FormField>
            <FormField label={b.unitType} htmlFor="bulk-type">
              <Select
                id="bulk-type"
                value={type}
                placeholder={t.rooms.list.selectType}
                options={typeOptions}
                onChange={(e) => setType(e.target.value)}
              />
            </FormField>
            <FormField label={b.fromNumber} htmlFor="bulk-from">
              <Input
                id="bulk-from"
                value={from}
                placeholder={b.fromPlaceholder}
                inputMode="numeric"
                onChange={(e) => setFrom(e.target.value)}
              />
            </FormField>
            <FormField label={b.toNumber} htmlFor="bulk-to">
              <Input
                id="bulk-to"
                value={to}
                placeholder={b.toPlaceholder}
                inputMode="numeric"
                onChange={(e) => setTo(e.target.value)}
              />
            </FormField>
            <FormField label={b.numberPrefix} htmlFor="bulk-prefix">
              <Input
                id="bulk-prefix"
                value={prefix}
                onChange={(e) => setPrefix(e.target.value)}
              />
            </FormField>
            <FormField label={b.nameBase} htmlFor="bulk-name">
              <Input
                id="bulk-name"
                value={nameBase}
                onChange={(e) => setNameBase(e.target.value)}
              />
            </FormField>
            {canStatus ? (
              <FormField label={b.unitStatus} htmlFor="bulk-status">
                <Select
                  id="bulk-status"
                  value={status}
                  options={statusOptions}
                  onChange={(e) => setStatus(e.target.value as RoomStatus)}
                />
              </FormField>
            ) : null}
            {canStatus && NOTE_REQUIRED.includes(status) ? (
              <FormField
                label={t.rooms.list.statusNote}
                htmlFor="bulk-status-note"
                hint={t.rooms.list.statusNoteHint}
              >
                <Input
                  id="bulk-status-note"
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
            id="bulk-active"
            label={t.rooms.floors.active}
            checked={isActive}
            onChange={setIsActive}
          />
          {rangeEntered && !rangeValid ? (
            <Alert tone="warning">{b.invalidRange}</Alert>
          ) : null}
          {rangeTooBig ? (
            <Alert tone="warning">
              {b.bulkTooBig.replace("{max}", String(MAX_RANGE))}
            </Alert>
          ) : null}
          {numbers.length > 0 ? (
            <div className="stack">
              <p>
                {b.willCreate.replace("{count}", String(fresh.length))}
                {fresh.length > 0 ? `: ${fresh.join("، ")}` : ""}
              </p>
              {duplicates.length > 0 ? (
                <Alert tone="warning">
                  {b.duplicateRooms}: {duplicates.join("، ")}
                </Alert>
              ) : null}
            </div>
          ) : null}
          {progress ? <p className="muted">{progress}</p> : null}
        </div>
      )}
    </Modal>
  );
}
