import type { ReactNode } from "react";

interface StatusSummaryItem {
  label: string;
  value: ReactNode;
  emphasis?: boolean;
}

interface StatusSummaryCardProps {
  title?: string;
  badge?: ReactNode;
  items: StatusSummaryItem[];
}

/** Central label/value summary strip (e.g. folio totals & balance). */
export function StatusSummaryCard({ title, badge, items }: StatusSummaryCardProps) {
  return (
    <div className="card status-summary">
      {title || badge ? (
        <div className="status-summary__head">
          {title ? <span className="status-summary__title">{title}</span> : null}
          {badge ?? null}
        </div>
      ) : null}
      <div className="status-summary__items">
        {items.map((item, i) => (
          <div
            key={i}
            className={item.emphasis ? "status-summary__item status-summary__item--emphasis" : "status-summary__item"}
          >
            <span className="muted">{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}
