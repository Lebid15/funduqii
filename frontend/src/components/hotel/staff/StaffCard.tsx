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
import type {
  OperationFact,
  OperationMenuItem,
} from "@/components/hotel/operations/OperationCard";

/** A visible, always-affordance action button on the card (common ops). */
export interface StaffCardAction {
  key: string;
  label: string;
  icon?: LucideIcon;
  onClick: () => void;
  variant?: "primary" | "secondary" | "danger";
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
 * Accessible "More" menu (menu-button pattern, WAI-ARIA APG) — the same pattern
 * OperationCard uses in operations/guest-folio, re-implemented locally so the
 * staff card can pair it with several visible common-action buttons (which the
 * single-primary OperationCard API cannot express). Trigger carries
 * `aria-haspopup="menu"` / `aria-expanded`; the popover is `role="menu"` with
 * `role="menuitem"` children, roving focus (Up/Down/Home/End), Escape-to-close
 * with focus return, and outside-click dismissal.
 */
function CardMenu({
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
 * One staff member as an equal-height card. Reuses the shared `.op-card`
 * visual shell but, unlike OperationCard, surfaces SEVERAL common actions as
 * visible affordances (Edit / Manage permissions / Activate–Deactivate / Reset)
 * and folds the rare, sensitive ops (Promote / Demote / Change email / Delete)
 * into the accessible "More" menu. Purely presentational — every gate and
 * mutation lives in the calling panel.
 */
export function StaffCard({
  accent = "neutral",
  number,
  title,
  badges,
  facts,
  actions,
  menu = [],
  moreLabel,
  ariaLabel,
}: {
  accent?: BadgeTone;
  number?: string;
  title: ReactNode;
  badges: ReactNode;
  facts: OperationFact[];
  actions: StaffCardAction[];
  menu?: OperationMenuItem[];
  moreLabel: string;
  ariaLabel: string;
}) {
  const hasActions = actions.length > 0 || menu.length > 0;

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
          {number ? (
            <span className="op-card__number">
              <bdi dir="ltr">{number}</bdi>
            </span>
          ) : null}
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

      {hasActions ? (
        <div className="op-card__actions">
          {actions.map((action) => (
            <Button
              key={action.key}
              size="sm"
              variant={action.variant ?? "secondary"}
              icon={action.icon}
              onClick={action.onClick}
            >
              {action.label}
            </Button>
          ))}
          {menu.length > 0 ? <CardMenu items={menu} label={moreLabel} /> : null}
        </div>
      ) : null}
    </article>
  );
}
