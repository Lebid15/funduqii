import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";

export type BadgeTone =
  | "neutral"
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "info";

/**
 * Visual weight of the badge:
 * - `soft`    — the historical default (tinted background + tone text). Renders
 *               EXACTLY as before; passing this is identical to omitting it.
 * - `filled`  — strong solid background + white text/icon (high emphasis, WCAG
 *               AA on the strong feedback tokens).
 * - `outline` — surface background + tone border and text (low emphasis).
 */
export type BadgeVariant = "soft" | "filled" | "outline";

interface BadgeProps {
  tone?: BadgeTone;
  /** Visual weight. Omit (or `"soft"`) for the unchanged default look. */
  variant?: BadgeVariant;
  /** Optional leading icon (central lucide set) so meaning is never colour-only. */
  icon?: LucideIcon;
  className?: string;
  children: ReactNode;
}

/** Central status pill. Text is passed in (already translated by the caller). */
export function Badge({
  tone = "neutral",
  variant = "soft",
  icon,
  className,
  children,
}: BadgeProps) {
  return (
    <span
      className={cx(
        "badge",
        `badge--${tone}`,
        variant !== "soft" && `badge--${variant}`,
        className,
      )}
    >
      {icon ? <Icon icon={icon} size="sm" className="badge__icon" /> : null}
      {children}
    </span>
  );
}
