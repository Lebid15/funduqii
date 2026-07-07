import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";

type Variant = "primary" | "secondary" | "danger" | "ghost";

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
