"use client";

import Link from "next/link";
import { Hotel, LogIn, Mail, MapPin, Phone, TicketCheck } from "lucide-react";

import { Icon } from "@/components/ui";
import { LanguageSwitcher } from "@/components/layout/LanguageSwitcher";
import { resolvePublicText } from "@/lib/api/public";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { SiteSettingsProvider, useSiteSettings } from "./SiteSettingsContext";

/**
 * Layout shell for the PUBLIC website (Phase 15). Since Phase 16 the header
 * links/buttons (visibility + labels), the contact info and the footer are
 * controlled by the platform owner's public-site settings — with the built-in
 * dictionary texts as the fallback when no override is set.
 */
export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <SiteSettingsProvider>
      <PublicShellInner>{children}</PublicShellInner>
    </SiteSettingsProvider>
  );
}

function PublicShellInner({ children }: { children: React.ReactNode }) {
  const { t, locale } = useI18n();
  const settings = useSiteSettings();
  const header = settings?.header;
  const contact = settings?.contact;

  const show = {
    home: header?.show_home_link ?? true,
    hotels: header?.show_hotels_link ?? true,
    contact: header?.show_contact_link ?? true,
    bookNow: header?.show_book_now_button ?? true,
    trial: header?.show_trial_button ?? true,
  };

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
            {show.home ? (
              <Link href="/" className="public-nav__link">
                {resolvePublicText(header?.home_label, locale, t.public.nav.home)}
              </Link>
            ) : null}
            {show.hotels ? (
              <Link href="/hotels" className="public-nav__link">
                {resolvePublicText(header?.hotels_label, locale, t.public.nav.hotels)}
              </Link>
            ) : null}
            {show.contact ? (
              <a href="#public-contact" className="public-nav__link">
                {resolvePublicText(
                  header?.contact_label,
                  locale,
                  t.public.nav.contact,
                )}
              </a>
            ) : null}
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
            {show.bookNow ? (
              <Link href="/hotels" className="btn btn--secondary btn--sm">
                {resolvePublicText(
                  header?.book_now_label,
                  locale,
                  t.public.nav.bookNow,
                )}
              </Link>
            ) : null}
            {show.trial ? (
              <Link href="/login" className="btn btn--primary btn--sm">
                {resolvePublicText(
                  header?.trial_label,
                  locale,
                  t.public.nav.freeTrial,
                )}
              </Link>
            ) : null}
          </div>
        </div>
      </header>
      <main className="public-main">{children}</main>
      <footer className="public-footer" id="public-contact">
        <div className="public-footer__inner">
          <div className="stack" style={{ gap: "var(--space-2)" }}>
            <span className="public-brand__name">{t.app.name}</span>
            <span className="muted">
              {resolvePublicText(
                settings?.footer.text,
                locale,
                t.public.footer.tagline,
              )}
            </span>
          </div>
          {contact && (contact.phone || contact.email || contact.address) ? (
            <ul className="public-contact">
              {contact.phone ? (
                <li>
                  <Icon icon={Phone} size="sm" />
                  <span dir="ltr">{contact.phone}</span>
                </li>
              ) : null}
              {contact.email ? (
                <li>
                  <Icon icon={Mail} size="sm" />
                  <span dir="ltr">{contact.email}</span>
                </li>
              ) : null}
              {contact.address ? (
                <li>
                  <Icon icon={MapPin} size="sm" />
                  {contact.address}
                </li>
              ) : null}
            </ul>
          ) : null}
        </div>
      </footer>
    </div>
  );
}
