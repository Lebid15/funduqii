import type { SelectHTMLAttributes } from "react";

import { cx } from "@/lib/utils";

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  options: SelectOption[];
  invalid?: boolean;
  /** Optional leading placeholder option. */
  placeholder?: string;
}

/** Central select control. Options + labels are provided (translated) by caller. */
export function Select({
  options,
  invalid,
  placeholder,
  className,
  ...rest
}: SelectProps) {
  return (
    <select
      className={cx("select", className)}
      aria-invalid={invalid || undefined}
      {...rest}
    >
      {placeholder !== undefined ? (
        <option value="">{placeholder}</option>
      ) : null}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
