"use client";

import { Icon } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { amenityIcon } from "./boardShared";

/**
 * Room-type amenity chips (unified icon + translated label). Amenities live on
 * the RoomType, so callers frame them as ROOM-TYPE features (an optional
 * `label` heading) and never as per-room data. When `max` is set only the
 * first `max` chips render and the remainder collapse into a quiet "+N" chip;
 * the details drawer omits `max` to show the full list. Renders nothing for an
 * empty list (no empty section). Icons are decorative — the label carries the
 * meaning — so they stay aria-hidden.
 */
export function AmenityChips({
  amenities,
  max,
  label,
}: {
  amenities: string[];
  max?: number;
  label?: string;
}) {
  const { t } = useI18n();
  const b = t.rooms.board;
  if (!amenities || amenities.length === 0) return null;

  const amenityLabels = b.amenity as Record<string, string>;
  const shown = typeof max === "number" ? amenities.slice(0, max) : amenities;
  const extra = amenities.length - shown.length;

  return (
    <div className="amenities">
      {label ? <span className="amenities__label">{label}</span> : null}
      <ul className="amenities__list" aria-label={label ?? b.roomTypeFeatures}>
        {shown.map((key) => (
          <li key={key} className="amenity-chip">
            <Icon icon={amenityIcon(key)} size="sm" className="amenity-chip__icon" />
            <span>{amenityLabels[key] ?? key}</span>
          </li>
        ))}
        {extra > 0 ? (
          <li className="amenity-chip amenity-chip--more">
            {b.amenitiesMore.replace("{count}", String(extra))}
          </li>
        ) : null}
      </ul>
    </div>
  );
}
