"use client";

import { useState, type ReactNode } from "react";

import type { CurrentUser } from "@/lib/api/types";
import { CurrentUserProvider } from "@/lib/session/CurrentUserContext";
import { HotelProfileProvider } from "@/lib/session/HotelProfileContext";
import { SubscriptionBanner } from "@/components/hotel/SubscriptionBanner";

import { ContentContainer } from "./ContentContainer";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/**
 * Central layout shell for both consoles (platform-owner and hotel-side). One
 * shell wraps every page — pages never build their own layout. Responsive: on
 * small screens the sidebar becomes an off-canvas drawer.
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
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const close = () => setSidebarOpen(false);

  const shell = (
    <div className="app-shell">
      <aside className="app-sidebar" data-open={sidebarOpen}>
        <Sidebar
          variant={variant}
          user={user}
          hotelName={hotelName}
          onNavigate={close}
        />
      </aside>
      <button
        type="button"
        className="sidebar-overlay"
        data-open={sidebarOpen}
        aria-hidden={!sidebarOpen}
        tabIndex={-1}
        onClick={close}
      />
      <div className="app-main">
        <Topbar variant={variant} onMenuToggle={() => setSidebarOpen((v) => !v)} />
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
