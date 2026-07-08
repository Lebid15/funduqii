"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ArrowLeftRight, Clock, Lock, PlayCircle } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  SectionHeader,
  StatCard,
  useToast,
} from "@/components/ui";
import { closeShift, getCurrentShift, openShift } from "@/lib/api/shifts";
import { messageForError } from "@/lib/api/errors";
import type { Shift, ShiftCashSummary } from "@/lib/api/types";
import { formatDateTime, shiftStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { HandoverFormModal } from "./HandoversTab";

export function CurrentShiftTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const c = t.shifts.current;

  const [shift, setShift] = useState<Shift | null>(null);
  const [summary, setSummary] = useState<ShiftCashSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openModal, setOpenModal] = useState(false);
  const [closeModal, setCloseModal] = useState(false);
  const [handoverModal, setHandoverModal] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getCurrentShift();
      setShift(data.shift);
      setSummary(data.cash_summary ?? null);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingState label={t.common.loading} />;
  if (error)
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={error}
        retryLabel={t.common.retry}
        onRetry={load}
      />
    );

  return (
    <>
      {shift === null ? (
        <EmptyState
          icon={Clock}
          title={c.none}
          hint={c.noneHint}
          action={
            <Button icon={PlayCircle} onClick={() => setOpenModal(true)}>
              {c.open}
            </Button>
          }
        />
      ) : (
        <Card>
          <SectionHeader
            title={`${c.title} — ${shift.shift_number}`}
            actions={
              <Badge tone={shiftStatusTone(shift.status)}>
                {t.shifts.status[shift.status]}
              </Badge>
            }
          />
          <div className="workflow-grid">
            <StatCard label={c.businessDate} value={shift.business_date} />
            <StatCard label={c.openedAt} value={formatDateTime(shift.opened_at, locale)} />
            <StatCard label={c.openingCash} value={summary?.opening_cash ?? shift.opening_cash_amount} />
            <StatCard label={c.expectedCash} value={summary?.expected_cash ?? "—"} />
            <StatCard
              label={c.cashIn}
              value={`${summary?.cash_payments_total ?? "0.00"} (${summary?.payments_count ?? 0})`}
            />
            <StatCard
              label={c.cashOut}
              value={`${summary?.cash_expenses_total ?? "0.00"} (${summary?.expenses_count ?? 0})`}
            />
          </div>
          <div className="cluster">
            <Button icon={Lock} onClick={() => setCloseModal(true)}>
              {c.close}
            </Button>
            <Button
              variant="secondary"
              icon={ArrowLeftRight}
              onClick={() => setHandoverModal(true)}
            >
              {c.handover}
            </Button>
          </div>
        </Card>
      )}

      <OpenShiftModal
        open={openModal}
        onClose={() => setOpenModal(false)}
        onDone={() => {
          setOpenModal(false);
          notify(t.shifts.msgs.opened);
          load();
        }}
      />
      {shift ? (
        <CloseShiftModal
          open={closeModal}
          shift={shift}
          expected={summary?.expected_cash ?? "0.00"}
          onClose={() => setCloseModal(false)}
          onDone={() => {
            setCloseModal(false);
            notify(t.shifts.msgs.closed);
            load();
          }}
        />
      ) : null}
      {shift ? (
        <HandoverFormModal
          open={handoverModal}
          presetShift={shift.id}
          onClose={() => setHandoverModal(false)}
          onSaved={() => {
            setHandoverModal(false);
            notify(t.shifts.ho.createdMsg);
          }}
        />
      ) : null}
    </>
  );
}

export function OpenShiftModal({
  open,
  onClose,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const f = t.shifts.form;
  const [openingCash, setOpeningCash] = useState("0.00");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setOpeningCash("0.00");
      setNotes("");
      setError(null);
    }
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await openShift({ opening_cash_amount: openingCash || "0.00", opening_notes: notes });
      onDone();
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
      title={f.openTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="shift-open-form" type="submit" loading={busy}>
            {t.shifts.current.open}
          </Button>
        </>
      }
    >
      <form id="shift-open-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={f.openingCash} htmlFor="so-cash">
          <Input
            id="so-cash"
            type="number"
            step="0.01"
            min="0"
            value={openingCash}
            onChange={(e) => setOpeningCash(e.target.value)}
          />
        </FormField>
        <FormField label={f.openingNotes} htmlFor="so-notes">
          <Input id="so-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}

export function CloseShiftModal({
  open,
  shift,
  expected,
  onClose,
  onDone,
}: {
  open: boolean;
  shift: { id: number; shift_number: string };
  expected: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const f = t.shifts.form;
  const [actual, setActual] = useState("");
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setActual(expected);
      setReason("");
      setNotes("");
      setError(null);
    }
  }, [open, expected]);

  const difference = (Number(actual || 0) - Number(expected || 0)).toFixed(2);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await closeShift(shift.id, {
        actual_cash_amount: actual || "0.00",
        difference_reason: reason,
        closing_notes: notes,
      });
      onDone();
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
      title={`${f.closeTitle} — ${shift.shift_number}`}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="shift-close-form" type="submit" loading={busy}>
            {t.shifts.current.close}
          </Button>
        </>
      }
    >
      <form id="shift-close-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <p className="muted">{f.closeHint}</p>
        <div className="form-grid">
          <FormField label={f.expected} htmlFor="sc-expected">
            <Input id="sc-expected" value={expected} readOnly disabled />
          </FormField>
          <FormField label={f.actualCash} htmlFor="sc-actual">
            <Input
              id="sc-actual"
              type="number"
              step="0.01"
              min="0"
              value={actual}
              onChange={(e) => setActual(e.target.value)}
            />
          </FormField>
        </div>
        {difference !== "0.00" ? (
          <Alert tone="warning">
            {f.difference}: {difference}
          </Alert>
        ) : null}
        <FormField label={f.differenceReason} htmlFor="sc-reason">
          <Input id="sc-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
        <FormField label={f.closingNotes} htmlFor="sc-notes">
          <Input id="sc-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}
