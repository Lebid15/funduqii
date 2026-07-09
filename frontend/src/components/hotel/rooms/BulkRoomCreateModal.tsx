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
import { createRoom } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type { Floor, RoomType } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

const MAX_RANGE = 100;

interface BulkResult {
  created: string[];
  failed: Array<{ number: string; reason: string }>;
}

/**
 * Bulk room creation (owner spec): floor + type + a numeric range (with an
 * optional prefix and display-name base) → an explicit PREVIEW with
 * duplicates called out, then sequential `createRoom` calls (no new backend)
 * with live progress and an honest created/failed summary.
 */
export function BulkRoomCreateModal({
  open,
  floors,
  types,
  existingNumbers,
  onClose,
  onCreated,
}: {
  open: boolean;
  floors: Floor[];
  types: RoomType[];
  existingNumbers: Set<string>;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;

  const [floor, setFloor] = useState("");
  const [type, setType] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [prefix, setPrefix] = useState("");
  const [nameBase, setNameBase] = useState("");
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
    setIsActive(true);
    setError(null);
    setProgress("");
    setResult(null);
  }, [open]);

  const numbers = useMemo(() => {
    const start = Number(from);
    const end = Number(to);
    if (
      !Number.isInteger(start) ||
      !Number.isInteger(end) ||
      from.trim() === "" ||
      to.trim() === "" ||
      start > end ||
      end - start + 1 > MAX_RANGE
    ) {
      return [];
    }
    const list: string[] = [];
    for (let n = start; n <= end; n += 1) list.push(`${prefix.trim()}${n}`);
    return list;
  }, [from, to, prefix]);

  const duplicates = numbers.filter((n) => existingNumbers.has(n));
  const fresh = numbers.filter((n) => !existingNumbers.has(n));
  const rangeTooBig =
    from.trim() !== "" &&
    to.trim() !== "" &&
    Number(to) - Number(from) + 1 > MAX_RANGE;

  async function run() {
    if (!floor || !type || fresh.length === 0) {
      setError(t.errors.validation);
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
        await createRoom({
          number,
          display_name: nameBase.trim() ? `${nameBase.trim()} ${number}` : "",
          floor: Number(floor),
          room_type: Number(type),
          is_active: isActive,
        });
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
                inputMode="numeric"
                onChange={(e) => setFrom(e.target.value)}
              />
            </FormField>
            <FormField label={b.toNumber} htmlFor="bulk-to">
              <Input
                id="bulk-to"
                value={to}
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
          </div>
          <Switch
            id="bulk-active"
            label={t.rooms.floors.active}
            checked={isActive}
            onChange={setIsActive}
          />
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
