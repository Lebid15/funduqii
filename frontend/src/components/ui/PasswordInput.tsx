"use client";

import { useState, type InputHTMLAttributes } from "react";

import { cx } from "@/lib/utils";

interface PasswordInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  showLabel: string;
  hideLabel: string;
  invalid?: boolean;
}

/** Text input with a show/hide toggle. Toggle labels are translated by caller. */
export function PasswordInput({
  showLabel,
  hideLabel,
  invalid,
  className,
  ...rest
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="input-group">
      <input
        type={visible ? "text" : "password"}
        className={cx("input", className)}
        aria-invalid={invalid || undefined}
        {...rest}
      />
      <button
        type="button"
        className="input-group__action"
        onClick={() => setVisible((v) => !v)}
        aria-pressed={visible}
      >
        {visible ? hideLabel : showLabel}
      </button>
    </div>
  );
}
