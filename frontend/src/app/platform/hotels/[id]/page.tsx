"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { PageContainer } from "@/components/layout/PageContainer";
import {
  Alert,
  Badge,
  Button,
  Card,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  PageHeader,
  PasswordInput,
  SectionHeader,
  Select,
  useToast,
} from "@/components/ui";
import {
  activateHotel,
  activatePaid,
  cancelHotelSubscription,
  expireHotelSubscription,
  fetchSubscriptionHistory,
  getHotel,
  listPlans,
  listPlatformPayments,
  renewSubscription,
  setHotelManager,
  startTrial,
  suspendHotel,
  unsuspendHotel,
  updateHotel,
} from "@/lib/api/platform";
import { messageForError } from "@/lib/api/errors";
import type {
  Hotel,
  HotelSubscription,
  PlatformPayment,
  SubscriptionPlan,
} from "@/lib/api/types";
import {
  formatDate,
  hotelStatusLabel,
  hotelStatusTone,
  subscriptionStatusLabel,
  subscriptionStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function HotelDetailPage() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const params = useParams<{ id: string }>();
  const hotelId = Number(params.id);

  const [hotel, setHotel] = useState<Hotel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Await-first: no synchronous setState on the effect tick.
  const load = useCallback(async () => {
    try {
      const data = await getHotel(hotelId);
      setHotel(data);
      setError(null);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [hotelId, t]);

  useEffect(() => {
    load();
  }, [load]);

  const reload = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);

  return (
    <PageContainer>
      <PageHeader
        title={t.hotels.detailTitle}
        actions={
          <Link className="btn btn--secondary btn--sm" href="/platform/hotels">
            {t.hotels.backToList}
          </Link>
        }
      />

      {loading ? <LoadingState label={t.common.loading} /> : null}

      {!loading && error ? (
        <ErrorState
          title={t.states.errorTitle}
          message={error}
          retryLabel={t.common.retry}
          onRetry={reload}
        />
      ) : null}

      {!loading && !error && hotel ? (
        <>
          <Card>
            <div className="detail-grid">
              <div className="detail-item">
                <span className="detail-item__label">{t.hotels.name}</span>
                <span className="detail-item__value">{hotel.name}</span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">{t.hotels.slug}</span>
                <span className="detail-item__value">{hotel.slug}</span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">{t.common.status}</span>
                <span>
                  <Badge tone={hotelStatusTone(hotel.status)}>
                    {hotelStatusLabel(hotel.status, t)}
                  </Badge>
                </span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">{t.common.createdAt}</span>
                <span className="detail-item__value">
                  {formatDate(hotel.created_at, locale)}
                </span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">{t.hotels.city}</span>
                <span className="detail-item__value">
                  {[hotel.city, hotel.country].filter(Boolean).join(" · ") || "—"}
                </span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">{t.hotels.roomsCount}</span>
                <span className="detail-item__value">{hotel.rooms_count}</span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">{t.hotels.staffCount}</span>
                <span className="detail-item__value">{hotel.staff_count}</span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">
                  {t.hotels.reservationsCount}
                </span>
                <span className="detail-item__value">
                  {hotel.reservations_count}
                </span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">{t.hotels.publicListed}</span>
                <span>
                  <Badge tone={hotel.public_is_listed ? "success" : "neutral"}>
                    {hotel.public_is_listed ? t.common.yes : t.common.no}
                  </Badge>
                </span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">
                  {t.hotels.publicBookingEnabled}
                </span>
                <span>
                  <Badge tone={hotel.public_booking_enabled ? "success" : "neutral"}>
                    {hotel.public_booking_enabled ? t.common.yes : t.common.no}
                  </Badge>
                </span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">{t.hotels.trialUsed}</span>
                <span>
                  <Badge tone={hotel.trial_used ? "warning" : "neutral"}>
                    {hotel.trial_used ? t.common.yes : t.common.no}
                  </Badge>
                </span>
              </div>
            </div>
            {hotel.status === "suspended" && hotel.suspension_reason ? (
              <Alert tone="warning">
                {t.hotels.suspendedReasonLabel}: {hotel.suspension_reason}
                {hotel.status_changed_by ? ` — ${hotel.status_changed_by}` : ""}
              </Alert>
            ) : null}
            <div className="cluster" style={{ marginTop: "var(--space-3)" }}>
              {hotel.status === "setup" ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={async () => {
                    try {
                      await activateHotel(hotel.id);
                      notify(t.settings.saved);
                      load();
                    } catch (err) {
                      notify(messageForError(err, t), "error");
                    }
                  }}
                >
                  {t.hotels.activate}
                </Button>
              ) : null}
              {hotel.status === "suspended" ? (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={async () => {
                    try {
                      await unsuspendHotel(hotel.id);
                      notify(t.settings.saved);
                      load();
                    } catch (err) {
                      notify(messageForError(err, t), "error");
                    }
                  }}
                >
                  {t.hotels.unsuspend}
                </Button>
              ) : null}
            </div>
            {hotel.status === "active" ? (
              <InlineSuspendForm hotel={hotel} onDone={load} onNotify={notify} />
            ) : null}
          </Card>

          <SubscriptionCard hotel={hotel} onChanged={load} onNotify={notify} />

          <Card>
            <SectionHeader title={t.hotels.currentSubscription} />
            {hotel.current_subscription ? (
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-item__label">{t.subscriptions.plan}</span>
                  <span className="detail-item__value">
                    {hotel.current_subscription.plan_name}
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-item__label">{t.common.status}</span>
                  <span>
                    <Badge
                      tone={subscriptionStatusTone(
                        hotel.current_subscription.status,
                      )}
                    >
                      {subscriptionStatusLabel(
                        hotel.current_subscription.status,
                        t,
                      )}
                    </Badge>
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-item__label">
                    {t.subscriptions.startsAt}
                  </span>
                  <span className="detail-item__value">
                    {formatDate(hotel.current_subscription.starts_at, locale)}
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-item__label">
                    {t.subscriptions.endsAt}
                  </span>
                  <span className="detail-item__value">
                    {formatDate(hotel.current_subscription.ends_at, locale)}
                  </span>
                </div>
              </div>
            ) : (
              <p className="muted">{t.hotels.noSubscription}</p>
            )}
          </Card>

          <EditHotelCard hotel={hotel} onSaved={load} onNotify={notify} />
          <ManagerCard hotel={hotel} onSaved={load} onNotify={notify} />
        </>
      ) : null}
    </PageContainer>
  );
}

