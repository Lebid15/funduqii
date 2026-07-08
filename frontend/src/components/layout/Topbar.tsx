"use client";

import { Menu } from "lucide-react";

import { IconButton } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { LanguageSwitcher } from "./LanguageSwitcher";
import { LogoutButton } from "./LogoutButton";
import { NotificationBell } from "./NotificationBell";

interface TopbarProps {
  variant?: "platform" | "hotel";
  onMenuToggle: () => void;
}

/**
 * Central top bar: menu toggle (mobile) + scope label on the start side;
 * language switcher and logout on the end. The current user lives in the
 * sidebar user card.
 */
export function Topbar({ variant = "platform", onMenuToggle }: TopbarProps) {
  const { t } = useI18n();
  const scopeLabel =
    variant === "hotel" ? t.hotel.nav.subtitle : t.nav.platformOwner;
  return (
    <header className="app-topbar">
      <div className="app-topbar__start">
        <IconButton
          label={t.nav.openMenu}
          icon={Menu}
          className="app-sidebar__toggle"
          onClick={onMenuToggle}
        />
        <span className="app-topbar__title">{scopeLabel}</span>
      </div>
      <div className="app-topbar__end">
        {variant === "hotel" ? <NotificationBell /> : null}
        <LanguageSwitcher />
        <span className="app-topbar__divider" aria-hidden="true" />
        <LogoutButton />
      </div>
    </header>
  );
}
