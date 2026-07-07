"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { CreditCard, Plus } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  Modal,
  PageHeader,
  Pagination,
  Select,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import {
  createSubscription,
  listHotels,
  listPlans,
  listSubscriptions,
  updateSubscription,
  type SubscriptionCreateBody,
} from "@/lib/api/platform";
import { messageForError } from "@/lib/api/errors";
import type {
  Hotel,
  HotelSubscription,
  SubscriptionPlan,
} from "@/lib/api/types";
import {
  formatDate,
  subscriptionStatusLabel,
  subscriptionStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

const PAGE_SIZE = 25;

export default function SubscriptionsPage() {
  const { t, locale } = useI18n();
  const { notify } = useToast();

  const [rows, setRows] = useState<HotelSubscription[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [cancelTarget, setCancelTarget] = useState<HotelSubscription | null>(
    null,
  );
  const [cancelBusy, setCancelBusy] = useState(false);

  // Await-first: no synchronous setState on the effect tick.
  const load = useCallback(async () => {
    try {
      const data = await listSubscriptions({
        page,
        status: status || undefined,
      });
      setRows(data.results);
      setCount(data.count);
      setError(null);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, status, t]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  const statusOptions = useMemo(
    () => [
      { value: "trial", label: t.subscriptions.statusTrial },
      { value: "active", label: t.subscriptions.statusActive },
      { value: "past_due", label: t.subscriptions.statusPastDue },
      { value: "expired", label: t.subscriptions.statusExpired },
      { value: "cancelled", label: t.subscriptions.statusCancelled },
    ],
    [t],
  );

  async function confirmCancel() {
    if (!cancelTarget) return;
    setCancelBusy(true);
    try {
      await updateSubscription(cancelTarget.id, { status: "cancelled" });
      notify(t.settings.saved);
      setCancelTarget(null);
      load();
    } catch (err) {
      notify(messageForError(err, t), "error");
      setCancelTarget(null);
    } finally {
      setCancelBusy(false);
    }
  }

  const isLive = (s: HotelSubscription) =>
    s.status === "trial" || s.status === "active" || s.status === "past_due";

  const columns: Column<HotelSubscription>[] = [
    { key: "hotel_name", header: t.subscriptions.hotel },
    { key: "plan_name", header: t.subscriptions.plan },
    {
      key: "status",
      header: t.common.status,
      render: (row) => (
        <Badge tone={subscriptionStatusTone(row.status)}>
          {subscriptionStatusLabel(row.status, t)}
        </Badge>
      ),
    },
    {
      key: "starts_at",
      header: t.subscriptions.startsAt,
      render: (row) => formatDate(row.starts_at, locale),
    },
    {
      key: "ends_at",
      header: t.subscriptions.endsAt,
      render: (row) => formatDate(row.ends_at, locale),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (row) =>
        isLive(row) ? (
          <div className="table__actions">
            <Button
              variant="danger"
              size="sm"
              onClick={() => setCancelTarget(row)}
            >
              {t.subscriptions.cancel}
            </Button>
          </div>
        ) : (
          <span className="muted">{t.common.notAvailable}</span>
        ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t.subscriptions.title}
        subtitle={t.subscriptions.subtitle}
        actions={
          <Button icon={Plus} onClick={() => setCreating(true)}>
            {t.subscriptions.create}
          </Button>
        }
      />

      <Card>
        <FilterBar>
          <FormField label={t.subscriptions.filterStatus} htmlFor="sub-status">
            <Select
              id="sub-status"
              value={status}
              placeholder={t.common.all}
              options={statusOptions}
              onChange={(event) => {
                setLoading(true);
                setPage(1);
                setStatus(event.target.value);
              }}
            />
          </FormField>
        </FilterBar>
      </Card>

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

      {!loading && !error ? (
        rows.length === 0 ? (
          <EmptyState
            title={t.subscriptions.empty}
            hint={t.subscriptions.emptyHint}
            icon={CreditCard}
            action={
              <Button icon={Plus} onClick={() => setCreating(true)}>
                {t.subscriptions.create}
              </Button>
            }
          />
        ) : (
          <>
            <DataTable
              caption={t.subscriptions.title}
              columns={columns}
              rows={rows}
              rowKey={(row) => row.id}
            />
            <Pagination
              page={page}
              totalPages={totalPages}
              onPageChange={(next) => {
                setLoading(true);
                setPage(next);
              }}
              labels={{
                previous: t.pagination.previous,
                next: t.pagination.next,
                status: t.pagination.page
                  .replace("{page}", String(page))
                  .replace("{total}", String(totalPages)),
              }}
            />
          </>
        )
      ) : null}

      <CreateSubscriptionModal
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={() => {
          setCreating(false);
          notify(t.settings.saved);
          setPage(1);
          load();
        }}
      />

      <ConfirmDialog
        open={cancelTarget !== null}
        title={t.subscriptions.cancelConfirmTitle}
        body={t.subscriptions.cancelConfirmBody}
        confirmLabel={t.subscriptions.cancel}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        busy={cancelBusy}
        onConfirm={confirmCancel}
        onClose={() => setCancelTarget(null)}
      />
    </PageContainer>
  );
}

function CreateSubscriptionModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [hotels, setHotels] = useState<Hotel[]>([]);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [hotel, setHotel] = useState("");
  const [plan, setPlan] = useState("");
  const [kind, setKind] = useState<"trial" | "paid">("trial");
  const [trialDays, setTrialDays] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [optionsError, setOptionsError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setHotel("");
    setPlan("");
    setKind("trial");
    setTrialDays("");
    setNotes("");
    setError(null);
    setOptionsError(null);
    (async () => {
      try {
        const [hotelData, planData] = await Promise.all([
          listHotels({ page_size: 100 }),
          listPlans({ page_size: 100, is_active: "true" }),
        ]);
        setHotels(hotelData.results);
        setPlans(planData.results);
      } catch (err) {
        setOptionsError(messageForError(err, t));
      }
    })();
  }, [open, t]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!hotel || !plan) {
      setError(t.errors.validation);
      return;
    }
    const body: SubscriptionCreateBody = {
      hotel: Number(hotel),
      plan: Number(plan),
      kind,
      notes: notes.trim() || undefined,
    };
    if (kind === "trial" && trialDays !== "") {
      body.trial_days = Number(trialDays);
    }
    setBusy(true);
    try {
      await createSubscription(body);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.subscriptions.createTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="sub-form" type="submit" disabled={busy}>
            {busy ? t.common.creating : t.common.create}
          </Button>
        </>
      }
    >
      <form id="sub-form" className="stack" onSubmit={submit} noValidate>
        {optionsError ? <Alert tone="error">{optionsError}</Alert> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={t.subscriptions.hotel} htmlFor="sub-hotel">
          <Select
            id="sub-hotel"
            value={hotel}
            placeholder={t.subscriptions.selectHotel}
            options={hotels.map((h) => ({
              value: String(h.id),
              label: `${h.name} (${h.slug})`,
            }))}
            onChange={(event) => setHotel(event.target.value)}
          />
        </FormField>
        <FormField label={t.subscriptions.plan} htmlFor="sub-plan">
          <Select
            id="sub-plan"
            value={plan}
            placeholder={t.subscriptions.selectPlan}
            options={plans.map((p) => ({
              value: String(p.id),
              label: p.name,
            }))}
            onChange={(event) => setPlan(event.target.value)}
          />
        </FormField>
        <FormField label={t.subscriptions.kind} htmlFor="sub-kind">
          <Select
            id="sub-kind"
            value={kind}
            options={[
              { value: "trial", label: t.subscriptions.kindTrial },
              { value: "paid", label: t.subscriptions.kindPaid },
            ]}
            onChange={(event) => setKind(event.target.value as "trial" | "paid")}
          />
        </FormField>
        {kind === "trial" ? (
          <FormField label={t.subscriptions.trialDays} htmlFor="sub-trial">
            <Input
              id="sub-trial"
              type="number"
              min="0"
              value={trialDays}
              onChange={(event) => setTrialDays(event.target.value)}
            />
          </FormField>
        ) : null}
        <FormField label={t.subscriptions.notes} htmlFor="sub-notes">
          <Textarea
            id="sub-notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}
