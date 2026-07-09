"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  BarChart3,
  BedDouble,
  Building2,
  CalendarCheck,
  CalendarClock,
  ClipboardList,
  Clock,
  CreditCard,
  DoorOpen,
  FileText,
  Globe,
  Hotel,
  Landmark,
  LayoutDashboard,
  Package,
  Settings,
  UserCog,
  Users,
  UtensilsCrossed,
  Wallet,
  type LucideIcon,
} from "lucide-react";

import { Icon } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { HOTEL_ROUTE_ACCESS } from "@/lib/session/hotelRouteAccess";

type ShellVariant = "platform" | "hotel";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
  /** Overrides the route-map permission lookup for this item. An empty
   * array means the item is visible to every active member. */
  access?: string[];
}

/** Central navigation: the PLATFORM identity on top and the nav list only —
 * the hotel identity and the user chip live in the topbar (owner decision).
 * Serves both shells via the `variant` prop. */
export function Sidebar({
  variant,
  onNavigate,
}: {
  variant: ShellVariant;
  onNavigate?: () => void;
}) {
  const { t } = useI18n();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const access = useHotelAccess();

  const platformItems: NavItem[] = [
    { href: "/platform", label: t.nav.dashboard, icon: LayoutDashboard, exact: true },
    { href: "/platform/hotels", label: t.nav.hotels, icon: Building2 },
    { href: "/platform/plans", label: t.nav.plans, icon: Package },
    { href: "/platform/subscriptions", label: t.nav.subscriptions, icon: CreditCard },
    { href: "/platform/public-site", label: t.nav.publicSite, icon: Globe },
    { href: "/platform/settings", label: t.nav.settings, icon: Settings },
  ];
  // The OFFICIAL hotel sidebar (owner-approved order and labels). Merged
  // consoles are split into separate entries via tab deep-links — the pages
  // themselves keep their existing services and tabs; notifications live in
  // the topbar bell only (the route stays reachable, just not listed here).
  const allHotelItems: NavItem[] = [
    { href: "/hotel/rooms", label: t.sidebar.roomsFloors, icon: BedDouble },
    { href: "/hotel/reservations", label: t.sidebar.reservations, icon: CalendarCheck },
    { href: "/hotel/front-desk", label: t.sidebar.checkInOut, icon: DoorOpen },
    { href: "/hotel/guests", label: t.sidebar.guests, icon: Users },
    { href: "/hotel/operations", label: t.sidebar.housekeeping, icon: ClipboardList },
    { href: "/hotel/services", label: t.sidebar.restaurant, icon: UtensilsCrossed },
    {
      href: "/hotel/finance?tab=folios",
      label: t.sidebar.guestFolio,
      icon: FileText,
      access: ["finance.view"],
    },
    {
      href: "/hotel/finance?tab=expenses",
      label: t.sidebar.expenses,
      icon: Wallet,
      access: ["expenses.view"],
    },
    { href: "/hotel/staff", label: t.sidebar.staff, icon: UserCog },
    {
      href: "/hotel/shifts",
      label: t.sidebar.shifts,
      icon: Clock,
      access: ["shifts.view"],
    },
    {
      href: "/hotel/shifts?tab=dailyClose",
      label: t.sidebar.dailyClose,
      icon: CalendarClock,
      access: ["daily_close.view"],
    },
    {
      href: "/hotel/finance",
      label: t.sidebar.finance,
      icon: Landmark,
      access: ["finance.view"],
    },
    { href: "/hotel/reports", label: t.sidebar.reports, icon: BarChart3 },
    {
      href: "/hotel/subscription",
      label: t.sidebar.subscription,
      icon: CreditCard,
      // Read-only billing state — the same information every member already
      // sees in the shell banner, so no permission code gates it.
      access: [],
    },
    { href: "/hotel/settings", label: t.sidebar.settings, icon: Settings },
  ];
  // Phase 11: the sidebar respects permissions — a link only shows when the
  // user holds ANY of its view codes (manager: all). Split entries carry
  // their own `access` override; others use the central route map. While the
  // context loads, nothing is shown rather than flashing forbidden links.
  // Hiding is cosmetic; every API enforces the same permissions itself.
  const hotelItems =
    access === null
      ? allHotelItems
      : access.loading
        ? []
        : allHotelItems.filter((item) => {
            const required = item.access ?? HOTEL_ROUTE_ACCESS[item.href];
            return !required || required.length === 0 || access.can(...required);
          });

  const items = variant === "hotel" ? hotelItems : platformItems;
  // Scope label only — never the hotel's name (the hotel identity is in the
  // topbar per the owner's correction).
  const brandSubtitle =
    variant === "hotel" ? t.hotel.nav.subtitle : t.nav.platformOwner;
  const navLabel = brandSubtitle;

  function isActive(item: NavItem): boolean {
    const [basePath, query] = item.href.split("?");
    if (item.exact) return pathname === basePath;
    if (pathname !== basePath && !pathname.startsWith(`${basePath}/`)) {
      return false;
    }
    // Split entries deep-link tabs on a shared page: an item with a ?tab=
    // is active only for its own tab, and the plain item only when the
    // current tab is not claimed by one of its siblings.
    const itemTab = query ? new URLSearchParams(query).get("tab") : null;
    const currentTab = searchParams.get("tab");
    if (itemTab) return currentTab === itemTab;
    const siblingTabs = items
      .filter((other) => other !== item && other.href.startsWith(`${basePath}?`))
      .map((other) => new URLSearchParams(other.href.split("?")[1]).get("tab"));
    return !currentTab || !siblingTabs.includes(currentTab);
  }

  // Owner correction: the sidebar carries the PLATFORM identity only —
  // Funduqii mark + name + the nav list. The HOTEL identity (logo/name)
  // lives in the topbar; user info lives in the topbar chip.
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
    </>
  );
}
