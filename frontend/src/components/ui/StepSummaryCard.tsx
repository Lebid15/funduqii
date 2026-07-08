import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { Icon } from "./Icon";

interface StepSummaryRow {
  label: string;
  value: ReactNode;
}

interface StepSummaryCardProps {
  title: string;
  icon?: LucideIcon;
  hint?: string;
  rows: StepSummaryRow[];
}

/** Central review-before-save card: a compact list of the values the user is
 * about to submit (used as the last step of multi-section forms). */
export function StepSummaryCard({ title, icon, hint, rows }: StepSummaryCardProps) {
  return (
    <div className="step-summary">
      <div className="step-summary__head">
        {icon ? (
          <span className="step-summary__icon">
            <Icon icon={icon} size="sm" />
          </span>
        ) : null}
        <span className="step-summary__title">{title}</span>
      </div>
      <dl className="step-summary__rows">
        {rows.map((row, i) => (
          <div key={i} className="step-summary__row">
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
      {hint ? <p className="muted small">{hint}</p> : null}
    </div>
  );
}
