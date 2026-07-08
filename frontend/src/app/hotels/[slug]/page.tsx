"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  BedDouble,
  Clock,
  Globe,
  Hotel,
  Mail,
  MapPin,
  Phone,
  Star,
  Users,
} from "lucide-react";

import { PublicBookingPanel } from "@/components/public/PublicBookingPanel";
import { PublicShell } from "@/components/public/PublicShell";
import { Badge, ErrorState, Icon, LoadingState } from "@/components/ui";
import { getPublicHotel, type PublicHotelDetail } from "@/lib/api/public";
import { messageForError } from "@/lib/api/errors";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** Public hotel page (Phase 15): display + availability + booking form. */
export default function PublicHotelPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const { t } = useI18n();
  const [hotel, setHotel] = useState<PublicHotelDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      setHotel(await getPublicHotel(slug));
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (status === 404) setNotFound(true);
      else setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [slug, t]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <PublicShell>
      {loading ? <LoadingState label={t.common.loading} /> : null}

      {!loading && notFound ? (
        <section className="public-section">
          <ErrorState
            title={t.public.hotel.notFound}
            message={t.public.hotel.notFoundHint}
            retryLabel={t.public.hotel.backToHotels}
            onRetry={() => {
              window.location.href = "/hotels";
            }}
          />
        </section>
      ) : null}

      {!loading && !notFound && error ? (
        <section className="public-section">
          <ErrorState
            title={t.states.errorTitle}
            message={error}
            retryLabel={t.common.retry}
            onRetry={load}
          />
        </section>
      ) : null}

      {!loading && hotel ? (
        <>
          <section className="public-hotel-hero">
            {hotel.cover_url ? (
              // eslint-disable-next-line @next/next/no-img-element -- user-uploaded media
              <img
                className="public-hotel-hero__cover"
                src={hotel.cover_url}
                alt={hotel.name}
              />
            ) : (
              <div className="public-hotel-hero__cover public-hotel-hero__cover--empty">
                <Icon icon={Hotel} size="lg" />
              </div>
            )}
            <div className="public-hotel-hero__head">
              <div>
                <h1 className="public-hotel-hero__name">{hotel.name}</h1>
                <p className="public-hotel-card__location">
                  <Icon icon={MapPin} size="sm" />
                  {[hotel.area, hotel.city, hotel.country]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <div className="cluster">
                {hotel.star_rating ? (
                  <Badge tone="info">
                    <Icon icon={Star} size="sm" /> {hotel.star_rating}
                  </Badge>
                ) : null}
                <Badge tone={hotel.booking_enabled ? "success" : "neutral"}>
                  {hotel.booking_enabled
                    ? t.public.hotels.bookingAvailable
                    : t.public.hotels.bookingUnavailable}
                </Badge>
              </div>
            </div>
          </section>

          <section className="public-hotel-layout">
            <div className="stack">
              {hotel.description || hotel.short_description ? (
                <div className="public-panel">
                  <h2>{t.public.hotel.about}</h2>
                  <p className="public-prewrap">
                    {hotel.description || hotel.short_description}
                  </p>
                </div>
              ) : null}

              <div className="public-panel">
                <h2>{t.public.hotel.roomTypes}</h2>
                {hotel.room_types.length === 0 ? (
                  <p className="muted">{t.public.hotel.noRoomTypes}</p>
                ) : (
                  <div className="stack">
                    {hotel.room_types.map((rt) => (
                      <div key={rt.id} className="public-room-type">
                        <div className="public-room-type__head">
                          <span className="public-room-type__name">
                            <Icon icon={BedDouble} size="sm" />
                            {rt.name}
                          </span>
                          {rt.base_price ? (
                            <span className="public-room-type__price">
                              {rt.base_price} {rt.currency}
                              <span className="muted"> {t.public.hotel.perNight}</span>
                            </span>
                          ) : null}
                        </div>
                        {rt.description ? (
                          <p className="muted public-prewrap">{rt.description}</p>
                        ) : null}
                        <span className="muted public-room-type__meta">
                          <Icon icon={Users} size="sm" />
                          {t.public.hotel.upTo.replace(
                            "{count}",
                            String(rt.max_capacity),
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {hotel.gallery.length > 0 ? (
                <div className="public-panel">
                  <h2>{t.public.hotel.gallery}</h2>
                  <div className="public-gallery">
                    {hotel.gallery.map((img) => (
                      // eslint-disable-next-line @next/next/no-img-element -- user-uploaded media
                      <img key={img.url} src={img.url} alt={img.alt} loading="lazy" />
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="public-panel">
                <h2>{t.public.hotel.policies}</h2>
                <dl className="detail-grid">
                  {hotel.check_in_time ? (
                    <div>
                      <dt>
                        <Icon icon={Clock} size="sm" /> {t.public.hotel.checkIn}
                      </dt>
                      <dd>{hotel.check_in_time.slice(0, 5)}</dd>
                    </div>
                  ) : null}
                  {hotel.check_out_time ? (
                    <div>
                      <dt>
                        <Icon icon={Clock} size="sm" /> {t.public.hotel.checkOut}
                      </dt>
                      <dd>{hotel.check_out_time.slice(0, 5)}</dd>
                    </div>
                  ) : null}
                  {hotel.min_nights ? (
                    <div>
                      <dt>{t.public.hotel.minNights}</dt>
                      <dd>{hotel.min_nights}</dd>
                    </div>
                  ) : null}
                  {hotel.max_nights ? (
                    <div>
                      <dt>{t.public.hotel.maxNights}</dt>
                      <dd>{hotel.max_nights}</dd>
                    </div>
                  ) : null}
                </dl>
                {hotel.cancellation_policy ? (
                  <>
                    <h3>{t.public.hotel.cancellationPolicy}</h3>
                    <p className="muted public-prewrap">{hotel.cancellation_policy}</p>
                  </>
                ) : null}
                {hotel.terms ? (
                  <>
                    <h3>{t.public.hotel.terms}</h3>
                    <p className="muted public-prewrap">{hotel.terms}</p>
                  </>
                ) : null}
              </div>

              <div className="public-panel">
                <h2>{t.public.hotel.contact}</h2>
                <ul className="public-contact">
                  {hotel.address ? (
                    <li>
                      <Icon icon={MapPin} size="sm" />
                      {hotel.address}
                    </li>
                  ) : null}
                  {hotel.phone ? (
                    <li>
                      <Icon icon={Phone} size="sm" />
                      <span dir="ltr">{hotel.phone}</span>
                    </li>
                  ) : null}
                  {hotel.email ? (
                    <li>
                      <Icon icon={Mail} size="sm" />
                      <span dir="ltr">{hotel.email}</span>
                    </li>
                  ) : null}
                  {hotel.website ? (
                    <li>
                      <Icon icon={Globe} size="sm" />
                      <a
                        href={hotel.website}
                        target="_blank"
                        rel="noopener noreferrer"
                        dir="ltr"
                      >
                        {hotel.website}
                      </a>
                    </li>
                  ) : null}
                </ul>
                <Link href="/hotels" className="public-nav__link">
                  {t.public.hotel.backToHotels}
                </Link>
              </div>
            </div>

            <aside className="public-hotel-aside">
              <PublicBookingPanel hotel={hotel} />
            </aside>
          </section>
        </>
      ) : null}
    </PublicShell>
  );
}
