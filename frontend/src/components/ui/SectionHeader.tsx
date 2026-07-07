import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { Icon } from "./Icon";

interface SectionHeaderProps {
  title: string;
  description?: string;
  icon?: LucideIcon;
  actions?: ReactNode;
}

/** Central sub-section heading with an optional icon chip, description, and
 * actions slot. */
export function SectionHeader({
  title,
  description,
  icon,
  actions,
}: SectionHeaderProps) {
  return (
    <div className="section-header">
      <div className="section-header__lead">
        {icon ? (
          <span className="section-header__icon">
            <Icon icon={icon} size="md" />
          </span>
        ) : null}
        <div className="section-header__titles">
          <h2 className="section-header__title">{title}</h2>
          {description ? (
            <span className="section-header__desc">{description}</span>
          ) : null}
        </div>
      </div>
      {actions ?? null}
    </div>
  );
}
