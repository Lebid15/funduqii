"use client";

import { Menu } from "lucide-react";

import { IconButton } from "@/components/ui";
import type { CurrentUser } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { LanguageSwitcher } from "./LanguageSwitcher";
import { LogoutButton } from "./LogoutButton";

interface TopbarProps {
  user: CurrentUser;
  onMenuToggle: () => void;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Central top bar: menu toggle (mobile), current user, language, logout. */
export function Topbar({ user, onMenuToggle }: TopbarProps) {
  const { t } = useI18n();
  return (
    <header className="app-topbar">
      <div className="app-topbar__start">
        <IconButton
          label={t.nav.openMenu}
          icon={Menu}
          className="app-sidebar__toggle"
          onClick={onMenuToggle}
        />
        <div className="app-topbar__user">
          <span className="app-topbar__avatar" aria-hidden="true">
            {initials(user.full_name)}
          </span>
          <span className="app-topbar__user-meta">
            <span className="app-topbar__user-name">{user.full_name}</span>
            <span className="app-topbar__user-email">{user.email}</span>
          </span>
        </div>
      </div>
      <div className="app-topbar__end">
        <LanguageSwitcher />
        <LogoutButton />
      </div>
    </header>
  );
}
