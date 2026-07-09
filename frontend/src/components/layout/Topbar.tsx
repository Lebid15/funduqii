"use client";

import { Hotel, Menu } from "lucide-react";

import { Icon, IconButton } from "@/components/ui";
import type { CurrentUser } from "@/lib/api/types";
import { initials } from "@/lib/format";
import { useHotelProfile } from "@/lib/session/HotelProfileContext";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { LanguageSwitcher } from "./LanguageSwitcher";
import { LogoutButton } from "./LogoutButton";
import { NotificationBell } from "./NotificationBell";

interface TopbarProps {
  variant?: "platform" | "hotel";
  user: CurrentUser;
  /** SSR fallback for the hotel name so the identity paints instantly. */
  hotelName?: string;
  onMenuToggle: () => void;
}

/**
 * Central top bar (owner correction): the START side carries the HOTEL
 * identity (uploaded logo or monogram + hotel name) in the hotel console —
 * the platform console keeps its scope label. The END side carries the
 * user tools: bell, language menu, user chip and the red logout.
 */
export function Topbar({
  variant = "platform",
  user,
  hotelName,
  onMenuToggle,
}: TopbarProps) {
  const { t } = useI18n();
  const profile = useHotelProfile();

  const hotelDisplayName =
    profile?.display_name || profile?.hotel.name || hotelName || "";
  const logoUrl = profile?.logo?.url ?? null;

  return (
    <header className="app-topbar">
      <div className="app-topbar__start">
        <IconButton
          label={t.nav.openMenu}
          icon={Menu}
          className="app-sidebar__toggle"
          onClick={onMenuToggle}
        />
        {variant === "hotel" ? (
          <span className="topbar-brand" title={hotelDisplayName}>
            {logoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element -- hotel-uploaded media
              <img
                className="topbar-brand__logo"
                src={logoUrl}
                alt={hotelDisplayName}
              />
            ) : hotelDisplayName ? (
              <span className="topbar-brand__mark" aria-hidden="true">
                {initials(hotelDisplayName)}
              </span>
            ) : (
              <span className="topbar-brand__mark" aria-hidden="true">
                <Icon icon={Hotel} size="sm" />
              </span>
            )}
            <span className="topbar-brand__name">{hotelDisplayName}</span>
          </span>
        ) : (
          <span className="app-topbar__title">{t.nav.platformOwner}</span>
        )}
      </div>
      <div className="app-topbar__end">
        {variant === "hotel" ? <NotificationBell /> : null}
        <LanguageSwitcher />
        {/* Name only — no email. The avatar span is the future
            profile-picture slot; no upload exists today. */}
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
