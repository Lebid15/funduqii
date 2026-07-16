"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import type { CurrentUser } from "@/lib/api/types";
import { CurrentUserProvider } from "@/lib/session/CurrentUserContext";
import { HotelProfileProvider } from "@/lib/session/HotelProfileContext";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { SubscriptionBanner } from "@/components/hotel/SubscriptionBanner";

import { ContentContainer } from "./ContentContainer";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/** Keyboard-focusable descendants used by the mobile drawer's focus trap. */
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

/**
 * Central layout shell for both consoles (platform-owner and hotel-side). One
 * shell wraps every page — pages never build their own layout. Responsive: on
 * small screens the sidebar becomes an off-canvas drawer.
 *
 * Drawer a11y: the CLOSED off-screen drawer is removed from the tab order + AT
 * via `visibility:hidden` (mobile CSS); while OPEN the drawer traps focus,
 * Escape closes it, focus returns to the trigger on close, and the backdrop
 * overlay is a labelled, keyboard-reachable close control. On desktop the
 * sidebar is a permanent panel (the hamburger is hidden), so none of this
 * applies — `sidebarOpen` only ever becomes true on mobile.
 */
export function AppShell({
  variant = "platform",
  user,
  hotelName,
  children,
}: {
  variant?: "platform" | "hotel";
  user: CurrentUser;
  hotelName?: string;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const close = () => setSidebarOpen(false);

  const drawerRef = useRef<HTMLElement>(null);
  const overlayRef = useRef<HTMLButtonElement>(null);
  // The element focused before the drawer opened (the hamburger), to restore.
  const triggerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!sidebarOpen) return;

    // The drawer + the backdrop overlay together form the focus-trap region, so
    // keyboard users can reach the overlay's "close" control without escaping.
    const focusables = (): HTMLElement[] => {
      const drawer = drawerRef.current;
      const list = drawer
        ? Array.from(
            drawer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
          ).filter((el) => el.offsetParent !== null)
        : [];
      if (overlayRef.current) list.push(overlayRef.current);
      return list;
    };

    triggerRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    focusables()[0]?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setSidebarOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const list = focusables();
      if (list.length === 0) return;
      const first = list[0];
      const last = list[list.length - 1];
      const active = document.activeElement as HTMLElement | null;
      const inside = active ? list.includes(active) : false;
      if (event.shiftKey) {
        if (active === first || !inside) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || !inside) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      const trigger = triggerRef.current;
      if (trigger && document.contains(trigger)) trigger.focus();
    };
  }, [sidebarOpen]);

  const shell = (
    <div className="app-shell">
      <aside className="app-sidebar" data-open={sidebarOpen} ref={drawerRef}>
        <Sidebar variant={variant} onNavigate={close} />
      </aside>
      <button
        type="button"
        className="sidebar-overlay"
        data-open={sidebarOpen}
        aria-label={t.nav.closeMenu}
        ref={overlayRef}
        onClick={close}
      />
      <div className="app-main">
        <Topbar
          variant={variant}
          user={user}
          hotelName={hotelName}
          onMenuToggle={() => setSidebarOpen((v) => !v)}
        />
        <ContentContainer>
          <CurrentUserProvider user={user}>
            {variant === "hotel" ? <SubscriptionBanner /> : null}
            {children}
          </CurrentUserProvider>
        </ContentContainer>
      </div>
    </div>
  );

  // The hotel shell shares ONE profile load (sidebar brand slot + the
  // subscription banner); the platform shell has no hotel profile.
  return variant === "hotel" ? (
    <HotelProfileProvider>{shell}</HotelProfileProvider>
  ) : (
    shell
  );
}
