import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  type ReactElement,
  type ReactNode,
} from "react";

import { cx } from "@/lib/utils";

interface FormFieldProps {
  label: string;
  htmlFor?: string;
  hint?: string;
  error?: string;
  className?: string;
  children: ReactNode;
}

/** The a11y attributes FormField injects into its single control child. */
type FieldChildProps = {
  id?: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
};

/**
 * Central labelled field wrapper. Pairs a label with any control and renders
 * hint/error text consistently. All strings come from the caller (translated).
 *
 * A11y (additive — the default visual is unchanged):
 * - Associates the label with the control: uses `htmlFor` when given, else the
 *   child's own `id`, else a generated id it injects into the child.
 * - Wires hint/error text to the control via `aria-describedby` (merged with any
 *   the child already has), sets `aria-invalid` on the child while `error` is
 *   present, and gives the error `role="alert"` so it is announced.
 */
export function FormField({
  label,
  htmlFor,
  hint,
  error,
  className,
  children,
}: FormFieldProps) {
  const autoId = useId();
  const errorId = `${autoId}-error`;
  const hintId = `${autoId}-hint`;

  // Only enhance when there is exactly one valid element child; otherwise fall
  // back to the untouched legacy behaviour (label + text, no injection).
  const onlyChild = Children.count(children) === 1 ? Children.only(children) : null;
  const childEl = isValidElement(onlyChild)
    ? (onlyChild as ReactElement<FieldChildProps>)
    : null;

  const showHint = Boolean(hint) && !error;
  // Generate an id for the control ONLY when there is a single enhanceable child
  // that has neither an htmlFor nor its own id (never override an explicit one).
  // Requiring `childEl` here keeps the generated id from being used as the
  // label's `htmlFor` when no element is actually cloned to receive it (which
  // would leave a `for` pointing at a nonexistent id).
  const injectedId =
    childEl && !htmlFor && !childEl.props.id ? autoId : undefined;
  const fieldId = htmlFor ?? childEl?.props.id ?? injectedId;

  const describedBy =
    [
      error ? errorId : null,
      showHint ? hintId : null,
      childEl?.props["aria-describedby"] ?? null,
    ]
      .filter(Boolean)
      .join(" ") || undefined;

  const enhancedChild = childEl
    ? cloneElement(childEl, {
        ...(injectedId ? { id: injectedId } : {}),
        // Only assert aria-invalid while there is an error. When there is none we
        // pass NO aria-invalid key at all, so a child that computes its own (e.g.
        // <Input invalid/>) keeps it instead of being overridden with undefined.
        ...(error ? { "aria-invalid": true } : {}),
        "aria-describedby": describedBy,
      })
    : children;

  return (
    <div className={cx("field", className)}>
      <label className="field__label" htmlFor={fieldId}>
        {label}
      </label>
      {enhancedChild}
      {showHint ? (
        <span id={hintId} className="field__hint">
          {hint}
        </span>
      ) : null}
      {error ? (
        <span id={errorId} className="field__error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}
