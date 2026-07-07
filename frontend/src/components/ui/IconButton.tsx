import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cx } from "@/lib/utils";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Accessible label — required, since the button shows only an icon. */
  label: string;
  children: ReactNode;
}

/** Icon-only button. `label` is applied as aria-label (never hardcoded text). */
export function IconButton({
  label,
  className,
  type = "button",
  children,
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
      {children}
    </button>
  );
}
