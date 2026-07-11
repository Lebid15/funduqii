"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ShieldCheck } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FormField,
  LoadingState,
  SectionHeader,
  Select,
  Switch,
  useToast,
} from "@/components/ui";
import {
  getStaffPermissions,
  listStaff,
  putStaffPermissions,
} from "@/lib/api/staff";
import { messageForError } from "@/lib/api/errors";
import type { StaffMemberListItem, StaffPermissionsPayload } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

/** Translated label for a registry section/operation with a safe fallback so
 * future registry additions never break the matrix. */
function sectionLabel(t: ReturnType<typeof useI18n>["t"], section: string): string {
  const labels = t.staff.registry.sections as Record<string, string>;
  return labels[section] ?? section;
}

function opLabel(t: ReturnType<typeof useI18n>["t"], op: string): string {
  const labels = t.staff.registry.ops as Record<string, string>;
  return labels[op] ?? op;
}

export function PermissionsMatrixTab({ initialTarget }: { initialTarget: number | null }) {
  const { t } = useI18n();
  const { notify } = useToast();
  const access = useHotelAccess();
  const m = t.staff.matrix;

  const [staff, setStaff] = useState<StaffMemberListItem[]>([]);
  const [target, setTarget] = useState<number | null>(initialTarget);
  const [payload, setPayload] = useState<StaffPermissionsPayload | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadStaff = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listStaff({ is_active: "true" });
      setStaff(data.results);
      setTarget((current) => {
        if (current && data.results.some((r) => r.id === current)) return current;
        const firstEditable = data.results.find((r) => !r.is_manager);
        return firstEditable?.id ?? data.results[0]?.id ?? null;
      });
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadStaff();
  }, [loadStaff]);

  useEffect(() => {
    if (target === null) return;
    let cancelled = false;
    setPayload(null);
    getStaffPermissions(target)
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
        setSelected(new Set(data.granted));
      })
      .catch((err) => {
        if (!cancelled) setError(messageForError(err, t));
      });
    return () => {
      cancelled = true;
    };
  }, [target, t]);

  const dirty = useMemo(() => {
    if (!payload) return false;
    const granted = new Set(payload.granted);
    if (granted.size !== selected.size) return true;
    for (const code of selected) if (!granted.has(code)) return true;
    return false;
  }, [payload, selected]);

  function toggle(code: string, on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(code);
      else next.delete(code);
      return next;
    });
  }

  function setSection(codes: string[], on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const code of codes) {
        if (on) next.add(code);
        else next.delete(code);
      }
      return next;
    });
  }

  async function save() {
    if (!payload) return;
    setBusy(true);
    try {
      await putStaffPermissions(payload.membership, [...selected]);
      notify(m.savedMsg);
      const fresh = await getStaffPermissions(payload.membership);
      setPayload(fresh);
      setSelected(new Set(fresh.granted));
      // Editing your own grants changes what the sidebar may show.
      if (payload.is_self) access?.refresh();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingState label={t.common.loading} />;
  if (error)
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={error}
        retryLabel={t.common.retry}
        onRetry={loadStaff}
      />
    );
  if (staff.length === 0)
    return <EmptyState title={m.noStaff} hint={t.staff.list.emptyHint} icon={ShieldCheck} />;

  const staffOptions = staff.map((r) => ({
    value: String(r.id),
    label: `${r.full_name} (${r.email})`,
  }));

  return (
    <>
      <Card>
        <SectionHeader title={m.title} />
        <p className="muted">{m.hint}</p>
        <FormField label={m.pickStaff} htmlFor="matrix-target">
          <Select
            id="matrix-target"
            value={target ? String(target) : ""}
            options={staffOptions}
            onChange={(e) => setTarget(Number(e.target.value))}
          />
        </FormField>
      </Card>

      {payload === null ? (
        <LoadingState label={t.common.loading} />
      ) : payload.is_manager ? (
        <Alert tone="info">{m.managerAll}</Alert>
      ) : (
        <>
          {payload.is_self ? <p className="muted">{m.selfCannotEdit}</p> : null}
          {!payload.is_active ? <Alert tone="warning">{m.inactiveNote}</Alert> : null}
          <div className="workflow-grid">
            {payload.registry.map((section) => {
              const grantedInSection = section.codes.filter((c) => selected.has(c)).length;
              return (
                <Card key={section.section}>
                  <SectionHeader
                    title={sectionLabel(t, section.section)}
                    actions={
                      <Badge tone={grantedInSection > 0 ? "primary" : "neutral"}>
                        {m.grantedCount.replace("{count}", String(grantedInSection))}
                      </Badge>
                    }
                  />
                  <div className="cluster">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={payload.is_self}
                      onClick={() => setSection(section.codes, true)}
                    >
                      {m.selectSection}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={payload.is_self}
                      onClick={() => setSection(section.codes, false)}
                    >
                      {m.clearSection}
                    </Button>
                  </div>
                  <div className="stack">
                    {section.operations.map((op, index) => {
                      const code = section.codes[index];
                      return (
                        <Switch
                          key={code}
                          id={`perm-${code}`}
                          checked={selected.has(code)}
                          disabled={payload.is_self}
                          onChange={(on) => toggle(code, on)}
                          label={opLabel(t, op)}
                        />
                      );
                    })}
                  </div>
                </Card>
              );
            })}
          </div>
          <div className="cluster">
            <Button onClick={save} loading={busy} disabled={!dirty || payload.is_self}>
              {m.save}
            </Button>
            <Button
              variant="secondary"
              disabled={!dirty || busy || payload.is_self}
              onClick={() => setSelected(new Set(payload.granted))}
            >
              {m.reset}
            </Button>
          </div>
        </>
      )}
    </>
  );
}
