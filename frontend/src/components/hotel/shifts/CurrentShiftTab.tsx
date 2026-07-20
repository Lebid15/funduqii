"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ArrowLeftRight, Clock, Inbox, Lock, PlayCircle, Printer } from "lucide-react";

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
  PrintDocumentLayout,
  SectionHeader,
  StatCard,
  useToast,
} from "@/components/ui";
import { closeShift, getCurrentShift, getShiftStatement, openShift } from "@/lib/api/shifts";
import { messageForError } from "@/lib/api/errors";
import type { Shift, ShiftCashSummary, ShiftStatement } from "@/lib/api/types";
import { formatDateTime, shiftStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { HandoverFormModal, HandoversDrawer } from "./HandoversTab";
import { PrintModal } from "../finance/shared";

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
  const [handoversDrawer, setHandoversDrawer] = useState(false);
  const [statement, setStatement] = useState<ShiftStatement | null>(null);

  async function openStatement(id: number) {
    try {
      setStatement(await getShiftStatement(id));
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

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
            <div className="cluster">
              <Button icon={PlayCircle} onClick={() => setOpenModal(true)}>
                {c.open}
              </Button>
              {/* Incoming handovers can be accepted even with no open shift. */}
              <Button
                variant="secondary"
                icon={Inbox}
                onClick={() => setHandoversDrawer(true)}
              >
                {t.shifts.tabs.handovers}
              </Button>
            </div>
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
            <Button
              variant="ghost"
              icon={Printer}
              onClick={() => openStatement(shift.id)}
            >
              {t.shifts.print.printStatement}
            </Button>
            <Button
              variant="ghost"
              icon={Inbox}
              onClick={() => setHandoversDrawer(true)}
            >
              {t.shifts.tabs.handovers}
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
      <ShiftStatementPrintModal statement={statement} onClose={() => setStatement(null)} />
      <HandoversDrawer
        open={handoversDrawer}
        onClose={() => setHandoversDrawer(false)}
      />
    </>
  );
}

/** Print-friendly shift statement (reprintable GET). Shared by the current
 *  shift card and the shifts list. */
export function ShiftStatementPrintModal({
  statement,
  onClose,
}: {
  statement: ShiftStatement | null;
  onClose: () => void;
}) {
  const { t, locale } = useI18n();
  if (!statement) return null;
  const { shift, cash_summary } = statement;
  const meta = [
    { label: t.common.status, value: t.shifts.status[shift.status] },
    { label: t.shifts.list.responsible, value: shift.responsible_name || "—" },
    { label: t.shifts.list.businessDate, value: shift.business_date },
    { label: t.shifts.list.openedAt, value: formatDateTime(shift.opened_at, locale) },
    ...(shift.closed_at
      ? [{ label: t.shifts.list.closedAt, value: formatDateTime(shift.closed_at, locale) }]
      : []),
    { label: t.shifts.current.openingCash, value: shift.opening_cash_amount },
    { label: t.shifts.current.expectedCash, value: shift.expected_cash_amount },
    ...(shift.actual_cash_amount !== null
      ? [{ label: t.shifts.list.actual, value: shift.actual_cash_amount }]
      : []),
    { label: t.shifts.list.difference, value: shift.cash_difference },
    ...(shift.difference_reason
      ? [{ label: t.shifts.form.differenceReason, value: shift.difference_reason }]
      : []),
    {
      label: t.shifts.current.cashIn,
      value: `${cash_summary.cash_payments_total} (${cash_summary.payments_count})`,
    },
    {
      label: t.shifts.current.cashOut,
      value: `${cash_summary.cash_expenses_total} (${cash_summary.expenses_count})`,
    },
  ];
  return (
    <PrintModal open={statement !== null} title={t.shifts.print.statementTitle} onClose={onClose}>
      <PrintDocumentLayout
        hotelName={statement.hotel.hotel_name}
        hotelAddress={statement.hotel.address}
        hotelPhone={statement.hotel.phone}
        docTitle={t.shifts.print.statementTitle}
        docNumber={shift.shift_number}
        meta={meta}
        signatureLabel={t.finance.print.signature}
      />
    </PrintModal>
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
