import type { TextareaHTMLAttributes } from "react";

import { cx } from "@/lib/utils";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

/** Central multi-line text control. */
export function Textarea({ invalid, className, ...rest }: TextareaProps) {
  return (
    <textarea
      className={cx("textarea", className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  );
}
