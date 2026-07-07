import type { ReactNode } from "react";

import { cx } from "@/lib/utils";

/** Central max-width wrapper for main content areas. */
export function ContentContainer({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cx("content-container", className)}>{children}</div>;
}
