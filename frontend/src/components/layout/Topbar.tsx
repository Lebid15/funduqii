"use client";

import { Menu } from "lucide-react";

import { IconButton } from "@/components/ui";
import type { CurrentUser } from "@/lib/api/types";
import { initials } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { LanguageSwitcher } from "./LanguageSwitcher";
import { LogoutButton } from "./LogoutButton";
import { NotificationBell } from "./NotificationBell";

interface TopbarProps {
  variant?: "platform" | "hotel";
  user: CurrentUser;
  onMenuToggle: () => void;
}

/**
 * Central top bar: menu toggle (mobile) + scope label on the start side;
 * bell, language menu, the USER CHIP (avatar + name — moved here from the
 * sidebar by owner decision) and the logout action on the end.
 */
export function Topbar({ variant = "platform", user, onMenuToggle }: TopbarProps) {
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
        {/* Name only — no email (owner decision). The avatar span is the
            future profile-picture slot: swap the initials for an <img> when
            profile photos arrive; no upload exists today. */}
        <span className="topbar-user" title={user.full_name}>
          <span className="avatar avatar--sm" aria-hidden="true">
            {initials(user.full_name)}
          </span>
          <span className="topbar-user__name">{user.full_name}</span>
        </span>
        <span className="app-topbar__divider" aria-hidden="true" />
        <LogoutButton />
      </div>
    </header>
  );
}
