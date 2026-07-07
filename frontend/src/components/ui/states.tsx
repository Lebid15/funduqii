import type { ReactNode } from "react";
import { CircleAlert, Inbox, type LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Button } from "./Button";
import { Icon } from "./Icon";

/** Centered loading indicator. `label` is translated by the caller. */
export function LoadingState({ label }: { label: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span className="state__hint">{label}</span>
    </div>
  );
}

/** Error panel with an icon and an optional retry action. */
export function ErrorState({
  title,
  message,
  retryLabel,
  onRetry,
}: {
  title: string;
  message?: string;
  retryLabel?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state" role="alert">
      <span className="state__icon state__icon--error">
        <Icon icon={CircleAlert} size="lg" />
      </span>
      <span className="state__title">{title}</span>
      {message ? <span className="state__hint">{message}</span> : null}
      {onRetry && retryLabel ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          {retryLabel}
        </Button>
      ) : null}
    </div>
  );
}

/** Empty placeholder for lists with no rows. */
export function EmptyState({
  title,
  hint,
  icon = Inbox,
  action,
  className,
}: {
  title: string;
  hint?: string;
  icon?: LucideIcon;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("state empty-state", className)}>
      <span className="state__icon">
        <Icon icon={icon} size="lg" />
      </span>
      <span className="state__title">{title}</span>
      {hint ? <span className="state__hint">{hint}</span> : null}
      {action}
    </div>
  );
}
