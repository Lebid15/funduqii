"use client";

import { useState, type ReactNode } from "react";

import type { CurrentUser } from "@/lib/api/types";

import { ContentContainer } from "./ContentContainer";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/**
 * Central layout shell for the platform-owner console. One shell wraps every
 * platform page — pages never build their own layout. Responsive: on small
 * screens the sidebar becomes an off-canvas drawer.
 */
export function AppShell({
  user,
  children,
}: {
  user: CurrentUser;
  children: ReactNode;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const close = () => setSidebarOpen(false);

  return (
    <div className="app-shell">
      <aside className="app-sidebar" data-open={sidebarOpen}>
        <Sidebar onNavigate={close} />
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
        <Topbar user={user} onMenuToggle={() => setSidebarOpen((v) => !v)} />
        <ContentContainer>{children}</ContentContainer>
      </div>
    </div>
  );
}
