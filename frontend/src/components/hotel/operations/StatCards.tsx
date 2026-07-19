"use client";

import type { LucideIcon } from "lucide-react";

import { SmartStatCard, type SmartStatTone } from "@/components/ui";

/** One counter tile in the operations stat row. */
export interface OperationStat {
  key: string;
  label: string;
  /** `null` while the count is still loading (renders a skeleton). */
  value: number | null;
  icon: LucideIcon;
  tone: SmartStatTone;
  /** When set, the tile becomes a filter TOGGLE (counter-as-filter). Omit for a
   * display-only counter (e.g. "upcoming arrival", which is not a list status). */
  onFilter?: () => void;
  active?: boolean;
}

/**
 * The relocated Overview counters: a compact, filterable stat-card row shown
 * atop each operations tab (WP10 §2). Clicking a tile that carries `onFilter`
 * applies the matching list filter and marks itself selected (`aria-pressed`);
 * display-only tiles render as static `<div>`s. Built entirely on the central
 * SmartStatCard / `.board-stat` family — no bespoke visuals.
 */
export function StatCards({
  stats,
  loading = false,
  ariaLabel,
}: {
  stats: OperationStat[];
  loading?: boolean;
  ariaLabel: string;
}) {
  return (
    <div className="op-stats" role="group" aria-label={ariaLabel}>
      {stats.map((stat) => (
        <SmartStatCard
          key={stat.key}
          value={stat.value}
          label={stat.label}
          icon={stat.icon}
          tone={stat.tone}
          loading={loading && stat.value === null}
          active={stat.active}
          onClick={stat.onFilter}
        />
      ))}
    </div>
  );
}
