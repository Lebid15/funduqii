import type { ReactNode } from "react";

import { cx } from "@/lib/utils";

export type BadgeTone =
  | "neutral"
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "vip"
  | "reserved"
  | "inhouse"
  | "blocked";

interface BadgeProps {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
}

/** Central status pill. Text is passed in (already translated by the caller). */
export function Badge({ tone = "neutral", className, children }: BadgeProps) {
  return (
    <span className={cx("badge", `badge--${tone}`, className)}>{children}</span>
  );
}
