import type { ReactNode } from "react";

import { cx } from "@/lib/utils";

interface ContainerProps {
  children: ReactNode;
  className?: string;
}

/** Central page-width container. Part of the shared layout primitives. */
export function Container({ children, className }: ContainerProps) {
  return <div className={cx("container", className)}>{children}</div>;
}
