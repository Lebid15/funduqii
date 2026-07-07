"use client";

import { IconButton } from "@/components/ui";
import type { CurrentUser } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { LanguageSwitcher } from "./LanguageSwitcher";
import { LogoutButton } from "./LogoutButton";

interface TopbarProps {
  user: CurrentUser;
  onMenuToggle: () => void;
}

/** Central top bar: menu toggle (mobile), current user, language, logout. */
export function Topbar({ user, onMenuToggle }: TopbarProps) {
  const { t } = useI18n();
  return (
    <header className="app-topbar">
      <div className="app-topbar__start">
        <IconButton
          label={t.nav.openMenu}
          className="app-sidebar__toggle"
          onClick={onMenuToggle}
        >
          ☰
        </IconButton>
        <div className="app-topbar__user">
          <span className="app-topbar__user-name">{user.full_name}</span>
          <span className="app-topbar__user-email">{user.email}</span>
        </div>
      </div>
      <div className="app-topbar__end">
        <LanguageSwitcher />
        <LogoutButton />
      </div>
    </header>
  );
}
