"use client";

import Link from "next/link";
import {
  Brush,
  CalendarPlus,
  LogIn,
  LogOut,
  Receipt,
  UtensilsCrossed,
  Wallet,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import { Icon, SectionHeader } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { cx } from "@/lib/utils";

interface QuickAction {
  key: string;
  href: string;
  icon: LucideIcon;
  /** Phase 11 codes — the button shows when the user holds ANY of them
   * (manager: all). Same any-of rule as the sidebar. */
  access: string[];
  primary?: boolean;
}

/** DIRECT daily operations in priority order (owner spec): every button
 * lands in the EXISTING create form/modal — `action=new` is consumed once
 * by the owning component (useQuickAction) which opens its modal and strips
 * the param. Check-in/out and payment are entity-scoped by design, so their
 * buttons open the existing selection surface (today's arrivals /
 * departures, the folio list) where the action lives on each row. No new
 * flows, no new modals, no new backend. */
const ACTIONS: QuickAction[] = [
  {
    key: "newReservation",
    href: "/hotel/reservations?tab=reservations&action=new",
    icon: CalendarPlus,
    access: ["reservations.view"],
    primary: true,
  },
  { key: "checkIn", href: "/hotel/front-desk?tab=arrivals", icon: LogIn, access: ["stays.view"] },
  { key: "checkOut", href: "/hotel/front-desk?tab=departures", icon: LogOut, access: ["stays.view"] },
  {
    key: "recordPayment",
    href: "/hotel/finance?tab=folios",
    icon: Receipt,
    access: ["finance.view"],
  },
  {
    key: "addExpense",
    href: "/hotel/finance?tab=expenses&action=new",
    icon: Wallet,
    access: ["expenses.view"],
  },
  {
    key: "serviceOrder",
    href: "/hotel/services?tab=orders&action=new",
    icon: UtensilsCrossed,
    access: ["services.view", "service_orders.view"],
  },
  {
    key: "housekeepingTask",
    href: "/hotel/operations?tab=housekeeping&action=new",
    icon: Brush,
    access: ["housekeeping.view"],
  },
  {
    key: "maintenance",
    href: "/hotel/operations?tab=maintenance&action=new",
    icon: Wrench,
    access: ["maintenance.view"],
  },
];

/**
 * Quick Operations section — lives ONLY on the /hotel dashboard (owner
 * correction: the topbar stays a clean identity/tools card). A titled
 * section of small direct-operation buttons filtered by the same Phase 11
 * access rule as the sidebar. Desktop: a tidy wrapping row; mobile: a
 * two-column grid — no overflow either way.
 */
export function QuickActionsBar() {
  const { t } = useI18n();
  const access = useHotelAccess();

  // Same visibility rule as the sidebar: nothing while permissions load
  // (no forbidden flash), any-of codes afterwards, manager sees all.
  if (access !== null && access.loading) return null;
  const visible = ACTIONS.filter(
    (action) => access === null || access.can(...action.access),
  );
  if (visible.length === 0) return null;

  const labels = t.quickActions as Record<string, string>;

  return (
    <section className="stack" aria-label={t.quickActions.title}>
      <SectionHeader title={t.quickActions.title} />
      <div className="quick-actions">
        {visible.map((action) => (
          <Link
            key={action.key}
            href={action.href}
            className={cx(
              "quick-actions__btn",
              action.primary && "quick-actions__btn--primary",
            )}
          >
            <Icon icon={action.icon} size="sm" />
            {labels[action.key]}
          </Link>
        ))}
      </div>
    </section>
  );
}
