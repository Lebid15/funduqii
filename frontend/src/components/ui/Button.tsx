import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";

type Variant =
  | "primary"
  | "secondary"
  | "success"
  | "info"
  | "indigo"
  | "warning"
  | "danger"
  | "dangerSoft"
  | "ghost";

/** Purpose-driven icon micro-interaction, played on hover only (UI polish
 * round). Purely cosmetic — respects prefers-reduced-motion. */
export type ButtonAnim =
  | "add"
  | "open"
  | "back"
  | "edit"
  | "save"
  | "checkin"
  | "checkout"
  | "move"
  | "extend"
  | "shorten"
  | "delete"
  | "block"
  | "vip";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "md" | "sm";
  block?: boolean;
  /** Optional leading icon (central lucide set). */
  icon?: LucideIcon;
  /** Optional trailing icon. */
  iconEnd?: LucideIcon;
  /** Shows a spinner and disables the button. */
  loading?: boolean;
  /** Optional purpose-matched icon hover animation. */
  anim?: ButtonAnim;
  children: ReactNode;
}

/** Central button primitive. All buttons in the app use this. */
export function Button({
  variant = "primary",
  size = "md",
  block = false,
  icon,
  iconEnd,
  loading = false,
  anim,
  className,
  type = "button",
  disabled,
  children,
  ...rest
}: ButtonProps) {
  const iconSize = size === "sm" ? "sm" : "md";
  return (
    <button
      type={type}
      className={cx(
        "btn",
        `btn--${variant}`,
        size === "sm" && "btn--sm",
        block && "btn--block",
        className,
      )}
      disabled={disabled || loading}
      data-loading={loading || undefined}
      data-anim={anim}
      {...rest}
    >
      {loading ? (
        <span className="btn__spinner" aria-hidden="true" />
      ) : icon ? (
        <Icon icon={icon} size={iconSize} />
      ) : null}
      {children}
      {iconEnd && !loading ? <Icon icon={iconEnd} size={iconSize} /> : null}
    </button>
  );
}
