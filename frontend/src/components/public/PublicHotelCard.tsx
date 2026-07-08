"use client";

import Link from "next/link";
import { Hotel, MapPin, Star } from "lucide-react";

import { Badge, Icon } from "@/components/ui";
import type { PublicHotelCard as HotelCardDto } from "@/lib/api/public";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** One published hotel in the public list/home — the whole card is a link. */
export function PublicHotelCard({ hotel }: { hotel: HotelCardDto }) {
  const { t } = useI18n();
  return (
    <Link href={`/hotels/${hotel.slug}`} className="public-hotel-card">
      <div className="public-hotel-card__cover">
        {hotel.cover_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- user-uploaded media
          <img src={hotel.cover_url} alt={hotel.name} loading="lazy" />
        ) : (
          <span className="public-hotel-card__placeholder">
            <Icon icon={Hotel} size="lg" />
          </span>
        )}
        {hotel.featured ? (
          <span className="public-hotel-card__featured">
            {t.public.hotels.featured}
          </span>
        ) : null}
      </div>
      <div className="public-hotel-card__body">
        <div className="public-hotel-card__title-row">
          <h3 className="public-hotel-card__name">{hotel.name}</h3>
          {hotel.star_rating ? (
            <span className="public-hotel-card__stars">
              <Icon icon={Star} size="sm" />
              {hotel.star_rating}
            </span>
          ) : null}
        </div>
        {hotel.city || hotel.country ? (
          <p className="public-hotel-card__location">
            <Icon icon={MapPin} size="sm" />
            {[hotel.city, hotel.country].filter(Boolean).join(" · ")}
          </p>
        ) : null}
        {hotel.short_description ? (
          <p className="public-hotel-card__desc">{hotel.short_description}</p>
        ) : null}
        <div className="public-hotel-card__foot">
          <Badge tone={hotel.booking_enabled ? "success" : "neutral"}>
            {hotel.booking_enabled
              ? t.public.hotels.bookingAvailable
              : t.public.hotels.bookingUnavailable}
          </Badge>
          <span className="public-hotel-card__cta">{t.public.hotels.viewHotel}</span>
        </div>
      </div>
    </Link>
  );
}
