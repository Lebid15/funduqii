import type { ReactNode } from "react";

import { cx } from "@/lib/utils";

/** Central page padding + vertical rhythm wrapper for every platform page. */
export function PageContainer({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cx("page-container", className)}>{children}</div>;
}
