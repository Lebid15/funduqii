"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Building2 } from "lucide-react";

import {
  Alert,
  Button,
  Card,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  SectionHeader,
  useToast,
} from "@/components/ui";
import { createFloor, deleteFloor, listFloors } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type { Floor } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

/**
 * Floors tab (owner UX round): ONE simple setting — the hotel's floor
 * count. Raising it auto-creates the missing floors with clear localized
 * names (the backend's name/number/sort fields are filled automatically
 * and hidden from the user); lowering it deletes only EMPTY trailing
 * floors and is blocked below the highest floor that has rooms. The
 * detailed add-floor form is gone — nobody needs it day to day.
 */
export function FloorsTab({ embedded = false }: { embedded?: boolean } = {}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  const { notify } = useToast();
  const access = useHotelAccess();
  const canManage =
    access === null ||
    (!access.loading && access.can("rooms.create", "rooms.update", "rooms.delete"));

  const [floors, setFloors] = useState<Floor[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [count, setCount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = (await listFloors()).results;
      setFloors(data);
      setCount(String(data.length));
    } catch (err) {
      setLoadError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t is stable per locale
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
      setProgress("");
      load();
    }
  }

  if (loading) return <LoadingState label={t.common.loading} />;
  if (loadError) {
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={loadError}
        retryLabel={t.common.retry}
        onRetry={load}
      />
    );
  }

  return (
    <div className="stack">
      {embedded ? null : <SectionHeader title={t.rooms.tabs.floors} icon={Building2} />}
      <Card>
        <div className="stack">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <FormField
            label={b.floorCount}
            htmlFor="floors-count"
            hint={b.floorsReduceBlocked}
          >
            <Input
              id="floors-count"
              value={count}
              inputMode="numeric"
              disabled={!canManage}
              onChange={(e) => setCount(e.target.value)}
            />
          </FormField>
          {canManage ? (
            <div className="cluster">
              <Button onClick={save} loading={busy}>
                {b.saveFloorCount}
              </Button>
              {progress ? <span className="muted">{progress}</span> : null}
            </div>
          ) : null}
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
        </div>
      </Card>
    </div>
  );
}
