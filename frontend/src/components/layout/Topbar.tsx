"use client";

import { Menu } from "lucide-react";

import { IconButton } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { LanguageSwitcher } from "./LanguageSwitcher";
import { LogoutButton } from "./LogoutButton";

interface TopbarProps {
  onMenuToggle: () => void;
}

/**
 * Central top bar: menu toggle (mobile) + scope label on the start side;
 * language switcher and logout on the end. The current user lives in the
 * sidebar user card.
 */
export function Topbar({ onMenuToggle }: TopbarProps) {
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
        <span className="app-topbar__title">{t.nav.platformOwner}</span>
      </div>
      <div className="app-topbar__end">
        <LanguageSwitcher />
        <span className="app-topbar__divider" aria-hidden="true" />
        <LogoutButton />
      </div>
    </header>
  );
}
