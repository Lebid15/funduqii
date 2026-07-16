"use client";

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";
import { Skeleton } from "./Skeleton";

/** Tone of the summary tile's icon chip (maps to `.board-stat__icon--*`). */
export type SmartStatTone =
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "neutral";

interface SmartStatCardProps {
  /** The metric. `null` renders an empty value slot — pass a fallback (e.g. an
   * ellipsis) or `loading` when the number is not yet available. */
  value: ReactNode | null;
  label: string;
  caption?: string;
  icon: LucideIcon;
  tone: SmartStatTone;
  /** Marks the tile as the selected filter (interactive tiles get `aria-pressed`). */
  active?: boolean;
  /** When provided, the tile is a filter TOGGLE (renders a `<button>`). Omit for
   * a display-only tile (renders a `<div>` with no hover/motion). */
  onClick?: () => void;
  /** Shows a fixed-height skeleton in place of the value so the grid never reflows. */
  loading?: boolean;
  disabled?: boolean;
  /** Optional trailing tag in the head row (e.g. the reservations "Source" tag). */
  tag?: ReactNode;
  /** Extra class on the root (e.g. `board-stat--source` for the dashed source card). */
  className?: string;
}

/**
 * Central summary tile (§10) — ONE abstraction behind the stays / rooms /
 * reservations summary cards.
 *
 * - Interactive (`onClick` given): renders a `<button>` with hover + motion and
 *   `aria-pressed={active}` — a filter toggle.
 * - Display-only (no `onClick`): renders a `<div>` with NO hover/motion.
 *
 * `active` uses a distinct primary border + soft wash, kept separate from the
 * keyboard focus ring; motion honours `prefers-reduced-motion`. It emits the
 * established `.board-stat` class family so each section keeps its own grid
 * container + responsive strips (no CSS churn).
 */
export function SmartStatCard({
  value,
  label,
  caption,
  icon,
  tone,
  active = false,
  onClick,
  loading = false,
  disabled = false,
  tag,
  className,
}: SmartStatCardProps) {
  const interactive = typeof onClick === "function";

  const inner = (
    <>
      <span className="board-stat__head">
        <span className={cx("board-stat__icon", `board-stat__icon--${tone}`)}>
          <Icon icon={icon} size="md" />
        </span>
        {tag ? <span className="board-stat__tag">{tag}</span> : null}
      </span>
      <span className="board-stat__value">
        {loading ? <Skeleton width="2.75rem" height="1.6rem" /> : value}
      </span>
      <span className="board-stat__label">{label}</span>
      {caption ? <span className="board-stat__caption">{caption}</span> : null}
    </>
  );

  if (interactive) {
    return (
      <button
        type="button"
        className={cx("board-stat", active && "board-stat--active", className)}
        aria-pressed={active}
        aria-busy={loading || undefined}
        disabled={disabled}
        onClick={onClick}
      >
        {inner}
      </button>
    );
  }

  return (
    <div
      className={cx(
        "board-stat",
        "board-stat--static",
        active && "board-stat--active",
        className,
      )}
      aria-busy={loading || undefined}
    >
      {inner}
    </div>
  );
}
