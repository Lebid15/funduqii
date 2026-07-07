"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Package, Pencil, Plus, Trash2 } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import {
  Alert,
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  PageHeader,
  Select,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import {
  createPlan,
  deletePlan,
  listPlans,
  updatePlan,
  type PlanWriteBody,
} from "@/lib/api/platform";
import { messageForError } from "@/lib/api/errors";
import type { SubscriptionPlan } from "@/lib/api/types";
import { billingCycleLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function PlansPage() {
  const { t } = useI18n();
  const { notify } = useToast();

  const [rows, setRows] = useState<SubscriptionPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<SubscriptionPlan | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SubscriptionPlan | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  // Await-first: no synchronous setState on the effect tick.
  const load = useCallback(async () => {
    try {
      const data = await listPlans({ page_size: 100 });
      setRows(data.results);
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

  const reload = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);

  async function toggleActive(plan: SubscriptionPlan) {
    try {
      await updatePlan(plan.id, { is_active: !plan.is_active });
      notify(t.settings.saved);
      load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await deletePlan(deleteTarget.id);
      notify(t.settings.saved);
      setDeleteTarget(null);
      load();
    } catch (err) {
      notify(messageForError(err, t), "error");
      setDeleteTarget(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  const columns: Column<SubscriptionPlan>[] = [
    { key: "name", header: t.plans.name },
    { key: "slug", header: t.plans.slug },
    {
      key: "price",
      header: t.plans.price,
      render: (row) => `${row.price} ${row.currency}`,
    },
    {
      key: "billing_cycle",
      header: t.plans.billingCycle,
      render: (row) => billingCycleLabel(row.billing_cycle, t),
    },
    {
      key: "is_active",
      header: t.common.status,
      render: (row) => (
        <Badge tone={row.is_active ? "success" : "neutral"}>
          {row.is_active ? t.plans.active : t.plans.inactive}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (row) => (
        <div className="table__actions">
          <Button
            variant="secondary"
            size="sm"
            icon={Pencil}
            onClick={() => setEditing(row)}
          >
            {t.common.edit}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => toggleActive(row)}>
            {row.is_active ? t.plans.deactivate : t.plans.activate}
          </Button>
          <Button
            variant="danger"
            size="sm"
            icon={Trash2}
            disabled={row.is_in_use}
            title={row.is_in_use ? t.plans.inUseCannotDelete : undefined}
            onClick={() => setDeleteTarget(row)}
          >
            {t.common.delete}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t.plans.title}
        subtitle={t.plans.subtitle}
        actions={
          <Button icon={Plus} onClick={() => setCreating(true)}>
            {t.plans.create}
          </Button>
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

      {!loading && !error ? (
        rows.length === 0 ? (
          <EmptyState
            title={t.plans.empty}
            hint={t.plans.emptyHint}
            icon={Package}
            action={
              <Button icon={Plus} onClick={() => setCreating(true)}>
                {t.plans.create}
              </Button>
            }
          />
        ) : (
          <DataTable
            caption={t.plans.title}
            columns={columns}
            rows={rows}
            rowKey={(row) => row.id}
          />
        )
      ) : null}

      <PlanModal
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={() => {
          setCreating(false);
          notify(t.settings.saved);
          load();
        }}
      />
      <PlanModal
        open={editing !== null}
        plan={editing ?? undefined}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          notify(t.settings.saved);
          load();
        }}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t.plans.deleteConfirmTitle}
        body={t.plans.deleteConfirmBody}
        confirmLabel={t.common.delete}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        busy={deleteBusy}
        onConfirm={confirmDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </PageContainer>
  );
}

function PlanModal({
  open,
  plan,
  onClose,
  onSaved,
}: {
  open: boolean;
  plan?: SubscriptionPlan;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [price, setPrice] = useState("0");
  const [currency, setCurrency] = useState("USD");
  const [billingCycle, setBillingCycle] = useState("monthly");
  const [trialDays, setTrialDays] = useState("0");
  const [roomLimit, setRoomLimit] = useState("");
  const [userLimit, setUserLimit] = useState("");
  const [features, setFeatures] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Reset the form whenever the modal opens for a (different) plan.
  useEffect(() => {
    if (!open) return;
    setName(plan?.name ?? "");
    setSlug(plan?.slug ?? "");
    setDescription(plan?.description ?? "");
    setPrice(plan?.price ?? "0");
    setCurrency(plan?.currency ?? "USD");
    setBillingCycle(plan?.billing_cycle ?? "monthly");
    setTrialDays(String(plan?.trial_days ?? 0));
    setRoomLimit(plan?.room_limit != null ? String(plan.room_limit) : "");
    setUserLimit(plan?.user_limit != null ? String(plan.user_limit) : "");
    setFeatures((plan?.feature_codes ?? []).join(", "));
    setError(null);
  }, [open, plan]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const body: PlanWriteBody = {
      name: name.trim(),
      slug: slug.trim(),
      description: description.trim(),
      price,
      currency: currency.trim() || "USD",
      billing_cycle: billingCycle as PlanWriteBody["billing_cycle"],
      trial_days: Number(trialDays) || 0,
      room_limit: roomLimit === "" ? null : Number(roomLimit),
      user_limit: userLimit === "" ? null : Number(userLimit),
      feature_codes: features
        .split(",")
        .map((code) => code.trim())
        .filter(Boolean),
    };
    setBusy(true);
    try {
      if (plan) {
        await updatePlan(plan.id, body);
      } else {
        await createPlan(body);
      }
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
      title={plan ? t.plans.editTitle : t.plans.createTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="plan-form" type="submit" disabled={busy}>
            {busy ? t.common.saving : t.common.save}
          </Button>
        </>
      }
    >
      <form id="plan-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.plans.name} htmlFor="plan-name">
            <Input
              id="plan-name"
              value={name}
              required
              onChange={(event) => setName(event.target.value)}
            />
          </FormField>
          <FormField label={t.plans.slug} htmlFor="plan-slug">
            <Input
              id="plan-slug"
              value={slug}
              required
              onChange={(event) => setSlug(event.target.value)}
            />
          </FormField>
          <FormField label={t.plans.price} htmlFor="plan-price">
            <Input
              id="plan-price"
              type="number"
              min="0"
              step="0.01"
              value={price}
              onChange={(event) => setPrice(event.target.value)}
            />
          </FormField>
          <FormField label={t.plans.currency} htmlFor="plan-currency">
            <Input
              id="plan-currency"
              value={currency}
              maxLength={3}
              onChange={(event) => setCurrency(event.target.value.toUpperCase())}
            />
          </FormField>
          <FormField label={t.plans.billingCycle} htmlFor="plan-cycle">
            <Select
              id="plan-cycle"
              value={billingCycle}
              options={[
                { value: "monthly", label: t.plans.cycleMonthly },
                { value: "yearly", label: t.plans.cycleYearly },
                { value: "custom", label: t.plans.cycleCustom },
              ]}
              onChange={(event) => setBillingCycle(event.target.value)}
            />
          </FormField>
          <FormField label={t.plans.trialDays} htmlFor="plan-trial">
            <Input
              id="plan-trial"
              type="number"
              min="0"
              value={trialDays}
              onChange={(event) => setTrialDays(event.target.value)}
            />
          </FormField>
          <FormField
            label={t.plans.roomLimit}
            htmlFor="plan-rooms"
            hint={t.plans.unlimited}
          >
            <Input
              id="plan-rooms"
              type="number"
              min="0"
              value={roomLimit}
              onChange={(event) => setRoomLimit(event.target.value)}
            />
          </FormField>
          <FormField
            label={t.plans.userLimit}
            htmlFor="plan-users"
            hint={t.plans.unlimited}
          >
            <Input
              id="plan-users"
              type="number"
              min="0"
              value={userLimit}
              onChange={(event) => setUserLimit(event.target.value)}
            />
          </FormField>
        </div>
        <FormField
          label={t.plans.features}
          htmlFor="plan-features"
          hint={t.plans.featuresHint}
        >
          <Input
            id="plan-features"
            value={features}
            onChange={(event) => setFeatures(event.target.value)}
          />
        </FormField>
        <FormField label={t.plans.description} htmlFor="plan-desc">
          <Textarea
            id="plan-desc"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}
