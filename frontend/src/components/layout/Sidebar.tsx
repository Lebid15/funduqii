"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BedDouble,
  Building2,
  CalendarCheck,
  CreditCard,
  Hotel,
  LayoutDashboard,
  Package,
  Settings,
  type LucideIcon,
} from "lucide-react";

import { Icon } from "@/components/ui";
import type { CurrentUser } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { initials } from "@/lib/format";

type ShellVariant = "platform" | "hotel";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
}

/** Central navigation with brand block, icon nav, and a user card. Serves both
 * the platform-owner and hotel-side shells via the `variant` prop. */
export function Sidebar({
  variant,
  user,
  hotelName,
  onNavigate,
}: {
  variant: ShellVariant;
  user: CurrentUser;
  hotelName?: string;
  onNavigate?: () => void;
}) {
  const { t } = useI18n();
  const pathname = usePathname();

  const platformItems: NavItem[] = [
    { href: "/platform", label: t.nav.dashboard, icon: LayoutDashboard, exact: true },
    { href: "/platform/hotels", label: t.nav.hotels, icon: Building2 },
    { href: "/platform/plans", label: t.nav.plans, icon: Package },
    { href: "/platform/subscriptions", label: t.nav.subscriptions, icon: CreditCard },
    { href: "/platform/settings", label: t.nav.settings, icon: Settings },
  ];
  const hotelItems: NavItem[] = [
    { href: "/hotel/reservations", label: t.reservations.nav, icon: CalendarCheck },
    { href: "/hotel/rooms", label: t.rooms.nav, icon: BedDouble },
    { href: "/hotel/settings", label: t.hotel.nav.settings, icon: Settings },
  ];

  const items = variant === "hotel" ? hotelItems : platformItems;
  const brandSubtitle =
    variant === "hotel"
      ? hotelName || t.hotel.nav.subtitle
      : t.nav.platformOwner;
  const navLabel = variant === "hotel" ? t.hotel.nav.subtitle : t.nav.platformOwner;

  function isActive(item: NavItem): boolean {
    if (item.exact) return pathname === item.href;
    return pathname === item.href || pathname.startsWith(`${item.href}/`);
  }

  return (
    <>
      <div className="app-sidebar__brand">
        <span className="brand-mark">
          <Icon icon={Hotel} size="lg" />
        </span>
        <span className="app-sidebar__brand-text">
          <span className="app-sidebar__brand-name">{t.app.name}</span>
          <span className="app-sidebar__brand-sub">{brandSubtitle}</span>
        </span>
      </div>

      <nav className="app-nav" aria-label={navLabel}>
        <span className="app-nav__section">{t.nav.mainSection}</span>
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="app-nav__link"
            aria-current={isActive(item) ? "page" : undefined}
            onClick={onNavigate}
          >
            <Icon icon={item.icon} size="md" />
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="app-sidebar__user">
        <span className="avatar avatar--md" aria-hidden="true">
          {initials(user.full_name)}
        </span>
        <span className="app-sidebar__user-meta">
          <span className="app-sidebar__user-name">{user.full_name}</span>
          <span className="app-sidebar__user-email">{user.email}</span>
        </span>
      </div>
    </>
  );
}
