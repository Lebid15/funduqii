"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

import { IconButton } from "./IconButton";

/** Width preset for the dialog. `md` is the historical default and renders
 * EXACTLY the base `.modal` width — larger sizes are opt-in via CSS modifiers. */
type ModalSize = "md" | "lg" | "xl" | "full";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  closeLabel: string;
  children: ReactNode;
  footer?: ReactNode;
  /** Optional width preset. Defaults to `md` (unchanged legacy width). */
  size?: ModalSize;
  /**
   * When set, the dialog is NON-dismissible via Escape or a backdrop click
   * (e.g. while a save is in flight). The explicit close button still works.
   * Default `false` = the historical dismissible behaviour, unchanged.
   */
  preventClose?: boolean;
}

/** Elements that can receive keyboard focus inside the dialog (focus trap). */
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

/** Visible, focusable descendants in DOM order. */
function getFocusable(root: HTMLElement | null): HTMLElement[] {
  if (!root) return [];
  return Array.from(
    root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((el) => el.offsetParent !== null || el === document.activeElement);
}

/**
 * Module-level stack of the ids of every currently-open Modal, in open order.
 * Only the LAST-opened (topmost) modal reacts to the global Escape key AND owns
 * the focus trap, so a nested dialog (e.g. a print dialog over the check-out
 * dialog) is what Escape/Tab act on — never the parent underneath it, which
 * would otherwise discard the parent's unsaved form state. Backdrop clicks are
 * already scoped to each overlay element (the click only lands on the topmost
 * overlay), so they need no coordination here.
 *
 * ASSUMPTION — sequential open: the "last pushed = topmost" rule relies on modals
 * opening one after another (a nested dialog mounts while its parent is already
 * open). If two modals were ever mounted already-open in the SAME render commit,
 * React runs the child's effect before the parent's, so the parent would push
 * LAST and be mistaken for the topmost dialog. That is a narrow edge case that
 * does not occur in the current sequential-open flows, so no timestamp/order
 * reconciliation is done here.
 */
const openModalStack: string[] = [];

/** Central modal dialog. Traps focus (topmost only), closes on Escape (topmost)
 * and overlay click unless `preventClose`, restores focus to the trigger, and
 * locks scroll. */
export function Modal({
  open,
  onClose,
  title,
  closeLabel,
  children,
  footer,
  size = "md",
  preventClose = false,
}: ModalProps) {
  const modalId = useId();
  const titleId = `${modalId}-title`;
  // Call the CURRENT onClose / preventClose from the key handler via refs, so the
  // registration effect below does not re-run (and re-order the stack) just
  // because an inline prop changed identity between renders.
  const onCloseRef = useRef(onClose);
  const preventCloseRef = useRef(preventClose);
  const dialogRef = useRef<HTMLDivElement>(null);
  // The element focused right before the dialog opened, to restore on close.
  const triggerRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    onCloseRef.current = onClose;
  });
  useEffect(() => {
    preventCloseRef.current = preventClose;
  });

  useEffect(() => {
    if (!open) return;
    openModalStack.push(modalId);

    // Remember what to restore focus to, then move focus into the dialog (the
    // container itself, so the accessible name — the title — is announced).
    triggerRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const dialog = dialogRef.current;
    dialog?.focus();

    const isTopmost = () => openModalStack[openModalStack.length - 1] === modalId;

    const onKey = (event: KeyboardEvent) => {
      // Only the topmost dialog responds — otherwise every open modal would
      // react at once and a parent dialog would lose its entered data.
      if (!isTopmost()) return;

      if (event.key === "Escape") {
        if (preventCloseRef.current) {
          event.preventDefault();
          return;
        }
        onCloseRef.current();
        return;
      }

      if (event.key === "Tab") {
        // Focus TRAP: cycle Tab / Shift+Tab within this dialog.
        const focusables = getFocusable(dialog);
        if (focusables.length === 0) {
          event.preventDefault();
          dialog?.focus();
          return;
        }
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        // "Inside" = membership in the trap list, NOT DOM containment. The dialog
        // CONTAINER itself (tabIndex=-1, the initial focus target) is contained by
        // the dialog but is NOT a focusable — so a containment check leaves the
        // first Shift+Tab (before any inner Tab) with neither branch matching and
        // it escapes to the background. Membership makes the container count as
        // "outside", so Shift+Tab wraps to `last` and Tab wraps to `first`. This
        // mirrors the AppShell drawer trap.
        const inside = active ? focusables.includes(active) : false;
        if (event.shiftKey) {
          if (active === first || !inside) {
            event.preventDefault();
            last.focus();
          }
        } else if (active === last || !inside) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      const i = openModalStack.lastIndexOf(modalId);
      if (i !== -1) openModalStack.splice(i, 1);
      document.body.style.overflow = previousOverflow;
      // Return focus to the element that opened the dialog (if still mounted).
      const trigger = triggerRef.current;
      if (trigger && document.contains(trigger)) trigger.focus();
    };
  }, [open, modalId]);

  if (!open || typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div
      className="modal-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (preventClose) return;
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className={size === "md" ? "modal" : `modal modal--${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-label={title ? undefined : closeLabel}
        tabIndex={-1}
      >
        <div className="modal__header">
          <h2 className="modal__title" id={titleId}>
            {title}
          </h2>
          <IconButton label={closeLabel} icon={X} onClick={onClose} />
        </div>
        <div className="modal__body">{children}</div>
        {footer ? <div className="modal__footer">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}
