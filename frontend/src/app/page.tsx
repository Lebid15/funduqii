"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Building2, CalendarCheck, ShieldCheck } from "lucide-react";

import { PublicHotelCard } from "@/components/public/PublicHotelCard";
import { PublicShell } from "@/components/public/PublicShell";
import { Icon, LoadingState } from "@/components/ui";
import { listPublicHotels, type PublicHotelCard as HotelCardDto } from "@/lib/api/public";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * The PUBLIC home page (Phase 15). Visitors land here; hotel staff and
 * platform owners continue to /login as before.
 */
export default function PublicHomePage() {
  const { t } = useI18n();
  const [hotels, setHotels] = useState<HotelCardDto[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listPublicHotels()
      .then((data) => {
        const featured = data.results.filter((h) => h.featured);
        setHotels((featured.length > 0 ? featured : data.results).slice(0, 6));
      })
      .catch(() => setHotels([]))
      .finally(() => setLoading(false));
  }, []);

  const features = [
    { icon: Building2, label: t.public.home.feature1 },
    { icon: CalendarCheck, label: t.public.home.feature2 },
    { icon: ShieldCheck, label: t.public.home.feature3 },
  ];

  return (
    <PublicShell>
      <section className="public-hero">
        <h1 className="public-hero__title">{t.public.home.heroTitle}</h1>
        <p className="public-hero__subtitle">{t.public.home.heroSubtitle}</p>
        <div className="cluster public-hero__actions">
          <Link href="/hotels" className="btn btn--primary">
            {t.public.home.browseCta}
          </Link>
          <Link href="/booking/manage" className="btn btn--secondary">
            {t.public.nav.manageBooking}
          </Link>
        </div>
        <ul className="public-hero__features">
          {features.map((f) => (
            <li key={f.label} className="public-hero__feature">
              <Icon icon={f.icon} size="sm" />
              {f.label}
            </li>
          ))}
        </ul>
      </section>

      <section className="public-section">
        <div className="public-section__head">
          <h2>{t.public.home.featuredTitle}</h2>
          <Link href="/hotels" className="public-nav__link">
            {t.public.home.browseAll}
          </Link>
        </div>
        {loading ? (
          <LoadingState label={t.common.loading} />
        ) : hotels.length === 0 ? (
          <p className="muted">{t.public.hotels.empty}</p>
        ) : (
          <div className="public-hotel-grid">
            {hotels.map((h) => (
              <PublicHotelCard key={h.slug} hotel={h} />
            ))}
          </div>
        )}
      </section>
    </PublicShell>
  );
}
