"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Inbox } from "lucide-react";

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
  Select,
  Textarea,
  useToast,
  type BadgeTone,
  type Column,
} from "@/components/ui";
import {
  acceptChangeRequest,
  cancelChangeRequest,
  executeChangeRequest,
  listChangeRequests,
  rejectChangeRequest,
} from "@/lib/api/platform";
import { messageForError } from "@/lib/api/errors";
import type {
  ChangeRequestStatus,
  PlatformChangeRequest,
  PlatformPaymentMethod,
} from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

const STATUS_TONE: Record<ChangeRequestStatus, BadgeTone> = {
  under_review: "warning",
  accepted: "info",
  executed: "success",
  rejected: "danger",
  cancelled: "neutral",
};

const METHODS: PlatformPaymentMethod[] = [
  "cash",
  "bank_transfer",
  "manual",
  "other",
];

type Action = "accept" | "reject" | "execute" | "cancel";

/**
 * Platform-owner review of hotel-submitted subscription requests (§8.5).
 *
 * Two-step: the owner ACCEPTS a request, then APPLIES it — applying runs the
 * matching lifecycle service on the backend (activate / renew / change plan)
 * with a fresh billing cycle, and can record an optional MANUAL payment. Reject
 * requires a reason. Every decision is re-validated server-side.
 */
export default function SubscriptionRequestsPage() {
  const { t, locale } = useI18n();
  const { notify } = useToast();

  const [rows, setRows] = useState<PlatformChangeRequest[]>([]);
  const [status, setStatus] = useState("open");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<{
    type: Action;
    req: PlatformChangeRequest;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await listChangeRequests({
        status: status || undefined,
      });
      setRows(data);
      setError(null);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [status, t]);

  useEffect(() => {
    load();
  }, [load]);

  const statusOptions = useMemo(
    () => [
      { value: "open", label: t.subscriptionRequests.filterOpen },
      { value: "", label: t.common.all },
      {
        value: "under_review",
        label: t.subscriptionRequests.status.under_review,
      },
      { value: "accepted", label: t.subscriptionRequests.status.accepted },
      { value: "executed", label: t.subscriptionRequests.status.executed },
      { value: "rejected", label: t.subscriptionRequests.status.rejected },
      { value: "cancelled", label: t.subscriptionRequests.status.cancelled },
    ],
    [t],
  );

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      notify(t.subscriptionRequests.done);
      setAction(null);
      setLoading(true);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<PlatformChangeRequest>[] = [
    { key: "hotel_name", header: t.subscriptionRequests.colHotel },
    {
      key: "kind",
      header: t.subscriptionRequests.colKind,
      render: (row) => t.subscriptionRequests.kind[row.kind],
    },
    {
      key: "requested_plan_name",
      header: t.subscriptionRequests.colPlan,
      render: (row) => row.requested_plan_name ?? "—",
    },
    {
      key: "status",
      header: t.subscriptionRequests.colStatus,
      render: (row) => (
        <Badge tone={STATUS_TONE[row.status]}>
          {t.subscriptionRequests.status[row.status]}
        </Badge>
      ),
    },
    {
      key: "created_at",
      header: t.subscriptionRequests.colSubmitted,
      render: (row) => formatDate(row.created_at, locale),
    },
    {
      key: "requested_by",
      header: t.subscriptionRequests.colRequestedBy,
      render: (row) => row.requested_by ?? "—",
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (row) => {
        if (row.status === "under_review") {
          return (
            <div className="table__actions">
              <Button
                size="sm"
                onClick={() => setAction({ type: "accept", req: row })}
              >
                {t.subscriptionRequests.accept}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setAction({ type: "reject", req: row })}
              >
                {t.subscriptionRequests.reject}
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => setAction({ type: "cancel", req: row })}
              >
                {t.subscriptionRequests.cancel}
              </Button>
            </div>
          );
        }
        if (row.status === "accepted") {
          return (
            <div className="table__actions">
              <Button
                size="sm"
                onClick={() => setAction({ type: "execute", req: row })}
              >
                {t.subscriptionRequests.execute}
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => setAction({ type: "cancel", req: row })}
              >
                {t.subscriptionRequests.cancel}
              </Button>
            </div>
          );
        }
        return <span className="muted">{t.common.notAvailable}</span>;
      },
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t.subscriptionRequests.title}
        subtitle={t.subscriptionRequests.subtitle}
      />

      <Card>
        <FilterBar>
          <FormField
            label={t.subscriptionRequests.filterStatus}
            htmlFor="req-status"
          >
            <Select
              id="req-status"
              value={status}
              options={statusOptions}
              onChange={(event) => {
                setLoading(true);
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
            title={t.subscriptionRequests.empty}
            hint={t.subscriptionRequests.emptyHint}
            icon={Inbox}
          />
        ) : (
          <DataTable
            caption={t.subscriptionRequests.title}
            columns={columns}
            rows={rows}
            rowKey={(row) => row.id}
          />
        )
      ) : null}

      {/* Accept — confirm only (applying is a separate step). */}
      <ConfirmDialog
        open={action?.type === "accept"}
        title={t.subscriptionRequests.acceptTitle}
        body={t.subscriptionRequests.acceptBody}
        confirmLabel={t.subscriptionRequests.accept}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        busy={busy}
        onConfirm={() =>
          action ? run(() => acceptChangeRequest(action.req.id)) : undefined
        }
        onClose={() => setAction(null)}
      />

      {/* Cancel — owner withdraws an open request. */}
      <ConfirmDialog
        open={action?.type === "cancel"}
        title={t.subscriptionRequests.cancelTitle}
        body={t.subscriptionRequests.cancelBody}
        confirmLabel={t.subscriptionRequests.cancel}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        busy={busy}
        onConfirm={() =>
          action ? run(() => cancelChangeRequest(action.req.id)) : undefined
        }
        onClose={() => setAction(null)}
      />

      <RejectModal
        open={action?.type === "reject"}
        busy={busy}
        onClose={() => setAction(null)}
        onReject={(reason) =>
          action ? run(() => rejectChangeRequest(action.req.id, reason)) : undefined
        }
      />

      <ExecuteModal
        open={action?.type === "execute"}
        busy={busy}
        onClose={() => setAction(null)}
        onExecute={(body) =>
          action ? run(() => executeChangeRequest(action.req.id, body)) : undefined
        }
      />
    </PageContainer>
  );
}

