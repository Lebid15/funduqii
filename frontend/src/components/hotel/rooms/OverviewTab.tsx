"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BedDouble,
  BrushCleaning,
  CircleCheck,
  PauseCircle,
  Sparkles,
  Wrench,
} from "lucide-react";

import { ErrorState, StatCard } from "@/components/ui";
import { listRooms } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import { useI18n } from "@/lib/i18n/I18nProvider";

interface Counts {
  total: number;
  available: number;
  dirty: number;
  cleaning: number;
  maintenance: number;
  out_of_service: number;
}

/** Room counts by status, derived from room data only (no reservations). */
export function OverviewTab() {
  const { t } = useI18n();
  const [counts, setCounts] = useState<Counts | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [total, available, dirty, cleaning, maintenance, oos] =
        await Promise.all([
          listRooms(),
          listRooms({ status: "available" }),
          listRooms({ status: "dirty" }),
          listRooms({ status: "cleaning" }),
          listRooms({ status: "maintenance" }),
          listRooms({ status: "out_of_service" }),
        ]);
      setCounts({
        total: total.count,
        available: available.count,
        dirty: dirty.count,
        cleaning: cleaning.count,
        maintenance: maintenance.count,
        out_of_service: oos.count,
      });
    } catch (err) {
      setError(messageForError(err, t));
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={error}
        retryLabel={t.common.retry}
        onRetry={load}
      />
    );
  }

  const c = counts;
  return (
    <section className="stat-grid">
      <StatCard label={t.rooms.overview.total} value={c?.total ?? "—"} icon={BedDouble} tone="primary" />
      <StatCard label={t.rooms.overview.available} value={c?.available ?? "—"} icon={CircleCheck} tone="success" />
      <StatCard label={t.rooms.overview.needsCleaning} value={c?.dirty ?? "—"} icon={Sparkles} tone="warning" />
      <StatCard label={t.rooms.overview.cleaning} value={c?.cleaning ?? "—"} icon={BrushCleaning} tone="info" />
      <StatCard label={t.rooms.overview.maintenance} value={c?.maintenance ?? "—"} icon={Wrench} tone="danger" />
      <StatCard label={t.rooms.overview.outOfService} value={c?.out_of_service ?? "—"} icon={PauseCircle} tone="neutral" />
    </section>
  );
}
