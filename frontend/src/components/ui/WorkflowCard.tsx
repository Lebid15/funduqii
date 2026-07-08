import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";

type WorkflowTone = "primary" | "success" | "warning" | "danger" | "info" | "neutral";

interface WorkflowCardProps {
  icon: LucideIcon;
  title: string;
  value?: number | string;
  description?: string;
  tone?: WorkflowTone;
  action?: ReactNode;
}

/** Central workflow tile: an icon, a short title, a count/status, a one-line
 * description and a clear call-to-action. Used for front-desk style flows. */
export function WorkflowCard({
  icon,
  title,
  value,
  description,
  tone = "neutral",
  action,
}: WorkflowCardProps) {
  return (
    <div className="workflow-card">
      <div className="workflow-card__top">
        <span className={cx("stat-card__icon", `stat-card__icon--${tone}`)}>
          <Icon icon={icon} size="lg" />
        </span>
        {value !== undefined ? (
          <span className="workflow-card__value">{value}</span>
        ) : null}
      </div>
      <div className="workflow-card__body">
        <span className="workflow-card__title">{title}</span>
        {description ? (
          <span className="workflow-card__desc">{description}</span>
        ) : null}
      </div>
      {action ? <div className="workflow-card__action">{action}</div> : null}
    </div>
  );
}
