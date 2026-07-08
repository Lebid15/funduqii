import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { Icon } from "./Icon";

interface SectionCardProps {
  title: string;
  icon?: LucideIcon;
  description?: string;
  children: ReactNode;
}

/** Central titled section wrapper — used to split long forms and pages into
 * clear, numbered/labelled blocks without ad-hoc CSS. */
export function SectionCard({ title, icon, description, children }: SectionCardProps) {
  return (
    <section className="section-card">
      <header className="section-card__head">
        {icon ? (
          <span className="section-card__icon">
            <Icon icon={icon} size="sm" />
          </span>
        ) : null}
        <div>
          <h3 className="section-card__title">{title}</h3>
          {description ? <p className="section-card__desc">{description}</p> : null}
        </div>
      </header>
      <div className="section-card__body">{children}</div>
    </section>
  );
}
