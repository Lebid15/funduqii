"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { MoreHorizontal } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Button, Icon, type BadgeTone } from "@/components/ui";

/** A secondary action folded into the card's "More" menu. */
export interface OperationMenuItem {
  key: string;
  label: string;
  icon?: LucideIcon;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
}

/** The single, state-computed primary action rendered as a full button. */
export interface OperationPrimaryAction {
  label: string;
  icon?: LucideIcon;
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: "primary" | "secondary" | "danger";
}

/** One labelled meta field in the card's compact fact row. */
export interface OperationFact {
  key: string;
  label: string;
  value: ReactNode;
  icon?: LucideIcon;
}

const ACCENT_VAR: Record<BadgeTone, string> = {
  success: "var(--color-success)",
  warning: "var(--color-warning)",
  danger: "var(--color-danger)",
  info: "var(--color-info)",
  primary: "var(--color-primary)",
  vip: "var(--color-vip)",
  neutral: "var(--color-border-strong)",
};

/**
 * Accessible "More" menu (menu-button pattern, WAI-ARIA APG): a trigger with
 * `aria-haspopup="menu"` / `aria-expanded`, a `role="menu"` popover with
 * `role="menuitem"` children, roving focus (Up/Down/Home/End), Escape-to-close
 * with focus return, and outside-click dismissal.
 */
function MoreMenu({
  items,
  label,
}: {
  items: OperationMenuItem[];
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = useId();

  // Dismiss on outside pointer + focus the first item when opening.
  useEffect(() => {
    if (!open) return;
    itemRefs.current[0]?.focus();
    const onPointer = (event: PointerEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  function close(focusTrigger = true) {
    setOpen(false);
    if (focusTrigger) {
      wrapRef.current
        ?.querySelector<HTMLButtonElement>('[aria-haspopup="menu"]')
        ?.focus();
    }
  }

  function moveFocus(nextIndex: number) {
    const count = items.length;
    const clamped = ((nextIndex % count) + count) % count;
    itemRefs.current[clamped]?.focus();
  }

  function onMenuKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const current = itemRefs.current.findIndex(
      (element) => element === document.activeElement,
    );
    switch (event.key) {
      case "Escape":
        event.preventDefault();
        close();
        break;
      case "ArrowDown":
        event.preventDefault();
        moveFocus(current + 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        moveFocus(current - 1);
        break;
      case "Home":
        event.preventDefault();
        moveFocus(0);
        break;
      case "End":
        event.preventDefault();
        moveFocus(items.length - 1);
        break;
      case "Tab":
        // Leaving the menu returns focus to the flow; close without stealing it.
        close(false);
        break;
      default:
        break;
    }
  }

  return (
    <div className={`op-menu${open ? " op-menu--open" : ""}`} ref={wrapRef}>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        icon={MoreHorizontal}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        {label}
      </Button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label={label}
          className="op-menu__panel"
          onKeyDown={onMenuKeyDown}
        >
          {items.map((item, index) => (
            <button
              key={item.key}
              ref={(element) => {
                itemRefs.current[index] = element;
              }}
              type="button"
              role="menuitem"
              tabIndex={-1}
              disabled={item.disabled}
              className={`op-menu__item${item.danger ? " op-menu__item--danger" : ""}`}
              onClick={() => {
                close();
                item.onSelect();
              }}
            >
              {item.icon ? <Icon icon={item.icon} size="sm" /> : null}
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * One operations record as a calm, equal-height card (WP10 §3). Shows the
 * record number + title, status/priority (and any extra) badges, a compact
 * fact row, an optional short note, then EXACTLY one primary action plus a
 * "More" menu for the rest — never a wall of buttons. Purely presentational and
 * props-driven; all state/permission logic lives in the calling tab.
 *
 * Identifiers (record number) are isolated LTR via `<bdi>` so they read
 * correctly inside an RTL layout.
 */
export function OperationCard({
  accent = "neutral",
  number,
  title,
  badges,
  facts,
  note,
  primary,
  menu = [],
  moreLabel,
  ariaLabel,
}: {
  accent?: BadgeTone;
  number: string;
  title: ReactNode;
  badges: ReactNode;
  facts: OperationFact[];
  note?: string | null;
  primary?: OperationPrimaryAction | null;
  menu?: OperationMenuItem[];
  moreLabel: string;
  ariaLabel: string;
}) {
  const hasActions = Boolean(primary) || menu.length > 0;

  return (
    <article
      className="op-card"
      aria-label={ariaLabel}
      style={{ "--op-accent": ACCENT_VAR[accent] } as CSSProperties}
    >
      <div className="op-card__header">
        <div className="op-card__badges">{badges}</div>
        <div className="op-card__idrow">
          <span className="op-card__title">{title}</span>
          <span className="op-card__number">
            <bdi dir="ltr">{number}</bdi>
          </span>
        </div>
      </div>

      {facts.length > 0 ? (
        <dl className="op-card__facts">
          {facts.map((fact) => (
            <div className="op-card__fact" key={fact.key}>
              <dt>
                {fact.icon ? <Icon icon={fact.icon} size="sm" /> : null}
                {fact.label}
              </dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {/* A short description clamped to two lines (op-card__note); the full text
          stays available via the native title tooltip so nothing is lost. */}
      {note ? (
        <p className="op-card__note" title={note}>
          {note}
        </p>
      ) : null}

      {hasActions ? (
        <div className="op-card__actions">
          {primary ? (
            <Button
              className="op-card__primary"
              size="sm"
              variant={primary.variant ?? "primary"}
              icon={primary.icon}
              loading={primary.loading}
              disabled={primary.disabled}
              onClick={primary.onClick}
            >
              {primary.label}
            </Button>
          ) : null}
          {menu.length > 0 ? (
            <MoreMenu items={menu} label={moreLabel} />
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
