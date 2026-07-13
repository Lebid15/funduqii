"use client";

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import type { LucideIcon } from "lucide-react";

import { Icon } from "@/components/ui";

import { MoreActionsIcon } from "./reservationShared";

export interface CardMenuItem {
  key: string;
  label: string;
  icon: LucideIcon;
  danger?: boolean;
  onSelect: () => void;
}

/** A quiet per-card overflow menu (owner UX): keeps the secondary actions off
 * the primary row so the card stays uncluttered. Self-contained a11y — opens
 * on click / ArrowDown, closes on outside click / Escape / Tab, roving focus
 * with the arrow keys, and returns focus to the trigger on close. Renders
 * nothing when it has no items. */
export function CardMenu({ label, items }: { label: string; items: CardMenuItem[] }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (open) itemRefs.current[0]?.focus();
  }, [open]);

  if (items.length === 0) return null;

  function focusItem(index: number) {
    const count = items.length;
    const next = ((index % count) + count) % count;
    itemRefs.current[next]?.focus();
  }

  function closeAndReturnFocus() {
    setOpen(false);
    buttonRef.current?.focus();
  }

  function onListKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const current = itemRefs.current.findIndex((el) => el === document.activeElement);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusItem(current + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusItem(current - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusItem(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusItem(items.length - 1);
    } else if (event.key === "Escape" || event.key === "Tab") {
      closeAndReturnFocus();
    }
  }

  return (
    <div className="card-menu" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="btn btn--ghost btn--sm card-menu__button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <Icon icon={MoreActionsIcon} size="sm" />
      </button>
      {open ? (
        <div
          className="card-menu__list"
          role="menu"
          aria-label={label}
          onKeyDown={onListKeyDown}
        >
          {items.map((item, index) => (
            <button
              key={item.key}
              ref={(el) => {
                itemRefs.current[index] = el;
              }}
              type="button"
              role="menuitem"
              className={item.danger ? "card-menu__item card-menu__item--danger" : "card-menu__item"}
              onClick={() => {
                item.onSelect();
                closeAndReturnFocus();
              }}
            >
              <Icon icon={item.icon} size="sm" />
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
