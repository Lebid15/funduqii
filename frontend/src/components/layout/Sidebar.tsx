"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  BedDouble,
  Bell,
  Building2,
  CalendarCheck,
  ClipboardList,
  Clock,
  ConciergeBell,
  CreditCard,
  Globe,
  Hotel,
  LayoutDashboard,
  Package,
  Receipt,
  Settings,
  UserCog,
  Users,
  UtensilsCrossed,
  type LucideIcon,
} from "lucide-react";

import { Icon } from "@/components/ui";
import type { CurrentUser } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { initials } from "@/lib/format";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { HOTEL_ROUTE_ACCESS } from "@/lib/session/hotelRouteAccess";

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
  const access = useHotelAccess();

  const platformItems: NavItem[] = [
    { href: "/platform", label: t.nav.dashboard, icon: LayoutDashboard, exact: true },
    { href: "/platform/hotels", label: t.nav.hotels, icon: Building2 },
    { href: "/platform/plans", label: t.nav.plans, icon: Package },
    { href: "/platform/subscriptions", label: t.nav.subscriptions, icon: CreditCard },
    { href: "/platform/public-site", label: t.nav.publicSite, icon: Globe },
    { href: "/platform/settings", label: t.nav.settings, icon: Settings },
  ];
  const allHotelItems: NavItem[] = [
    { href: "/hotel/front-desk", label: t.frontDesk.nav, icon: ConciergeBell },
    { href: "/hotel/reservations", label: t.reservations.nav, icon: CalendarCheck },
    { href: "/hotel/guests", label: t.guests.nav, icon: Users },
    { href: "/hotel/finance", label: t.finance.nav, icon: Receipt },
    { href: "/hotel/services", label: t.services.nav, icon: UtensilsCrossed },
    { href: "/hotel/operations", label: t.operations.nav, icon: ClipboardList },
    { href: "/hotel/staff", label: t.staff.nav, icon: UserCog },
    { href: "/hotel/shifts", label: t.shifts.nav, icon: Clock },
    { href: "/hotel/reports", label: t.reports.nav, icon: BarChart3 },
    { href: "/hotel/notifications", label: t.notifications.nav, icon: Bell },
    { href: "/hotel/rooms", label: t.rooms.nav, icon: BedDouble },
    { href: "/hotel/settings", label: t.hotel.nav.settings, icon: Settings },
  ];
  // Phase 11: the sidebar respects permissions — a link only shows when the
  // user holds ANY of the route's view codes (manager: all). While the
  // context loads, nothing is shown rather than flashing forbidden links.
  // Hiding is cosmetic; every API enforces the same permissions itself.
  const hotelItems =
    access === null
      ? allHotelItems
      : access.loading
        ? []
        : allHotelItems.filter((item) => {
            const required = HOTEL_ROUTE_ACCESS[item.href];
            return !required || access.can(...required);
          });

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
