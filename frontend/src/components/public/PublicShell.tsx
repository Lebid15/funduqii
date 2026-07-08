"use client";

import Link from "next/link";
import { Hotel, LogIn, TicketCheck } from "lucide-react";

import { Icon } from "@/components/ui";
import { LanguageSwitcher } from "@/components/layout/LanguageSwitcher";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Layout shell for the PUBLIC website (Phase 15): header with brand,
 * navigation, language switcher and the console entry points, plus a footer.
 * No session, no hotel context — visitors only.
 */
export function PublicShell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <div className="public-shell">
      <header className="public-header">
        <div className="public-header__inner">
          <Link href="/" className="public-brand">
            <span className="brand-mark">
              <Icon icon={Hotel} size="md" />
            </span>
            <span className="public-brand__name">{t.app.name}</span>
          </Link>
          <nav className="public-nav" aria-label={t.public.nav.label}>
            <Link href="/hotels" className="public-nav__link">
              {t.public.nav.hotels}
            </Link>
            <Link href="/booking/manage" className="public-nav__link">
              <Icon icon={TicketCheck} size="sm" />
              {t.public.nav.manageBooking}
            </Link>
          </nav>
          <div className="public-header__actions">
            <LanguageSwitcher />
            <Link href="/login" className="public-nav__link">
              <Icon icon={LogIn} size="sm" />
              {t.public.nav.login}
            </Link>
            <Link href="/login" className="btn btn--primary btn--sm">
              {t.public.nav.freeTrial}
            </Link>
          </div>
        </div>
      </header>
      <main className="public-main">{children}</main>
      <footer className="public-footer">
        <div className="public-footer__inner">
          <span className="public-brand__name">{t.app.name}</span>
          <span className="muted">{t.public.footer.tagline}</span>
        </div>
      </footer>
    </div>
  );
}