function RejectModal({
  open,
  busy,
  onClose,
  onReject,
}: {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onReject: (reason: string) => void;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setReason("");
      setError(null);
    }
  }, [open]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) {
      setError(t.subscriptionRequests.errors.reasonRequired);
      return;
    }
    onReject(reason.trim());
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.subscriptionRequests.rejectTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button
            form="reject-form"
            type="submit"
            variant="danger"
            disabled={busy}
          >
            {t.subscriptionRequests.reject}
          </Button>
        </>
      }
    >
      <form id="reject-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField
          label={t.subscriptionRequests.rejectReasonLabel}
          htmlFor="reject-reason"
        >
          <Textarea
            id="reject-reason"
            value={reason}
            placeholder={t.subscriptionRequests.rejectReasonPlaceholder}
            onChange={(event) => setReason(event.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

interface ExecuteBody {
  notes?: string;
  payment_amount?: string;
  payment_method?: PlatformPaymentMethod;
  payment_reference?: string;
}

function ExecuteModal({
  open,
  busy,
  onClose,
  onExecute,
}: {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onExecute: (body: ExecuteBody) => void;
}) {
  const { t } = useI18n();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<PlatformPaymentMethod>("cash");
  const [reference, setReference] = useState("");

  useEffect(() => {
    if (open) {
      setAmount("");
      setMethod("cash");
      setReference("");
    }
  }, [open]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const body: ExecuteBody = {};
    if (amount.trim()) {
      body.payment_amount = amount.trim();
      body.payment_method = method;
      if (reference.trim()) body.payment_reference = reference.trim();
    }
    onExecute(body);
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.subscriptionRequests.executeTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="execute-form" type="submit" disabled={busy}>
            {t.subscriptionRequests.execute}
          </Button>
        </>
      }
    >
      <form id="execute-form" className="stack" onSubmit={submit} noValidate>
        <p className="muted">{t.subscriptionRequests.executeBody}</p>
        <p className="detail-item__label">
          {t.subscriptionRequests.recordPaymentOptional}
        </p>
        <FormField
          label={t.subscriptionRequests.paymentAmount}
          htmlFor="exec-amount"
        >
          <Input
            id="exec-amount"
            type="number"
            min="0"
            step="0.01"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </FormField>
        <FormField
          label={t.subscriptionRequests.paymentMethod}
          htmlFor="exec-method"
        >
          <Select
            id="exec-method"
            value={method}
            options={METHODS.map((m) => ({
              value: m,
              label: t.subscriptions.methods[m],
            }))}
            onChange={(event) =>
              setMethod(event.target.value as PlatformPaymentMethod)
            }
          />
        </FormField>
        <FormField
          label={t.subscriptionRequests.paymentReference}
          htmlFor="exec-ref"
        >
          <Input
            id="exec-ref"
            value={reference}
            onChange={(event) => setReference(event.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}
