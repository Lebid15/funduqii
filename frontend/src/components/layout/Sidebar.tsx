"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Building2,
  CreditCard,
  Hotel,
  LayoutDashboard,
  Package,
  Settings,
  type LucideIcon,
} from "lucide-react";

import { Icon } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
}

/** Central platform navigation. Rendered inside the AppShell sidebar. */
export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useI18n();
  const pathname = usePathname();

  const items: NavItem[] = [
    { href: "/platform", label: t.nav.dashboard, icon: LayoutDashboard, exact: true },
    { href: "/platform/hotels", label: t.nav.hotels, icon: Building2 },
    { href: "/platform/plans", label: t.nav.plans, icon: Package },
    { href: "/platform/subscriptions", label: t.nav.subscriptions, icon: CreditCard },
    { href: "/platform/settings", label: t.nav.settings, icon: Settings },
  ];

  function isActive(item: NavItem): boolean {
    if (item.exact) return pathname === item.href;
    return pathname === item.href || pathname.startsWith(`${item.href}/`);
  }

  return (
    <>
      <div className="app-sidebar__brand">
        <span className="app-sidebar__brand-mark">
          <Icon icon={Hotel} size="lg" />
        </span>
        <span className="app-sidebar__brand-text">
          <span className="app-sidebar__brand-name">{t.app.name}</span>
          <span className="app-sidebar__brand-sub">{t.nav.platformOwner}</span>
        </span>
      </div>
      <nav className="app-nav" aria-label={t.nav.platformOwner}>
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
