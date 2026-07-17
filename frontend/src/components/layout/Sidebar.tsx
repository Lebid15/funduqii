"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  Building2,
  CreditCard,
  Globe,
  Hotel,
  Inbox,
  LayoutDashboard,
  Package,
  Settings,
} from "lucide-react";

import { Icon } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

import {
  hotelNavItems,
  visibleHotelNavItems,
  type HotelNavItem,
} from "./hotelNav";

type ShellVariant = "platform" | "hotel";

/** Central navigation: the PLATFORM identity on top and the nav list only —
 * the hotel identity and the user chip live in the topbar (owner decision).
 * Serves both shells via the `variant` prop. The hotel list itself comes
 * from the shared hotelNav config (also feeds the dashboard shortcuts). */
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

  const platformItems: HotelNavItem[] = [
    { href: "/platform", label: t.nav.dashboard, icon: LayoutDashboard, exact: true },
    { href: "/platform/hotels", label: t.nav.hotels, icon: Building2 },
    { href: "/platform/plans", label: t.nav.plans, icon: Package },
    { href: "/platform/subscriptions", label: t.nav.subscriptions, icon: CreditCard },
    {
      href: "/platform/subscription-requests",
      label: t.nav.subscriptionRequests,
      icon: Inbox,
    },
    { href: "/platform/public-site", label: t.nav.publicSite, icon: Globe },
    { href: "/platform/settings", label: t.nav.settings, icon: Settings },
  ];

  const items =
    variant === "hotel"
      ? visibleHotelNavItems(hotelNavItems(t), access)
      : platformItems;
  // Scope label only — never the hotel's name (the hotel identity is in the
  // topbar per the owner's correction).
  const brandSubtitle =
    variant === "hotel" ? t.hotel.nav.subtitle : t.nav.platformOwner;
  const navLabel = brandSubtitle;

  function isActive(item: HotelNavItem): boolean {
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
          <Icon icon={Hotel} size="xl" />
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
