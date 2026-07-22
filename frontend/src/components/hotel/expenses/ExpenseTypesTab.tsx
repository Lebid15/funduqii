"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Plus, Power, PowerOff, Pencil, Tags } from "lucide-react";

import {
  Alert, Badge, Button, Card, EmptyState, ErrorState, FormField, Input,
  LoadingState, Modal, SectionHeader, useToast,
} from "@/components/ui";
import {
  createExpenseType, listExpenseTypes, updateExpenseType,
} from "@/lib/api/expenses";
import { messageForError } from "@/lib/api/errors";
import type { ExpenseType } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useCan } from "./shared";

export function ExpenseTypesTab() {
  const { t } = useI18n();
  const { notify } = useToast();
  const e = t.expenses;
  const can = useCan();
  const canManage = can("expenses.manage_types");

  const [rows, setRows] = useState<ExpenseType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ExpenseType | null>(null);
  const [creating, setCreating] = useState(false);
  const mountedRef = useRef(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await listExpenseTypes({ all: true });
      if (mountedRef.current) setRows(list);
    } catch (err) {
      if (mountedRef.current) setError(messageForError(err, t));
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    mountedRef.current = true;
    load();
    return () => { mountedRef.current = false; };
  }, [load]);

  async function toggleActive(ty: ExpenseType) {
    try {
      await updateExpenseType(ty.id, { is_active: !ty.is_active });
      notify(e.typeUpdated);
      load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  return (
    <>
      <Card>
        <SectionHeader
          title={e.typesTitle}
          actions={canManage ? <Button icon={Plus} onClick={() => setCreating(true)}>{e.addType}</Button> : undefined}
        />
        {loading ? <LoadingState label={t.common.loading} /> : null}
        {!loading && error ? (
          <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} />
        ) : null}
        {!loading && !error ? (
          rows.length === 0 ? (
            <EmptyState
              title={e.noTypes}
              hint={e.noTypesHint}
              icon={Tags}
              action={canManage ? <Button icon={Plus} onClick={() => setCreating(true)}>{e.addType}</Button> : undefined}
            />
          ) : (
            <ul className="stack" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {rows.map((ty) => (
                <li key={ty.id} className="cluster" style={{ justifyContent: "space-between", alignItems: "center", gap: "0.75rem", padding: "0.5rem 0", borderBottom: "1px solid var(--color-border)" }}>
                  <span className="cluster" style={{ gap: "0.5rem", alignItems: "center" }}>
                    <span>{ty.name}</span>
                    <Badge tone={ty.is_active ? "success" : "neutral"}>
                      {ty.is_active ? e.typeActive : e.typeInactive}
                    </Badge>
                  </span>
                  {canManage ? (
                    <span className="cluster" style={{ gap: "0.5rem" }}>
                      <Button variant="secondary" icon={Pencil} onClick={() => setEditing(ty)}>{e.renameType}</Button>
                      <Button
                        variant="secondary"
                        icon={ty.is_active ? PowerOff : Power}
                        onClick={() => toggleActive(ty)}
                      >
                        {ty.is_active ? e.deactivate : e.activate}
                      </Button>
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )
        ) : null}
      </Card>

      <TypeModal
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={() => { setCreating(false); notify(e.typeCreated); load(); }}
      />
      <TypeModal
        open={editing !== null}
        initial={editing}
        onClose={() => setEditing(null)}
        onSaved={() => { setEditing(null); notify(e.typeUpdated); load(); }}
      />
    </>
  );
}

function TypeModal({
  open, initial, onClose, onSaved,
}: { open: boolean; initial?: ExpenseType | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n();
  const e = t.expenses;
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setName(initial?.name ?? ""); setError(null); }
  }, [open, initial]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!name.trim()) return setError(t.errors.validation);
    setBusy(true);
    try {
      if (initial) await updateExpenseType(initial.id, { name: name.trim() });
      else await createExpenseType(name.trim());
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={initial ? e.editTypeTitle : e.addTypeTitle} closeLabel={t.common.close}
      footer={<><Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button><Button form="type-form" type="submit" loading={busy}>{t.common.save}</Button></>}>
      <form id="type-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={e.typeName} htmlFor="type-name">
          <Input id="type-name" value={name} placeholder={e.typeNamePlaceholder} onChange={(ev) => setName(ev.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}
