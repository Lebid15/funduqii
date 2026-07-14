import type { ButtonHTMLAttributes } from "react";
import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";

export type ActionIconButtonVariant = "ghost" | "subtle" | "solid";
export type ActionIconButtonSize = "sm" | "md" | "lg";

interface ActionIconButtonBaseProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> {
  /** Icon from the central lucide set (this is an icon-only button). */
  icon: LucideIcon;
  size?: ActionIconButtonSize;
  variant?: ActionIconButtonVariant;
  /**
   * Shows a spinner AND blocks activation (native `disabled` + guarded
   * `onClick`) so a slow action can't be double-fired.
   */
  loading?: boolean;
}

/**
 * The button is icon-only, so it MUST expose an accessible name. Enforced at the
 * type level: provide `label` (preferred — the translated aria-label) and/or
 * `tooltip`. When only `tooltip` is given it also becomes the aria-label, so the
 * control is never tooltip-only (a `title` alone is not announced reliably).
 */
type ActionIconButtonProps = ActionIconButtonBaseProps &
  (
    | { label: string; tooltip?: string }
    | { label?: string; tooltip: string }
  );

const ICON_SIZE: Record<ActionIconButtonSize, "sm" | "md" | "lg"> = {
  sm: "sm",
  md: "md",
  lg: "lg",
};

/**
 * Central icon-only action button — the richer sibling of `IconButton`
 * (variants, sizes, tooltip, loading, blocked double-clicks, visible focus).
 * `label`/`tooltip` supply the aria-label; text is always translated by the
 * caller, never hardcoded here.
 */
export function ActionIconButton({
  icon,
  label,
  tooltip,
  size = "md",
  variant = "ghost",
  loading = false,
  className,
  type = "button",
  disabled,
  onClick,
  ...rest
}: ActionIconButtonProps) {
  const accessibleName = label ?? tooltip;
  return (
    <button
      type={type}
      aria-label={accessibleName}
      title={tooltip ?? label}
      className={cx(
        "action-icon-btn",
        `action-icon-btn--${variant}`,
        `action-icon-btn--${size}`,
        className,
      )}
      disabled={disabled || loading}
      data-loading={loading || undefined}
      aria-busy={loading || undefined}
      onClick={loading ? undefined : onClick}
      {...rest}
    >
      {loading ? (
        <span className="action-icon-btn__spinner" aria-hidden="true" />
      ) : (
        <Icon icon={icon} size={ICON_SIZE[size]} />
      )}
    </button>
  );
}
