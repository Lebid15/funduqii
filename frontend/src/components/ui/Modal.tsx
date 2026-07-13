"use client";

import { useEffect, type ReactNode } from "react";
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

/** Central modal dialog. Closes on Escape and overlay click; locks scroll. */
export function Modal({
  open,
  onClose,
  title,
  closeLabel,
  children,
  footer,
  size = "md",
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

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
