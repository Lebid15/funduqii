import type { InputHTMLAttributes } from "react";

import { cx } from "@/lib/utils";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

/** Central text input. */
export function Input({ invalid, className, ...rest }: InputProps) {
  return (
    <input
      className={cx("input", className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  );
}
