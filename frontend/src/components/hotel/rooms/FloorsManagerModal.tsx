"use client";

import { useEffect, useMemo, useState } from "react";

import {
  Alert,
  Button,
  FormField,
  Input,
  Modal,
  useToast,
} from "@/components/ui";
import { createFloor, deleteFloor } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type { Floor } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Floors manager (owner UX round): a COUNT-based smart front over the
 * existing Floor records and APIs — raising the count auto-creates the
 * missing floors with clear names; lowering it deletes only EMPTY trailing
 * floors and is blocked below the highest floor that has rooms. Nothing
 * destructive: the backend refuses deleting a floor with rooms anyway.
 */
export function FloorsManagerModal({
  open,
  floors,
  onClose,
  onChanged,
}: {
  open: boolean;
  floors: Floor[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  const { notify } = useToast();

  const [count, setCount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [busy, setBusy] = useState(false);

  const ordered = useMemo(
    () => [...floors].sort((a, x) => a.sort_order - x.sort_order || a.id - x.id),
    [floors],
  );
  // 1-based position of the highest floor that still holds rooms.
  const highestUsed = useMemo(() => {
    let highest = 0;
    ordered.forEach((floor, index) => {
      if (floor.room_count > 0) highest = index + 1;
    });
    return highest;
  }, [ordered]);

  useEffect(() => {
    if (!open) return;
    setCount(String(ordered.length));
    setError(null);
    setProgress("");
  }, [open, ordered.length]);

  async function save() {
    setError(null);
    const target = Number(count);
    if (!Number.isInteger(target) || target < 0 || target > 50) {
      setError(t.errors.validation);
      return;
    }
    if (target < highestUsed) {
      setError(b.floorsReduceBlocked);
      return;
    }
    setBusy(true);
    try {
      if (target > ordered.length) {
        for (let n = ordered.length + 1; n <= target; n += 1) {
          setProgress(`${b.floorAutoName.replace("{n}", String(n))}…`);
          await createFloor({
            name: b.floorAutoName.replace("{n}", String(n)),
            number: String(n),
            sort_order: n,
          });
        }
      } else if (target < ordered.length) {
        // Trailing floors are empty here (guarded above) — delete them; the
        // backend still refuses any floor that has rooms (defense in depth).
        for (let i = ordered.length - 1; i >= target; i -= 1) {
          setProgress(`${ordered[i].name}…`);
          await deleteFloor(ordered[i].id);
        }
      }
      notify(t.rooms.saved);
      onChanged();
      onClose();
    } catch (err) {
      setError(messageForError(err, t));
      onChanged();
    } finally {
      setBusy(false);
      setProgress("");
    }
  }

  return (
    <Modal
      open={open}
      onClose={busy ? () => undefined : onClose}
      title={b.editFloors}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button onClick={save} loading={busy}>
            {b.saveFloors}
          </Button>
        </>
      }
    >
      <div className="stack">
        <strong>{b.floorSettings}</strong>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField
          label={b.enabledFloorCount}
          htmlFor="floors-count"
          hint={b.floorsReduceHint}
        >
          <Input
            id="floors-count"
            value={count}
            inputMode="numeric"
            onChange={(e) => setCount(e.target.value)}
          />
        </FormField>
        <div className="stack">
          <span className="muted">{b.currentFloors}</span>
          <div className="cluster">
            {ordered.map((floor) => (
              <span key={floor.id} className="chip">
                {floor.name}
                {floor.room_count > 0 ? ` (${floor.room_count})` : ""}
              </span>
            ))}
            {ordered.length === 0 ? <span className="muted">—</span> : null}
          </div>
        </div>
        {progress ? <p className="muted">{progress}</p> : null}
      </div>
    </Modal>
  );
}
