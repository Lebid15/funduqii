"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarClock, CreditCard, Gauge, Receipt } from "lucide-react";

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
import type {
  EntitlementDimension,
  HotelSubscriptionState,
} from "@/lib/api/types";
import {
  billingCycleLabel,
  entitlementStateLabel,
  entitlementStateTone,
  formatDate,
  subscriptionStatusLabel,
  subscriptionStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * READ-ONLY subscription status page for the hotel console (sidebar item
 * "الاشتراك والباقات"). It displays the same `subscription_state` the shell
 * banner uses — now enriched with the frozen plan terms, usage vs limits and
 * the hotel's own payment history. Plans themselves are managed ONLY from the
 * platform owner panel: there is no payment, no gateway and no upgrade checkout
 * here — the only action is to contact the platform administration.
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

  const dimensionRow = (label: string, dim: EntitlementDimension) => (
    <div className="detail-item">
      <span className="detail-item__label">{label}</span>
      <span className="detail-item__value">
        {dim.usage} / {dim.limit ?? t.entitlements.unlimited}
        {dim.limit !== null ? (
          <>
            {" "}
            <Badge tone={entitlementStateTone(dim.state)}>
              {entitlementStateLabel(dim.state, t)}
            </Badge>
            {dim.remaining !== null ? (
              <span className="muted">
                {" "}
                · {dim.remaining} {t.hotelSubscription.remaining}
              </span>
            ) : null}
          </>
        ) : null}
      </span>
    </div>
  );

  const effective = state?.effective_status ?? state?.status ?? null;

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
            <Alert tone="error">{t.hotelSubscription.expiredMessage}</Alert>
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
                  <span className="detail-item__label">
                    {t.hotelSubscription.effectiveStatus}
                  </span>
                  <span>
                    {effective ? (
                      <Badge tone={subscriptionStatusTone(effective)}>
                        {subscriptionStatusLabel(effective, t)}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </span>
                </div>
                {state.terms ? (
                  <>
                    <div className="detail-item">
                      <span className="detail-item__label">
                        {t.hotelSubscription.price}
                      </span>
                      <span className="detail-item__value">
                        {state.terms.price} {state.terms.currency}
                      </span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-item__label">
                        {t.hotelSubscription.billingCycle}
                      </span>
                      <span className="detail-item__value">
                        {billingCycleLabel(state.terms.billing_cycle, t)}
                      </span>
                    </div>
                  </>
                ) : null}
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

          {state.terms ? (
            <Card>
              <SectionHeader
                title={t.hotelSubscription.usageTitle}
                icon={Gauge}
              />
              <div className="detail-grid">
                {dimensionRow(
                  t.hotelSubscription.rooms,
                  state.entitlements.rooms,
                )}
                {dimensionRow(
                  t.hotelSubscription.staff,
                  state.entitlements.staff,
                )}
                {dimensionRow(
                  t.hotelSubscription.publicBookings,
                  state.entitlements.public_bookings,
                )}
              </div>
              <div style={{ marginTop: "0.75rem" }}>
                <span className="detail-item__label">
                  {t.hotelSubscription.features}
                </span>
                <div>
                  {state.entitlements.features.length > 0 ? (
                    state.entitlements.features.map((f) => (
                      <Badge key={f} tone="neutral">
                        {f}
                      </Badge>
                    ))
                  ) : (
                    <span className="muted">
                      {t.hotelSubscription.noFeatures}
                    </span>
                  )}
                </div>
              </div>
            </Card>
          ) : null}

          {state.payments.length > 0 ? (
            <Card>
              <SectionHeader
                title={t.hotelSubscription.payments}
                icon={Receipt}
              />
              <div className="detail-grid">
                {state.payments.map((p, i) => (
                  <div className="detail-item" key={i}>
                    <span className="detail-item__label">
                      {formatDate(p.received_at, locale)}
                    </span>
                    <span className="detail-item__value">
                      {p.amount} {p.currency} · {p.method}
                      {p.is_voided ? (
                        <>
                          {" "}
                          <Badge tone="danger">
                            {t.hotelSubscription.voided}
                          </Badge>
                        </>
                      ) : null}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}

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
