"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Printer } from "lucide-react";

import { Alert, Button, FormField, Modal, Textarea } from "@/components/ui";
import { messageForError } from "@/lib/api/errors";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** A modal that collects a required reason and runs a void action. */
export function VoidDialog({
  open,
  title,
  onClose,
  onConfirm,
}: {
  open: boolean;
  title?: string;
  onClose: () => void;
  onConfirm: (reason: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setReason("");
      setError(null);
    }
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return setError(t.finance.errors.voidReasonRequired);
    setBusy(true);
    try {
      await onConfirm(reason.trim());
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
      title={title ?? t.finance.void.title}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="void-form" type="submit" variant="danger" loading={busy}>{t.finance.void.confirm}</Button>
        </>
      }
    >
      <form id="void-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={t.finance.void.reason} htmlFor="void-reason">
          <Textarea id="void-reason" value={reason} required placeholder={t.finance.void.reasonPlaceholder} onChange={(e) => setReason(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}

/** A print-friendly document modal. The `.print-doc` node is the only thing
 *  visible when the browser print dialog runs (see globals.css @media print). */
export function PrintModal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t.finance.print.close}</Button>
          <Button icon={Printer} onClick={() => window.print()}>{t.finance.print.print}</Button>
        </>
      }
    >
      <div className="print-doc">{children}</div>
    </Modal>
  );
}
