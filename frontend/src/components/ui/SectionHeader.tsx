import type { ReactNode } from "react";

interface SectionHeaderProps {
  title: string;
  actions?: ReactNode;
}

/** Central sub-section heading with an optional actions slot. */
export function SectionHeader({ title, actions }: SectionHeaderProps) {
  return (
    <div className="section-header">
      <h2 className="section-header__title">{title}</h2>
      {actions ?? null}
    </div>
  );
}
