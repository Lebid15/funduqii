"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  CalendarClock,
  CreditCard,
  Gauge,
  Inbox,
  LayoutGrid,
  Receipt,
} from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  ErrorState,
  FormField,
  LoadingState,
  Modal,
  PageHeader,
  SectionHeader,
  Textarea,
  useToast,
  type BadgeTone,
} from "@/components/ui";
import {
  cancelMyRequest,
  getAvailablePlans,
  getProfile,
  listMyRequests,
  submitChangeRequest,
} from "@/lib/api/hotel";
import { messageForError } from "@/lib/api/errors";
import type {
  AvailablePlan,
  AvailablePlansResponse,
  ChangeRequestKind,
  ChangeRequestStatus,
  EntitlementDimension,
  HotelSubscriptionState,
  SubscriptionChangeRequest,
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

const STATUS_TONE: Record<ChangeRequestStatus, BadgeTone> = {
  under_review: "warning",
  accepted: "info",
  executed: "success",
  rejected: "danger",
  cancelled: "neutral",
};

const PLAN_STATE_TONE: Record<AvailablePlan["state"], BadgeTone> = {
  current: "primary",
  upgradeable: "success",
  available: "info",
  unavailable: "neutral",
};

interface SubmitTarget {
  kind: ChangeRequestKind;
  plan?: AvailablePlan;
}

/**
 * The hotel console's subscription page (sidebar "الاشتراك والباقات").
 *
 * The current subscription, usage and payment history stay READ-ONLY (the
 * platform owner drives the lifecycle). What is new (§8.4/§8.5): the hotel can
 * see the plans it may move to — each with its per-hotel state — and SUBMIT a
 * change request (new subscription / renewal / upgrade) for the platform to
 * review. There is still no payment gateway and no self-service checkout here;
 * a request is an internal review, applied only when the owner accepts + applies
 * it. All eligibility is decided by the backend, never here.
 */
export default function HotelSubscriptionPage() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [state, setState] = useState<HotelSubscriptionState | null>(null);
  const [plansData, setPlansData] = useState<AvailablePlansResponse | null>(null);
  const [requests, setRequests] = useState<SubscriptionChangeRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitTarget, setSubmitTarget] = useState<SubmitTarget | null>(null);
  const [cancelTarget, setCancelTarget] = useState<SubscriptionChangeRequest | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [profile, plans, reqs] = await Promise.all([
        getProfile(),
        getAvailablePlans(),
        listMyRequests(),
      ]);
      setState(profile.subscription_state);
      setPlansData(plans);
      setRequests(reqs);
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

  // A hotel may hold at most one OPEN request (under_review or accepted).
  const hasOpenRequest = useMemo(
    () =>
      requests.some(
        (r) => r.status === "under_review" || r.status === "accepted",
      ),
    [requests],
  );
  const suspended = state?.suspended ?? false;
  const canAct = !suspended && !hasOpenRequest;

  async function doSubmit(note: string) {
    if (!submitTarget) return;
    setBusy(true);
    try {
      await submitChangeRequest({
        kind: submitTarget.kind,
        requested_plan: submitTarget.plan?.id,
        hotel_note: note.trim() || undefined,
      });
      notify(t.hotelSubscription.requestSubmitted);
      setSubmitTarget(null);
      setLoading(true);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusy(false);
    }
  }

  async function confirmCancel() {
    if (!cancelTarget) return;
    setBusy(true);
    try {
      await cancelMyRequest(cancelTarget.id);
      notify(t.hotelSubscription.requestCancelled);
      setCancelTarget(null);
      setLoading(true);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
      setCancelTarget(null);
    } finally {
      setBusy(false);
    }
  }

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
            {plansData?.can_request_renewal ? (
              <div style={{ marginTop: "1rem" }}>
                <Button
                  icon={CalendarClock}
                  variant="secondary"
                  disabled={!canAct}
                  onClick={() =>
                    setSubmitTarget({ kind: "renewal" })
                  }
                >
                  {t.hotelSubscription.requestRenewal}
                </Button>
              </div>
            ) : null}
          </Card>

          {state.terms ? (
            <Card>
              <SectionHeader title={t.hotelSubscription.usageTitle} icon={Gauge} />
              <div className="detail-grid">
                {dimensionRow(t.hotelSubscription.rooms, state.entitlements.rooms)}
                {dimensionRow(t.hotelSubscription.staff, state.entitlements.staff)}
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

          {/* §8.4 — available plans with per-hotel state */}
          <Card>
            <SectionHeader
              title={t.hotelSubscription.availablePlansTitle}
              description={t.hotelSubscription.availablePlansDesc}
              icon={LayoutGrid}
            />
            {hasOpenRequest ? (
              <Alert tone="info">{t.hotelSubscription.pendingNotice}</Alert>
            ) : null}
            {(plansData?.plans.length ?? 0) === 0 ? (
              <p className="muted">{t.hotelSubscription.noPlans}</p>
            ) : (
              <div
                style={{
                  display: "grid",
                  gap: "1rem",
                  gridTemplateColumns: "repeat(auto-fill, minmax(15rem, 1fr))",
                  marginTop: "0.75rem",
                }}
              >
                {(plansData?.plans ?? []).map((plan) => (
                  <PlanCard
                    key={plan.id}
                    plan={plan}
                    canAct={canAct}
                    onRequest={() =>
                      setSubmitTarget({
                        kind: plan.request_kind ?? "new_subscription",
                        plan,
                      })
                    }
                  />
                ))}
              </div>
            )}
          </Card>

          {/* §8.5 — the hotel's own requests */}
          <Card>
            <SectionHeader
              title={t.hotelSubscription.myRequestsTitle}
              description={t.hotelSubscription.myRequestsDesc}
              icon={Inbox}
            />
            {requests.length === 0 ? (
              <p className="muted">{t.hotelSubscription.noRequests}</p>
            ) : (
              <div className="stack">
                {requests.map((req) => (
                  <div
                    key={req.id}
                    className="detail-item"
                    style={{ alignItems: "flex-start" }}
                  >
                    <span className="detail-item__label">
                      {t.subscriptionRequests.kind[req.kind]}
                      {req.requested_plan_name ? ` · ${req.requested_plan_name}` : ""}
                      <span className="muted">
                        {" "}
                        · {formatDate(req.created_at, locale)}
                      </span>
                    </span>
                    <span className="detail-item__value">
                      <Badge tone={STATUS_TONE[req.status]}>
                        {t.subscriptionRequests.status[req.status]}
                      </Badge>
                      {req.admin_note ? (
                        <span className="muted">
                          {" "}
                          · {t.hotelSubscription.decisionNote}: {req.admin_note}
                        </span>
                      ) : null}
                      {req.status === "under_review" ? (
                        <>
                          {" "}
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => setCancelTarget(req)}
                          >
                            {t.hotelSubscription.cancelRequest}
                          </Button>
                        </>
                      ) : null}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

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
        </>
      ) : null}

      <SubmitRequestModal
        target={submitTarget}
        busy={busy}
        onClose={() => setSubmitTarget(null)}
        onSubmit={doSubmit}
      />

      <ConfirmDialog
        open={cancelTarget !== null}
        title={t.hotelSubscription.cancelConfirmTitle}
        body={t.hotelSubscription.cancelConfirmBody}
        confirmLabel={t.hotelSubscription.cancelRequest}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        busy={busy}
        onConfirm={confirmCancel}
        onClose={() => setCancelTarget(null)}
      />
    </PageContainer>
  );
}

function PlanCard({
  plan,
  canAct,
  onRequest,
}: {
  plan: AvailablePlan;
  canAct: boolean;
  onRequest: () => void;
}) {
  const { t } = useI18n();
  const actionLabel =
    plan.request_kind === "plan_change"
      ? t.hotelSubscription.requestUpgrade
      : t.hotelSubscription.subscribe;
  return (
    <div
      className="card"
      style={{
        border: "1px solid var(--border, #e5e7eb)",
        borderRadius: "0.75rem",
        padding: "1rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
      }}
    >
      <div className="cluster" style={{ justifyContent: "space-between" }}>
        <strong>{plan.name}</strong>
        <Badge tone={PLAN_STATE_TONE[plan.state]}>
          {t.subscriptionRequests.planState[plan.state]}
        </Badge>
      </div>
      <div className="detail-item__value">
        {plan.price} {plan.currency}
        <span className="muted">
          {" "}
          · {billingCycleLabel(plan.billing_cycle, t)}
        </span>
      </div>
      {plan.description ? (
        <p className="muted" style={{ margin: 0 }}>
          {plan.description}
        </p>
      ) : null}
      <div className="muted" style={{ fontSize: "0.85em" }}>
        {t.hotelSubscription.rooms}: {plan.room_limit ?? t.entitlements.unlimited}
        {" · "}
        {t.hotelSubscription.staff}: {plan.user_limit ?? t.entitlements.unlimited}
      </div>
      {plan.feature_codes.length > 0 ? (
        <div>
          {plan.feature_codes.map((f) => (
            <Badge key={f} tone="neutral">
              {f}
            </Badge>
          ))}
        </div>
      ) : null}
      {plan.requestable ? (
        <div style={{ marginTop: "auto" }}>
          <Button size="sm" disabled={!canAct} onClick={onRequest}>
            {actionLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function SubmitRequestModal({
  target,
  busy,
  onClose,
  onSubmit,
}: {
  target: SubmitTarget | null;
  busy: boolean;
  onClose: () => void;
  onSubmit: (note: string) => void;
}) {
  const { t } = useI18n();
  const [note, setNote] = useState("");

  useEffect(() => {
    if (target) setNote("");
  }, [target]);

  const kindLabel = target ? t.subscriptionRequests.kind[target.kind] : "";

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit(note);
  }

  return (
    <Modal
      open={target !== null}
      onClose={onClose}
      title={t.hotelSubscription.requestModalTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="request-form" type="submit" disabled={busy}>
            {busy ? t.hotelSubscription.submitting : t.hotelSubscription.submit}
          </Button>
        </>
      }
    >
      <form id="request-form" className="stack" onSubmit={submit} noValidate>
        <p>
          {kindLabel}
          {target?.plan ? ` · ${target.plan.name}` : ""}
        </p>
        <FormField label={t.hotelSubscription.noteLabel} htmlFor="request-note">
          <Textarea
            id="request-note"
            value={note}
            placeholder={t.hotelSubscription.notePlaceholder}
            onChange={(event) => setNote(event.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}
