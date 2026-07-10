import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";

/** Section sub-identity: tints the header wash + icon chip. */
type HeaderTone = "teal" | "indigo" | "violet" | "emerald";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  /** Optional section icon, rendered in a tinted container. */
  icon?: LucideIcon;
  tone?: HeaderTone;
}

/** Central page title block: tinted icon chip, strong title, subtitle and an
 * actions slot on a soft gradient wash — each section keeps its own accent. */
export function PageHeader({
  title,
  subtitle,
  actions,
  icon,
  tone = "teal",
}: PageHeaderProps) {
  return (
    <header className={cx("page-header", `page-header--${tone}`)}>
      <div className="page-header__lead">
        {icon ? (
          <span className="page-header__icon" aria-hidden="true">
            <Icon icon={icon} size="lg" />
          </span>
        ) : null}
        <div className="page-header__titles">
          <h1 className="page-header__title">{title}</h1>
          {subtitle ? <p className="page-header__subtitle">{subtitle}</p> : null}
        </div>
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}
