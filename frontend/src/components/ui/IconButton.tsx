import type { ButtonHTMLAttributes } from "react";
import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Accessible label — required, since the button shows only an icon. */
  label: string;
  /** Icon from the central lucide set. */
  icon: LucideIcon;
  size?: "sm" | "md" | "lg";
}

/** Icon-only button. `label` is applied as aria-label (never hardcoded text). */
export function IconButton({
  label,
  icon,
  size = "md",
  className,
  type = "button",
  ...rest
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cx("icon-btn", className)}
      {...rest}
    >
      <Icon icon={icon} size={size} />
    </button>
  );
}
