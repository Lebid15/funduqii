"use client";

import { Alert } from "@/components/ui";
import { useHotelProfile } from "@/lib/session/HotelProfileContext";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Phase 16 — the hotel console's subscription banner. Shown at the top of
 * every hotel page: suspended / expired / expiring soon. Purely a UX layer:
 * the REAL protection is the backend enforcement (`hotel_suspended` /
 * `subscription_inactive`); old data is never hidden and reads keep working.
 * The profile comes from the shared shell context (one load per shell).
 */
export function SubscriptionBanner() {
  const { t } = useI18n();
  const state = useHotelProfile()?.subscription_state ?? null;

  if (!state) return null;

  if (state.suspended) {
    return <Alert tone="error">{t.subscriptionState.suspended}</Alert>;
  }
  if (state.expired) {
    return <Alert tone="error">{t.subscriptionState.expired}</Alert>;
  }
  if (state.expiring_soon) {
    return (
      <Alert tone="warning">
        {t.subscriptionState.expiringSoon.replace(
          "{days}",
          String(state.days_left ?? 0),
        )}
      </Alert>
    );
  }
  return null;
}
