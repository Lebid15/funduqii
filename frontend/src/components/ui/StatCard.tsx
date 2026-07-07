import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";

type StatTone = "primary" | "success" | "warning" | "danger" | "info" | "neutral";

interface StatCardProps {
  label: string;
  value: number | string;
  icon?: LucideIcon;
  tone?: StatTone;
  caption?: string;
}

/** Central summary tile: prominent value, label, tinted icon chip, and an
 * optional truthful caption. Used on the dashboard. */
export function StatCard({
  label,
  value,
  icon,
  tone = "neutral",
  caption,
}: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-card__top">
        <span className="stat-card__value">{value}</span>
        {icon ? (
          <span className={cx("stat-card__icon", `stat-card__icon--${tone}`)}>
            <Icon icon={icon} size="lg" />
          </span>
        ) : null}
      </div>
      <div className="stat-card__body">
        <span className="stat-card__label">{label}</span>
        {caption ? <span className="stat-card__caption">{caption}</span> : null}
      </div>
    </div>
  );
}
