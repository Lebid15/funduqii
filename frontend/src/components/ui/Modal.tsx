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
}

/**
 * Module-level stack of the ids of every currently-open Modal, in open order.
 * Only the LAST-opened (topmost) modal reacts to the global Escape key, so
 * pressing Escape while a nested modal is open (e.g. a print dialog opened over
 * the check-out dialog) closes ONLY that nested modal — never the parent
 * underneath it, which would otherwise discard the parent's unsaved form state.
 * Backdrop clicks are already scoped to each overlay element (the click only
 * lands on the topmost overlay), so they need no coordination here.
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

/** Central modal dialog. Closes on Escape (topmost only) and overlay click;
 * locks scroll. */
export function Modal({
  open,
  onClose,
  title,
  closeLabel,
  children,
  footer,
  size = "md",
}: ModalProps) {
  const modalId = useId();
  // Always call the CURRENT onClose from the key handler via a ref, so the
  // registration effect below does not re-run (and re-order the stack) just
  // because an inline `onClose` prop changed identity between renders.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    openModalStack.push(modalId);
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      // Only the topmost dialog responds — otherwise every open modal would
      // close at once and a parent dialog would lose its entered data.
      if (openModalStack[openModalStack.length - 1] !== modalId) return;
      onCloseRef.current();
    };
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      const i = openModalStack.lastIndexOf(modalId);
      if (i !== -1) openModalStack.splice(i, 1);
      document.body.style.overflow = previousOverflow;
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
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className={size === "md" ? "modal" : `modal modal--${size}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal__header">
          <h2 className="modal__title">{title}</h2>
          <IconButton label={closeLabel} icon={X} onClick={onClose} />
        </div>
        <div className="modal__body">{children}</div>
        {footer ? <div className="modal__footer">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}
