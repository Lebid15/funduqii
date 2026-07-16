import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { Icon } from "./Icon";

interface ActionCardProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  meta?: ReactNode;
  action?: ReactNode;
}

/** Central row card for a single entity with one clear action (e.g. an
 * arriving reservation with a check-in button). */
export function ActionCard({ icon, title, description, meta, action }: ActionCardProps) {
  return (
    <div className="card action-card">
      <span className="action-card__icon">
        <Icon icon={icon} size="md" />
      </span>
      <div className="action-card__main">
        <strong className="action-card__title">{title}</strong>
        {description ? <span className="muted">{description}</span> : null}
        {meta ? <div className="action-card__meta">{meta}</div> : null}
      </div>
      {action ? <span className="action-card__action">{action}</span> : null}
    </div>
  );
}
