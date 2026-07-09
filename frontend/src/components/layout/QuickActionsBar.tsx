"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Brush,
  CalendarPlus,
  ChevronDown,
  LogIn,
  LogOut,
  Receipt,
  UserPlus,
  UtensilsCrossed,
  Wallet,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { Icon } from "@/components/ui";
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

/** DIRECT daily operations in priority order (owner correction): every
 * button lands in the EXISTING create form/modal — `action=new` is consumed
 * once by the owning component (useQuickAction) which opens its modal and
 * strips the param. Check-in/out and payment are entity-scoped by design,
 * so their buttons open the existing selection surface (today's arrivals /
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
  { key: "addGuest", href: "/hotel/guests?action=new", icon: UserPlus, access: ["guests.view"] },
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
 * Quick Actions Bar (owner spec): the second row of the topbar card in the
 * HOTEL shell — small icon+label buttons for the daily operations, filtered
 * by the same Phase 11 access rule as the sidebar. Desktop: one tidy
 * wrapping row. Mobile (≤640px): a quiet disclosure button that unfolds a
 * two-column grid — no horizontal overflow ever.
 */
export function QuickActionsBar() {
  const { t } = useI18n();
  const access = useHotelAccess();
  const [open, setOpen] = useState(false);

  // Same visibility rule as the sidebar: nothing while permissions load
  // (no forbidden flash), any-of codes afterwards, manager sees all.
  if (access !== null && access.loading) return null;
  const visible = ACTIONS.filter(
    (action) => access === null || access.can(...action.access),
  );
  if (visible.length === 0) return null;

  const labels = t.quickActions as Record<string, string>;

  return (
    <nav
      className="quick-actions"
      aria-label={t.quickActions.title}
      data-open={open || undefined}
    >
      <button
        type="button"
        className="quick-actions__toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon icon={Zap} size="sm" />
        {t.quickActions.title}
        <Icon icon={ChevronDown} size="sm" className="quick-actions__chevron" />
      </button>
      <div className="quick-actions__list">
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
    </nav>
  );
}
