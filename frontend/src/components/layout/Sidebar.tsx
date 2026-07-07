"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useI18n } from "@/lib/i18n/I18nProvider";

interface NavItem {
  href: string;
  label: string;
  exact?: boolean;
}

/** Central platform navigation. Rendered inside the AppShell sidebar. */
export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useI18n();
  const pathname = usePathname();

  const items: NavItem[] = [
    { href: "/platform", label: t.nav.dashboard, exact: true },
    { href: "/platform/hotels", label: t.nav.hotels },
    { href: "/platform/plans", label: t.nav.plans },
    { href: "/platform/subscriptions", label: t.nav.subscriptions },
    { href: "/platform/settings", label: t.nav.settings },
  ];

  function isActive(item: NavItem): boolean {
    if (item.exact) return pathname === item.href;
    return pathname === item.href || pathname.startsWith(`${item.href}/`);
  }

  return (
    <>
      <div className="app-sidebar__brand">
        <span>{t.app.name}</span>
        <span className="app-sidebar__brand-sub">{t.nav.platformOwner}</span>
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
            {item.label}
          </Link>
        ))}
      </nav>
    </>
  );
}