function EditHotelCard({
  hotel,
  onSaved,
  onNotify,
}: {
  hotel: Hotel;
  onSaved: () => void;
  onNotify: (message: string, tone?: "success" | "error") => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(hotel.name);
  const [slug, setSlug] = useState(hotel.slug);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // Phase 16: the status is deliberately NOT editable here — it changes
      // only through the audited activate/suspend/unsuspend actions.
      await updateHotel(hotel.id, { name, slug });
      onNotify(t.settings.saved);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionHeader title={t.hotels.editTitle} />
      <form className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.hotels.name} htmlFor="edit-name">
            <Input
              id="edit-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </FormField>
          <FormField label={t.hotels.slug} htmlFor="edit-slug">
            <Input
              id="edit-slug"
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
            />
          </FormField>
        </div>
        <div className="cluster">
          <Button type="submit" disabled={busy}>
            {busy ? t.common.saving : t.common.save}
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** Suspension from the detail page — the reason is mandatory and audited. */
function InlineSuspendForm({
  hotel,
  onDone,
  onNotify,
}: {
  hotel: Hotel;
  onDone: () => void;
  onNotify: (message: string, tone?: "success" | "error") => void;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return;
    setBusy(true);
    try {
      await suspendHotel(hotel.id, reason.trim());
      onNotify(t.settings.saved);
      onDone();
    } catch (err) {
      onNotify(messageForError(err, t), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="cluster" onSubmit={submit} noValidate style={{ marginTop: "var(--space-3)" }}>
      <FormField label={t.hotels.suspendReason} htmlFor="detail-suspend-reason">
        <Input
          id="detail-suspend-reason"
          value={reason}
          required
          onChange={(event) => setReason(event.target.value)}
        />
      </FormField>
      <Button type="submit" variant="danger" size="sm" loading={busy} disabled={!reason.trim()}>
        {t.hotels.suspend}
      </Button>
    </form>
  );
}

/** Current subscription + lifecycle actions + preserved history + manual
 * platform payments (never a gateway). */
function SubscriptionCard({
  hotel,
  onChanged,
  onNotify,
}: {
  hotel: Hotel;
  onChanged: () => void;
  onNotify: (message: string, tone?: "success" | "error") => void;
}) {
  const { t, locale } = useI18n();
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [history, setHistory] = useState<HotelSubscription[]>([]);
  const [payments, setPayments] = useState<PlatformPayment[]>([]);
  const [planId, setPlanId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadExtras = useCallback(async () => {
    try {
      const [planData, historyData, paymentData] = await Promise.all([
        listPlans({ is_active: "true", page_size: 100 }),
        fetchSubscriptionHistory(hotel.id),
        listPlatformPayments(hotel.id),
      ]);
      setPlans(planData.results);
      setHistory(historyData);
      setPayments(paymentData);
      if (planData.results.length > 0) {
        setPlanId((prev) => prev || String(planData.results[0].id));
      }
    } catch {
      // Non-blocking: the page still shows the hotel itself.
    }
  }, [hotel.id]);

  useEffect(() => {
    loadExtras();
  }, [loadExtras]);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    setBusy(true);
    try {
      await action();
      onNotify(t.settings.saved);
      onChanged();
      loadExtras();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const sub = hotel.current_subscription;
  const planOptions = plans.map((plan) => ({
    value: String(plan.id),
    label: `${plan.name} — ${plan.price} ${plan.currency}`,
  }));

  return (
    <Card>
      <SectionHeader
        title={t.hotels.subscriptionSection}
        description={t.hotels.subscriptionSectionDesc}
      />
      {error ? <Alert tone="error">{error}</Alert> : null}

      {sub ? (
        <div className="detail-grid">
          <div className="detail-item">
            <span className="detail-item__label">{t.subscriptions.plan}</span>
            <span className="detail-item__value">{sub.plan_name}</span>
          </div>
          <div className="detail-item">
            <span className="detail-item__label">{t.common.status}</span>
            <span>
              <Badge tone={subscriptionStatusTone(sub.status)}>
                {subscriptionStatusLabel(sub.status, t)}
              </Badge>
            </span>
          </div>
          <div className="detail-item">
            <span className="detail-item__label">{t.subscriptions.endsAt}</span>
            <span className="detail-item__value">
              {formatDate(sub.ends_at ?? sub.trial_ends_at, locale)}
            </span>
          </div>
        </div>
      ) : (
        <p className="muted">{t.hotels.noSubscription}</p>
      )}

      <div className="cluster">
        {!sub ? (
          <>
            <FormField label={t.subscriptions.plan} htmlFor="sub-plan">
              <Select
                id="sub-plan"
                value={planId}
                options={planOptions}
                onChange={(event) => setPlanId(event.target.value)}
              />
            </FormField>
            <Button
              size="sm"
              variant="secondary"
              disabled={busy || !planId || hotel.trial_used}
              onClick={() => run(() => startTrial(hotel.id, { plan: Number(planId) }))}
            >
              {t.subscriptions.startTrial}
            </Button>
            <Button
              size="sm"
              disabled={busy || !planId}
              onClick={() => run(() => activatePaid(hotel.id, { plan: Number(planId) }))}
            >
              {t.subscriptions.activatePaid}
            </Button>
          </>
        ) : (
          <>
            <Button
              size="sm"
              disabled={busy}
              onClick={() => run(() => renewSubscription(hotel.id, {}))}
            >
              {t.subscriptions.renew}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() => run(() => cancelHotelSubscription(hotel.id))}
            >
              {t.subscriptions.cancel}
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={busy}
              onClick={() => run(() => expireHotelSubscription(hotel.id))}
            >
              {t.subscriptions.expire}
            </Button>
          </>
        )}
      </div>
      {!sub && hotel.trial_used ? (
        <p className="muted">{t.subscriptions.trialAlreadyUsedHint}</p>
      ) : null}

      {history.length > 0 ? (
        <div>
          <h4>{t.hotels.subscriptionHistory}</h4>
          <ul className="mini-list">
            {history.map((row) => (
              <li key={row.id} className="mini-list__row">
                <span>{row.plan_name}</span>
                <Badge tone={subscriptionStatusTone(row.status)}>
                  {subscriptionStatusLabel(row.status, t)}
                </Badge>
                <span className="muted">
                  {formatDate(row.starts_at, locale)} →{" "}
                  {formatDate(row.ends_at ?? row.trial_ends_at, locale)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {payments.length > 0 ? (
        <div>
          <h4>{t.hotels.paymentsHistory}</h4>
          <ul className="mini-list">
            {payments.map((payment) => (
              <li key={payment.id} className="mini-list__row">
                <span>
                  {payment.amount} {payment.currency}
                </span>
                <span className="muted">
                  {t.subscriptions.methods[payment.method]}
                </span>
                <span className="muted">{formatDate(payment.received_at, locale)}</span>
                {payment.is_voided ? (
                  <Badge tone="danger">{t.subscriptions.voided}</Badge>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}

function ManagerCard({
  hotel,
  onSaved,
  onNotify,
}: {
  hotel: Hotel;
  onSaved: () => void;
  onNotify: (message: string, tone?: "success" | "error") => void;
}) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await setHotelManager(hotel.id, {
        email: email.trim(),
        full_name: fullName.trim(),
        password,
      });
      setEmail("");
      setFullName("");
      setPassword("");
      onNotify(t.settings.saved);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionHeader title={t.hotels.managerSection} />
      {hotel.primary_manager ? (
        <p className="muted">
          {hotel.primary_manager.full_name} · {hotel.primary_manager.email}
        </p>
      ) : (
        <p className="muted">{t.hotels.noManager}</p>
      )}
      <form className="stack" onSubmit={submit} noValidate style={{ marginTop: "var(--space-4)" }}>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.hotels.managerFullName} htmlFor="mgr-name">
            <Input
              id="mgr-name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
            />
          </FormField>
          <FormField label={t.hotels.managerEmail} htmlFor="mgr-email">
            <Input
              id="mgr-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </FormField>
          <FormField label={t.hotels.managerPassword} htmlFor="mgr-pass">
            <PasswordInput
              id="mgr-pass"
              value={password}
              showLabel={t.auth.showPassword}
              hideLabel={t.auth.hidePassword}
              onChange={(event) => setPassword(event.target.value)}
            />
          </FormField>
        </div>
        <div className="cluster">
          <Button type="submit" variant="secondary" disabled={busy}>
            {busy ? t.common.saving : t.hotels.assignManager}
          </Button>
        </div>
      </form>
    </Card>
  );
}
