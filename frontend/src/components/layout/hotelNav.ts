import {
  BarChart3,
  BedDouble,
  CalendarCheck,
  CalendarClock,
  ClipboardList,
  Clock,
  DoorOpen,
  FileText,
  Landmark,
  LayoutDashboard,
  Settings,
  UserCog,
  Users,
  UtensilsCrossed,
  Wallet,
  type LucideIcon,
} from "lucide-react";

import type { Dictionary } from "@/lib/i18n/dictionaries";
import type { HotelAccess } from "@/lib/session/HotelAccessContext";
import { HOTEL_ROUTE_ACCESS } from "@/lib/session/hotelRouteAccess";

export interface HotelNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
  /** Overrides the route-map permission lookup for this item. An empty
   * array means the item is visible to every active member. */
  access?: string[];
}

/**
 * The OFFICIAL hotel navigation (owner-approved order and labels) — ONE
 * source of truth shared by the sidebar and the dashboard's quick-access
 * grid. Dashboard first; subscription is deliberately NOT here (owner
 * decision: it is reached from the topbar badge, and notifications from
 * the topbar bell only — both routes stay alive, just not listed).
 */
export function hotelNavItems(t: Dictionary): HotelNavItem[] {
  return [
    {
      href: "/hotel",
      label: t.sidebar.dashboard,
      icon: LayoutDashboard,
      exact: true,
      access: [],
    },
    { href: "/hotel/rooms", label: t.sidebar.roomsFloors, icon: BedDouble },
    { href: "/hotel/reservations", label: t.sidebar.reservations, icon: CalendarCheck },
    { href: "/hotel/front-desk", label: t.sidebar.checkInOut, icon: DoorOpen },
    { href: "/hotel/guests", label: t.sidebar.guests, icon: Users },
    { href: "/hotel/operations", label: t.sidebar.housekeeping, icon: ClipboardList },
    { href: "/hotel/services", label: t.sidebar.restaurant, icon: UtensilsCrossed },
    {
      href: "/hotel/guest-folio",
      label: t.sidebar.guestFolio,
      icon: FileText,
      access: ["service_orders.create", "services.view", "finance.view"],
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
      href: "/hotel/daily-close",
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
    { href: "/hotel/settings", label: t.sidebar.settings, icon: Settings },
  ];
}

/**
 * Phase 11 visibility filter (shared verbatim by sidebar and dashboard):
 * an item shows only when the user holds ANY of its view codes (manager:
 * all). Split entries carry their own `access` override; others use the
 * central route map. While the context loads, nothing is shown rather than
 * flashing forbidden links. Hiding is cosmetic; every API enforces the
 * same permissions itself.
 */
export function visibleHotelNavItems(
  items: HotelNavItem[],
  access: HotelAccess | null,
): HotelNavItem[] {
  if (access === null) return items;
  if (access.loading) return [];
  return items.filter((item) => {
    const required = item.access ?? HOTEL_ROUTE_ACCESS[item.href];
    return !required || required.length === 0 || access.can(...required);
  });
}
