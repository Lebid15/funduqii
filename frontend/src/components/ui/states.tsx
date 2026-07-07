import type { ReactNode } from "react";

import { cx } from "@/lib/utils";

import { Button } from "./Button";

/** Centered loading indicator. `label` is translated by the caller. */
export function LoadingState({ label }: { label: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span className="state__hint">{label}</span>
    </div>
  );
}

/** Error panel with an optional retry action. */
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
  action,
  className,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("state empty-state", className)}>
      <span className="state__title">{title}</span>
      {hint ? <span className="state__hint">{hint}</span> : null}
      {action}
    </div>
  );
}
