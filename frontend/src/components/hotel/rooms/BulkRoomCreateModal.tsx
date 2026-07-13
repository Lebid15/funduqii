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
import { bulkCreateRooms, getOperationalBoard } from "@/lib/api/rooms";
import { isApiError, messageForError } from "@/lib/api/errors";
import type { Floor, RoomBulkRow, RoomStatus, RoomType } from "@/lib/api/types";
import { roomStatusLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

/** Hard cap — mirrors the backend MAX_BULK_ROOMS (all-or-nothing batch). */
const MAX_RANGE = 100;
const SETTABLE_STATUSES: RoomStatus[] = [
  "available",
  "dirty",
  "cleaning",
  "maintenance",
  "out_of_service",
];
const NOTE_REQUIRED: RoomStatus[] = ["maintenance", "out_of_service"];

/**
 * Bulk room creation (owner spec): floor + type + a numeric range (optional
 * prefix) with an optional initial status, an explicit PREVIEW with existing
 * numbers called out and auto-skipped, a 100-room client cap, then ONE
 * all-or-nothing request to `POST /rooms/bulk/` (no per-room loop). The result
 * reports created_count and maps the typed error codes to readable messages.
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
  const bulk = t.rooms.bulk;
  const access = useHotelAccess();
  const canStatus =
    access === null || (!access.loading && access.can("rooms.status_update"));

  const [existing, setExisting] = useState<Set<string>>(new Set());
  const [floor, setFloor] = useState("");
  const [type, setType] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [prefix, setPrefix] = useState("");
  const [status, setStatus] = useState<RoomStatus>("available");
  const [statusNote, setStatusNote] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [createdCount, setCreatedCount] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    setFloor("");
    setType("");
    setFrom("");
    setTo("");
    setPrefix("");
    setStatus("available");
    setStatusNote("");
    setIsActive(true);
    setError(null);
    setCreatedCount(null);
    // Existing numbers (incl. archived) for the duplicate preview — one
    // read-only call so known collisions are auto-skipped before submit.
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
  const noteMissing =
    canStatus &&
    status !== "available" &&
    NOTE_REQUIRED.includes(status) &&
    !statusNote.trim();

  /** Map the typed bulk error codes (with their details) to readable text. */
  function describeError(err: unknown): string {
    if (isApiError(err)) {
      const details =
        err.details && typeof err.details === "object"
          ? (err.details as Record<string, unknown>)
          : {};
      if (err.code === "duplicate_room_number") {
        const nums = Array.isArray(details.numbers)
          ? (details.numbers as string[]).join("، ")
          : "";
        return details.source === "existing"
          ? bulk.duplicateExisting.replace("{numbers}", nums)
          : bulk.duplicateInRequest.replace("{numbers}", nums);
      }
      if (err.code === "bulk_request_too_large") {
        return bulk.tooLarge.replace("{limit}", String(details.limit ?? MAX_RANGE));
      }
      if (err.code === "room_limit_reached") {
        return bulk.limitReached
          .replace("{usage}", String(details.usage ?? "—"))
          .replace("{limit}", String(details.limit ?? "—"));
      }
    }
    return messageForError(err, t);
  }

  async function run() {
    if (!floor || !type || fresh.length === 0) {
      setError(t.errors.validation);
      return;
    }
    if (fresh.length > MAX_RANGE) {
      setError(bulk.tooLarge.replace("{limit}", String(MAX_RANGE)));
      return;
    }
    if (noteMissing) {
      setError(t.rooms.list.statusNoteHint);
      return;
    }
    setError(null);
    setBusy(true);
    const withStatus = canStatus && status !== "available";
    const rows: RoomBulkRow[] = fresh.map((number) => ({
      number,
      floor: Number(floor),
      room_type: Number(type),
      is_active: isActive,
      ...(withStatus
        ? { initial_status: status, status_note: statusNote.trim() }
        : {}),
    }));
    try {
      const res = await bulkCreateRooms(rows);
      setCreatedCount(res.created_count);
      onCreated();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  const floorOptions = floors.map((f) => ({ value: String(f.id), label: f.name }));
  // Only ACTIVE types are offered for new rooms (owner rule).
  const typeOptions = types
    .filter((ty) => ty.is_active)
    .map((ty) => ({ value: String(ty.id), label: ty.name }));
  const statusOptions = SETTABLE_STATUSES.map((s) => ({
    value: s,
    label: roomStatusLabel(s, t),
  }));

  const done = createdCount !== null;

  return (
    <Modal
      open={open}
      onClose={busy ? () => undefined : onClose}
      title={b.addRoomRange}
      closeLabel={t.common.close}
      footer={
        done ? (
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
      {done ? (
        <div className="stack">
          <Alert tone="success">
            {bulk.createdCount.replace("{count}", String(createdCount))}
          </Alert>
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
            <FormField label={t.rooms.list.roomType} htmlFor="bulk-type">
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
            {canStatus ? (
              <FormField label={bulk.initialStatus} htmlFor="bulk-status">
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
        </div>
      )}
    </Modal>
  );
}
