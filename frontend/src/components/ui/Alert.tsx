import type { ReactNode } from "react";
import { CircleAlert, CircleCheck, Info } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";

type AlertTone = "error" | "success" | "info";

const TONE_ICON = {
  error: CircleAlert,
  success: CircleCheck,
  info: Info,
} as const;

interface AlertProps {
  tone?: AlertTone;
  className?: string;
  children: ReactNode;
}

/** Central inline alert (form errors, success notices) with a leading icon. */
export function Alert({ tone = "info", className, children }: AlertProps) {
  return (
    <div
      className={cx("alert", `alert--${tone}`, className)}
      role={tone === "error" ? "alert" : "status"}
    >
      <Icon icon={TONE_ICON[tone]} size="sm" />
      <span>{children}</span>
    </div>
  );
}
