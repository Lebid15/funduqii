import type { ReactNode } from "react";

/** Central filter/search row. Children are the individual filter controls. */
export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="filter-bar">{children}</div>;
}
