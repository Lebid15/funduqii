"use client";

import Link from "next/link";
import { Hotel, Menu } from "lucide-react";

import { Badge, Icon, IconButton, type BadgeTone } from "@/components/ui";
import type { CurrentUser, HotelSubscriptionState } from "@/lib/api/types";
import { initials } from "@/lib/format";
import { useHotelProfile } from "@/lib/session/HotelProfileContext";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { LanguageSwitcher } from "./LanguageSwitcher";
import { LogoutButton } from "./LogoutButton";
import { NotificationBell } from "./NotificationBell";
import { PlatformNotificationBell } from "./PlatformNotificationBell";

interface TopbarProps {
  variant?: "platform" | "hotel";
  user: CurrentUser;
  /** SSR fallback for the hotel name so the identity paints instantly. */
  hotelName?: string;
  onMenuToggle: () => void;
}

/**
 * Central top bar (owner spec): the START side carries the HOTEL identity
 * (logo/monogram + name) and the subscription badge; the END side carries
 * the user tools (bell, language menu, user chip, solid-red logout). The
 * platform console keeps its scope label. The menu toggle is mobile-only.
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
          <>
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
                  <Icon icon={Hotel} size="md" />
                </span>
              )}
              <span className="topbar-brand__name">{hotelDisplayName}</span>
            </span>
            <SubscriptionBadge state={profile?.subscription_state ?? null} />
          </>
        ) : (
          <span className="app-topbar__title">{t.nav.platformOwner}</span>
        )}
      </div>
      <div className="app-topbar__end">
        {/* The global refresh button was removed (owner decision): the boards
            that mutate already refetch, and rooms/reservations additionally
            refetch (without remounting) when the operator returns to the tab —
            so a manual "pull latest" needs no button. */}
        {variant === "hotel" ? <NotificationBell /> : <PlatformNotificationBell />}
        <LanguageSwitcher />
        {/* Name only — no email. The avatar span is the future
            profile-picture slot; no upload exists today. */}
        <span className="topbar-user" title={user.full_name}>
          <span className="avatar avatar--lg" aria-hidden="true">
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

/** The hotel's plan/subscription pill (Phase 16 data, display only — no
 * checkout, no payment): plan and remaining days for live subscriptions,
 * clear states otherwise. Clicking it opens the subscription page — that is
 * the ONLY entry point now that the sidebar item is gone (owner decision). */
function SubscriptionBadge({
  state,
}: {
  state: HotelSubscriptionState | null;
}) {
  const { t } = useI18n();
  if (!state) return null;

  let tone: BadgeTone = "neutral";
  let label = t.subscriptionState.badgeNone;

  if (state.suspended) {
    tone = "danger";
    label = t.subscriptionState.badgeSuspended;
  } else if (state.expired) {
    tone = "danger";
    label = t.subscriptionState.badgeExpired;
  } else if (state.status === "trial") {
    tone = "info";
    label = t.subscriptionState.badgeTrial.replace(
      "{days}",
      String(state.days_left ?? 0),
    );
  } else if (state.status) {
    tone = "success";
    const plan = state.plan_name ?? "";
    label =
      state.days_left !== null
        ? t.subscriptionState.badgePaid
            .replace("{plan}", plan)
            .replace("{days}", String(state.days_left))
        : plan || t.subscriptionState.badgeNone;
  }

  return (
    <Link
      href="/hotel/subscription"
      className="topbar-plan"
      title={t.sidebar.subscription}
    >
      <Badge tone={tone}>{label}</Badge>
    </Link>
  );
}
