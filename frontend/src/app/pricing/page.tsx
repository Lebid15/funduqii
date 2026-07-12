"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { PublicShell } from "@/components/public/PublicShell";
import { Badge, Card, LoadingState } from "@/components/ui";
import { getPublicPlans } from "@/lib/api/public";
import type { PublicPlan } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * The PUBLIC plans & pricing page (subscriptions final closure). It renders the
 * SAME SubscriptionPlan catalog the owner panel manages — read from the public
 * API, never a hardcoded frontend list. Only active + public plans are returned
 * by the backend. There is NO checkout, NO card entry and NO payment gateway:
 * the CTA only points visitors to get in touch.
 */
export default function PricingPage() {
  return (
    <PublicShell>
      <PricingContent />
    </PublicShell>
  );
}

function PricingContent() {
  const { t } = useI18n();
  const [plans, setPlans] = useState<PublicPlan[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPublicPlans()
      .then((data) => setPlans(data.plans))
      .catch(() => setPlans([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <section className="public-hero">
        <h1 className="public-hero__title">{t.pricing.title}</h1>
        <p className="public-hero__subtitle">{t.pricing.subtitle}</p>
      </section>

      <section className="public-section">
        {loading ? (
          <LoadingState label={t.common.loading} />
        ) : plans.length === 0 ? (
          <p className="muted">{t.pricing.empty}</p>
        ) : (
          <div className="public-hotel-grid">
            {plans.map((plan) => (
              <PlanCard key={plan.id} plan={plan} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function PlanCard({ plan }: { plan: PublicPlan }) {
  const { t } = useI18n();

  const roomsLabel =
    plan.room_limit === null
      ? t.pricing.unlimitedRooms
      : t.pricing.upToRooms.replace("{n}", String(plan.room_limit));
  const staffLabel =
    plan.user_limit === null
      ? t.pricing.unlimitedStaff
      : t.pricing.upToStaff.replace("{n}", String(plan.user_limit));

  return (
    <Card>
      <h3>{plan.name}</h3>
      {plan.description ? <p className="muted">{plan.description}</p> : null}

      <p className="public-plan__price">
        <strong>
          {plan.price} {plan.currency}
        </strong>
        <span className="muted"> {t.pricing.perMonth}</span>
      </p>
      {plan.price_yearly ? (
        <p className="muted">
          {plan.price_yearly} {plan.currency} {t.pricing.perYear}
        </p>
      ) : null}

      <ul>
        <li>{roomsLabel}</li>
        <li>{staffLabel}</li>
        {plan.trial_days > 0 ? (
          <li>{t.pricing.trialDays.replace("{n}", String(plan.trial_days))}</li>
        ) : null}
      </ul>

      {plan.feature_codes.length > 0 ? (
        <div>
          <span className="detail-item__label">{t.pricing.features}</span>
          <div>
            {plan.feature_codes.map((f) => (
              <Badge key={f} tone="neutral">
                {f}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}

      <div className="cluster" style={{ marginTop: "0.75rem" }}>
        <Link href="/" className="btn btn--secondary">
          {t.pricing.ctaContact}
        </Link>
      </div>
    </Card>
  );
}
