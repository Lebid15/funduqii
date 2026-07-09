"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarClock, CreditCard } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import {
  Alert,
  Badge,
  Card,
  ErrorState,
  LoadingState,
  PageHeader,
  SectionHeader,
} from "@/components/ui";
import { getProfile } from "@/lib/api/hotel";
import { messageForError } from "@/lib/api/errors";
import type { HotelSubscriptionState } from "@/lib/api/types";
import { formatDate, subscriptionStatusLabel, subscriptionStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * READ-ONLY subscription status page for the hotel console (sidebar item
 * "الاشتراك والباقات"). It displays the same `subscription_state` the shell
 * banner uses: plan, status, end date and restrictions. Plans themselves are
 * managed ONLY from the platform owner panel — there is no payment, no
 * gateway and no upgrade checkout here.
 */
export default function HotelSubscriptionPage() {
  const { t, locale } = useI18n();
  const [state, setState] = useState<HotelSubscriptionState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const profile = await getProfile();
      setState(profile.subscription_state);
      setError(null);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <PageContainer>
      <PageHeader
        title={t.hotelSubscription.title}
        subtitle={t.hotelSubscription.subtitle}
      />

      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? (
        <ErrorState
          title={t.states.errorTitle}
          message={error}
          retryLabel={t.common.retry}
          onRetry={() => {
            setLoading(true);
            load();
          }}
        />
      ) : null}

      {!loading && !error && state ? (
        <>
          {state.suspended ? (
            <Alert tone="error">{t.subscriptionState.suspended}</Alert>
          ) : state.expired ? (
            <Alert tone="error">{t.subscriptionState.expired}</Alert>
          ) : state.expiring_soon ? (
            <Alert tone="warning">
              {t.subscriptionState.expiringSoon.replace(
                "{days}",
                String(state.days_left ?? 0),
              )}
            </Alert>
          ) : null}

          <Card>
            <SectionHeader
              title={t.hotelSubscription.currentPlan}
              description={t.hotelSubscription.managedByPlatform}
              icon={CreditCard}
            />
            {state.status ? (
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-item__label">
                    {t.hotelSubscription.plan}
                  </span>
                  <span className="detail-item__value">
                    {state.plan_name ?? "—"}
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-item__label">{t.common.status}</span>
                  <span>
                    <Badge tone={subscriptionStatusTone(state.status)}>
                      {subscriptionStatusLabel(state.status, t)}
                    </Badge>
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-item__label">
                    {t.hotelSubscription.endsAt}
                  </span>
                  <span className="detail-item__value">
                    {state.ends_at ? formatDate(state.ends_at, locale) : "—"}
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-item__label">
                    {t.hotelSubscription.daysLeft}
                  </span>
                  <span className="detail-item__value">
                    {state.days_left ?? "—"}
                  </span>
                </div>
              </div>
            ) : (
              <p className="muted">{t.hotelSubscription.noSubscription}</p>
            )}
          </Card>

          <Card>
            <SectionHeader
              title={t.hotelSubscription.renewalTitle}
              icon={CalendarClock}
            />
            <p className="muted">{t.hotelSubscription.contactOwner}</p>
          </Card>
        </>
      ) : null}
    </PageContainer>
  );
}
