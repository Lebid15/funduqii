"use client";

import { useEffect, useState, type FormEvent } from "react";
import { UserCheck } from "lucide-react";

import { Alert, Button, FormField, Modal, Select } from "@/components/ui";
import { messageForError } from "@/lib/api/errors";
import { listStaff } from "@/lib/api/staff";
import type { LostFoundCategory } from "@/lib/api/types";
import type { Locale } from "@/lib/i18n/config";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useCurrentUser } from "@/lib/session/CurrentUserContext";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

/** Cosmetic permission gate — every API re-checks server-side regardless.
 * `null` (outside the hotel shell) and the still-loading state both read as
 * "allowed" so the UI never briefly hides a control the user actually has. */
export function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

/** Lost & found categories that require ownership proof on handover (WP7). The
 * proof fields are shown ONLY for these categories. */
export const SENSITIVE_LF_CATEGORIES: readonly LostFoundCategory[] = [
  "money",
  "jewelry",
  "documents",
];

export function isSensitiveCategory(category: LostFoundCategory): boolean {
  return SENSITIVE_LF_CATEGORIES.includes(category);
}

/** Compact, locale-aware elapsed duration between two instants (WP10 cleaning
 * card). Uses `Intl` unit formatting so no per-unit translation key is needed.
 * `end === null` measures up to now (an in-progress task). */
export function formatDuration(
  start: string | null,
  end: string | null,
  locale: Locale,
): string | null {
  if (!start) return null;
  const from = new Date(start).getTime();
  const to = end ? new Date(end).getTime() : Date.now();
  const minutes = Math.max(0, Math.round((to - from) / 60000));
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  const hourFmt = new Intl.NumberFormat(locale, {
    style: "unit",
    unit: "hour",
    unitDisplay: "narrow",
  });
  const minFmt = new Intl.NumberFormat(locale, {
    style: "unit",
    unit: "minute",
    unitDisplay: "narrow",
  });
  const parts: string[] = [];
  if (hours > 0) parts.push(hourFmt.format(hours));
  parts.push(minFmt.format(mins));
  return parts.join(" ");
}

interface AssignLabels {
  title: string;
  staffMember: string;
  assignToMe: string;
  unassign: string;
  unassigned: string;
}

/**
 * Shared assignee picker (housekeeping + maintenance). Offers a FULL staff
 * Select (any active member — never just assign-to-me) plus an "assign to me"
 * shortcut and an optional unassign. The concrete API call is injected via
 * `onAssign(userId | null)`, so the same modal serves both domains.
 */
export function AssignModal({
  open,
  labels,
  currentAssignee,
  allowUnassign,
  onClose,
  onAssign,
}: {
  open: boolean;
  labels: AssignLabels;
  currentAssignee: number | null;
  allowUnassign: boolean;
  onClose: () => void;
  onAssign: (userId: number | null) => Promise<void>;
}) {
  const { t } = useI18n();
  const me = useCurrentUser();
  const [staffOptions, setStaffOptions] = useState<{ value: string; label: string }[]>(
    [],
  );
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setValue(currentAssignee ? String(currentAssignee) : me ? String(me.id) : "");
    setError(null);
    listStaff({ page_size: 100 })
      .then((res) => {
        const options = res.results
          .filter((member) => member.is_active)
          .map((member) => ({ value: String(member.user_id), label: member.full_name }));
        if (me && !options.some((option) => option.value === String(me.id))) {
          options.unshift({ value: String(me.id), label: me.full_name });
        }
        setStaffOptions(options);
      })
      .catch(() => {
        setStaffOptions(me ? [{ value: String(me.id), label: me.full_name }] : []);
      });
  }, [open, currentAssignee, me]);

  async function run(userId: number | null) {
    setBusy(true);
    setError(null);
    try {
      await onAssign(userId);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!value) return setError(t.errors.validation);
    void run(Number(value));
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={labels.title}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          {allowUnassign ? (
            <Button variant="dangerSoft" loading={busy} onClick={() => void run(null)}>
              {labels.unassign}
            </Button>
          ) : null}
          <Button form="op-assign-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="op-assign-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={labels.staffMember} htmlFor="op-assign-user">
          <Select
            id="op-assign-user"
            value={value}
            placeholder={labels.unassigned}
            options={staffOptions}
            onChange={(event) => setValue(event.target.value)}
          />
        </FormField>
        {me ? (
          <div className="cluster">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              icon={UserCheck}
              disabled={busy}
              onClick={() => setValue(String(me.id))}
            >
              {labels.assignToMe}
            </Button>
          </div>
        ) : null}
      </form>
    </Modal>
  );
}
