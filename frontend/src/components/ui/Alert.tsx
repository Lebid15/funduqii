import type { ReactNode } from "react";

import { cx } from "@/lib/utils";

interface AlertProps {
  tone?: "error" | "success" | "info";
  className?: string;
  children: ReactNode;
}

/** Central inline alert (form errors, success notices). */
export function Alert({ tone = "info", className, children }: AlertProps) {
  return (
    <div
      className={cx("alert", `alert--${tone}`, className)}
      role={tone === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}
