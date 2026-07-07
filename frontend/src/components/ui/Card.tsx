import type { ReactNode } from "react";

import { cx } from "@/lib/utils";

interface CardProps {
  children: ReactNode;
  className?: string;
}

/** Central surface primitive. Part of the shared design system. */
export function Card({ children, className }: CardProps) {
  return <div className={cx("card", className)}>{children}</div>;
}
