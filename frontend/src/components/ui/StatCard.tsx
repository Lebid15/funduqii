import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";

type StatTone = "primary" | "success" | "warning" | "danger" | "info" | "neutral";

interface StatCardProps {
  label: string;
  value: number | string;
  icon?: LucideIcon;
  tone?: StatTone;
}

/** Central summary tile with a tinted icon chip. Used on the dashboard. */
export function StatCard({ label, value, icon, tone = "neutral" }: StatCardProps) {
  return (
    <div className="stat-card">
      {icon ? (
        <span className={cx("stat-card__icon", `stat-card__icon--${tone}`)}>
          <Icon icon={icon} size="lg" />
        </span>
      ) : null}
      <span className="stat-card__body">
        <span className="stat-card__label">{label}</span>
        <span className="stat-card__value">{value}</span>
      </span>
    </div>
  );
}
