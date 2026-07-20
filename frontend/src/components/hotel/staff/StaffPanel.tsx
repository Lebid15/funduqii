"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowDown,
  ArrowUp,
  Briefcase,
  KeyRound,
  Link2,
  Mail,
  Pencil,
  Phone,
  Plus,
  SearchX,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserCog,
  Users,
  UserX,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  Modal,
  Pagination,
  PasswordInput,
  SectionHeader,
  Select,
  Switch,
  useToast,
  type BadgeTone,
} from "@/components/ui";
import { StatCards, type OperationStat } from "@/components/hotel/operations/StatCards";
import type {
  OperationFact,
  OperationMenuItem,
} from "@/components/hotel/operations/OperationCard";
import { StaffCard, type StaffCardAction } from "./StaffCard";
import { PermissionSectionsEditor, useCodeSelection } from "./PermissionSectionsEditor";
import {
  changeStaffEmail,
  createStaffMember,
  deactivateStaffMember,
  deleteStaffMember,
  demoteStaffMember,
  getPermissionRegistry,
  getStaffOverview,
  getStaffPermissions,
  linkExistingUser,
  listStaff,
  promoteStaffMember,
  putStaffPermissions,
  reactivateStaffMember,
  resetStaffPassword,
  updateStaffMember,
  type LinkExistingBody,
  type StaffCreateBody,
  type StaffUpdateBody,
} from "@/lib/api/staff";
import { messageForError } from "@/lib/api/errors";
import type {
  PermissionRegistrySection,
  StaffMemberListItem,
  StaffOverview,
  StaffPermissionsPayload,
} from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useCurrentUser } from "@/lib/session/CurrentUserContext";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

const PAGE_SIZE = 25;

/** Cosmetic permission gate — every API re-checks server-side regardless. Null
 * access = platform console context, where this page never renders. */
function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

/**
 * The whole staff section collapsed to ONE operational page (RAPID wave §3):
 * a stat row (folded from the old Overview tab) + search + status/type filters
 * + "Add employee", over a CARD grid of members. The standalone Overview,
 * Permissions-matrix and Registry tabs are gone; permission editing now lives in
 * a modal launched from each card, and the create flow is a single two-step
 * modal that posts the chosen grants inline. No Tabs shell.
 */
export function StaffPanel() {
  const { t } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const me = useCurrentUser();
  const s = t.staff.list;
  const o = t.staff.overview;

  const [rows, setRows] = useState<StaffMemberListItem[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState(""); // "" | "true" | "false"
  const [type, setType] = useState(""); // "" | "manager" | "staff"
  // `search` is what the user is typing; `appliedSearch` is what the SERVER is
  // currently filtered by. Only the latter drives a request.
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Flips true after the FIRST settled load — the initial load owns the full
  // LoadingState/ErrorState; later fetches keep the cards mounted (a11y).
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  // The counters folded from the old Overview tab. Refreshed after any action
  // that changes them; degrades silently (the list stays usable) on failure.
  const [overview, setOverview] = useState<StaffOverview | null>(null);
  const [overviewError, setOverviewError] = useState(false);

  // The generic permission registry, loaded once for the create step-2 editor.
  const [registry, setRegistry] = useState<PermissionRegistrySection[] | null>(null);
  const [registryError, setRegistryError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [editRow, setEditRow] = useState<StaffMemberListItem | null>(null);
  const [manageRow, setManageRow] = useState<StaffMemberListItem | null>(null);
  const [deactivateRow, setDeactivateRow] = useState<StaffMemberListItem | null>(null);
  const [reactivateRow, setReactivateRow] = useState<StaffMemberListItem | null>(null);
  const [resetRow, setResetRow] = useState<StaffMemberListItem | null>(null);
  const [promoteRow, setPromoteRow] = useState<StaffMemberListItem | null>(null);
  const [demoteRow, setDemoteRow] = useState<StaffMemberListItem | null>(null);
  const [emailRow, setEmailRow] = useState<StaffMemberListItem | null>(null);
  const [deleteRow, setDeleteRow] = useState<StaffMemberListItem | null>(null);

  const loadedOnceRef = useRef(false);
  const mountedRef = useRef(true);
  const seqRef = useRef(0);
  const resultsRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef(false);

  const load = useCallback(async () => {
    const seq = (seqRef.current += 1);
    setLoading(true);
    setError(null);
    try {
      const data = await listStaff({
        page,
        search: appliedSearch || undefined,
        is_active: status || undefined,
        membership_type: type || undefined,
      });
      if (seqRef.current !== seq) return;
      setRows(data.results);
      setCount(data.count);
      loadedOnceRef.current = true;
      setHasLoadedOnce(true);
    } catch (err) {
      if (seqRef.current !== seq) return;
      const message = messageForError(err, t);
      // BACKGROUND refetch failure keeps the cards + a non-blocking toast; the
      // full ErrorState + retry is reserved for the initial load.
      if (loadedOnceRef.current) notify(message, "error");
      else setError(message);
    } finally {
      if (mountedRef.current && seqRef.current === seq) setLoading(false);
    }
  }, [page, appliedSearch, status, type, t, notify]);

  const loadOverview = useCallback(async () => {
    try {
      const data = await getStaffOverview();
      if (!mountedRef.current) return;
      setOverview(data);
      setOverviewError(false);
    } catch {
      if (mountedRef.current) setOverviewError(true);
    }
  }, []);

  const loadRegistry = useCallback(async () => {
    setRegistryError(null);
    try {
      const data = await getPermissionRegistry();
      if (!mountedRef.current) return;
      setRegistry(data.sections);
    } catch (err) {
      if (mountedRef.current) setRegistryError(messageForError(err, t));
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadOverview();
    loadRegistry();
  }, [loadOverview, loadRegistry]);

  // DEBOUNCE the search (~350ms after typing stops) so a five-letter term is one
  // round-trip, not five. Applying the term and resetting to page 1 in the SAME
  // tick keeps it to a single render/fetch; the seq-guard discards stale replies.
  useEffect(() => {
    const id = setTimeout(() => {
      setAppliedSearch(search.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(id);
  }, [search]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // After an ACTION-triggered reload settles, restore focus to the stable results
  // anchor if the acting control (a card menu item) unmounted.
  useEffect(() => {
    if (loading || !restoreFocusRef.current) return;
    restoreFocusRef.current = false;
    const active = document.activeElement as HTMLElement | null;
    if (!active || active === document.body || !active.isConnected) {
      resultsRef.current?.focus();
    }
  }, [rows, loading]);

  // A mutation changed the roster: refetch the page AND the counters, and mark
  // focus for restoration if the acting control vanished.
  const refreshAfterAction = useCallback(() => {
    restoreFocusRef.current = true;
    loadOverview();
    return load();
  }, [load, loadOverview]);

  const filtering = appliedSearch !== "" || status !== "" || type !== "";
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  const statCards: OperationStat[] = [
    { key: "total", label: o.total, value: overview ? overview.total_staff : null, icon: Users, tone: "info" },
    { key: "active", label: o.active, value: overview ? overview.active_staff : null, icon: UserCheck, tone: "success" },
    {
      key: "disabled",
      label: o.inactive,
      value: overview ? overview.inactive_staff : null,
      icon: UserX,
      tone: overview && overview.inactive_staff > 0 ? "warning" : "neutral",
    },
    { key: "managers", label: o.managers, value: overview ? overview.managers : null, icon: UserCog, tone: "primary" },
  ];

  const statusOptions = [
    { value: "true", label: s.active },
    { value: "false", label: s.inactive },
  ];
  const typeOptions = [
    { value: "manager", label: s.manager },
    { value: "staff", label: s.staffType },
  ];

  const showInitialLoading = loading && !hasLoadedOnce;
  const showInitialError = !showInitialLoading && !hasLoadedOnce && error !== null;
  const backgroundRefreshing = loading && hasLoadedOnce;

  // DEBOUNCED live-region text: announce only once the result has SETTLED and
  // stayed settled for ~450ms so typing does not fire a burst of announcements.
  const settledCount = !loading && hasLoadedOnce ? rows.length : null;
  useEffect(() => {
    if (settledCount === null) return;
    const id = setTimeout(() => {
      setAnnouncement(
        settledCount === 0
          ? t.operations.noResults
          : t.operations.resultsCount.replace("{count}", String(settledCount)),
      );
    }, 450);
    return () => clearTimeout(id);
  }, [settledCount, t]);

  function renderCard(r: StaffMemberListItem) {
    const isSelf = me?.id === r.user_id;
    const accent: BadgeTone = !r.is_active ? "neutral" : r.is_manager ? "primary" : "info";

    const facts: OperationFact[] = [
      {
        key: "job",
        label: s.jobTitle,
        value: r.job_title ? <bdi>{r.job_title}</bdi> : "—",
        icon: Briefcase,
      },
      {
        key: "contact",
        label: s.contact,
        value: <bdi dir="ltr">{r.phone || r.email}</bdi>,
        icon: r.phone ? Phone : Mail,
      },
      {
        key: "perms",
        label: s.permissions,
        value: r.is_manager ? s.managerFullAccess : String(r.permission_count),
        icon: ShieldCheck,
      },
    ];

    // COMMON actions as visible affordances (each gate preserved from the old
    // table). One emphasised primary, the rest secondary.
    const actions: StaffCardAction[] = [];
    if (!r.is_manager) {
      actions.push({
        key: "manage",
        label: s.managePermissions,
        icon: ShieldCheck,
        variant: "primary",
        onClick: () => setManageRow(r),
      });
    }
    actions.push({
      key: "edit",
      label: s.edit,
      icon: Pencil,
      variant: r.is_manager ? "primary" : "secondary",
      onClick: () => setEditRow(r),
    });
    if (!r.is_primary_manager) {
      if (r.is_active) {
        actions.push({ key: "deactivate", label: s.deactivate, icon: UserX, onClick: () => setDeactivateRow(r) });
      } else {
        actions.push({ key: "reactivate", label: s.reactivate, icon: UserCheck, onClick: () => setReactivateRow(r) });
      }
    }
    actions.push({ key: "reset", label: s.resetPassword, icon: KeyRound, onClick: () => setResetRow(r) });

    // RARE / sensitive ops folded into the accessible "More" menu — same gates.
    const menu: OperationMenuItem[] = [];
    if (!r.is_manager && !isSelf && can("staff.manage_managers")) {
      menu.push({ key: "promote", label: s.promote, icon: ArrowUp, onSelect: () => setPromoteRow(r) });
    }
    if (r.is_manager && !r.is_primary_manager && !isSelf && can("staff.manage_managers")) {
      menu.push({ key: "demote", label: s.demote, icon: ArrowDown, onSelect: () => setDemoteRow(r) });
    }
    if (!isSelf && can("staff.change_email")) {
      menu.push({ key: "email", label: s.changeEmail, icon: Mail, onSelect: () => setEmailRow(r) });
    }
    if (!r.is_primary_manager && !isSelf && can("staff.delete")) {
      menu.push({ key: "delete", label: s.delete, icon: Trash2, danger: true, onSelect: () => setDeleteRow(r) });
    }

    return (
      <StaffCard
        accent={accent}
        number={r.staff_code || undefined}
        title={<bdi>{r.full_name}</bdi>}
        ariaLabel={`${s.title} ${r.full_name}`}
        moreLabel={s.more}
        badges={
          <>
            <Badge tone={r.is_manager ? "primary" : "neutral"}>
              {r.is_manager ? s.manager : s.staffType}
            </Badge>
            <Badge tone={r.is_active ? "success" : "danger"}>
              {r.is_active ? s.active : s.inactive}
            </Badge>
          </>
        }
        facts={facts}
        actions={actions}
        menu={menu}
      />
    );
  }

  return (
    <>
      <StatCards
        stats={statCards}
        loading={overview === null && !overviewError}
        ariaLabel={t.staff.title}
      />

      <Card>
        <SectionHeader
          title={s.title}
          actions={
            <>
              <Button variant="secondary" icon={Link2} onClick={() => setLinkOpen(true)}>
                {s.link}
              </Button>
              <Button icon={Plus} onClick={() => setCreateOpen(true)}>
                {s.add}
              </Button>
            </>
          }
        />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setAppliedSearch(search.trim());
            setPage(1);
          }}
        >
          <FilterBar>
            <FormField label={t.common.search} htmlFor="st-search">
              <Input
                id="st-search"
                value={search}
                placeholder={s.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
              />
            </FormField>
            <FormField label={t.common.status} htmlFor="st-status">
              <Select
                id="st-status"
                value={status}
                placeholder={t.common.all}
                options={statusOptions}
                onChange={(e) => {
                  setPage(1);
                  setStatus(e.target.value);
                }}
              />
            </FormField>
            <FormField label={s.typeLabel} htmlFor="st-type">
              <Select
                id="st-type"
                value={type}
                placeholder={t.common.all}
                options={typeOptions}
                onChange={(e) => {
                  setPage(1);
                  setType(e.target.value);
                }}
              />
            </FormField>
          </FilterBar>
        </form>

        {/* STABLE polite live region — always mounted; announces the settled
            result count by a text change. */}
        <div
          className="sr-only"
          aria-live="polite"
          aria-atomic="true"
          data-testid="staff-results-announce"
        >
          {announcement}
        </div>

        {showInitialLoading ? <LoadingState label={t.common.loading} /> : null}
        {showInitialError ? (
          <ErrorState
            title={t.states.errorTitle}
            message={error ?? ""}
            retryLabel={t.common.retry}
            onRetry={load}
          />
        ) : null}
        {!showInitialLoading && !showInitialError ? (
          <div className="op-results" ref={resultsRef} tabIndex={-1} aria-label={s.title}>
            <div className="op-results__status" role="status" aria-live="polite">
              {backgroundRefreshing ? (
                <span className="op-results__searching">
                  <span className="spinner" aria-hidden="true" />
                  <span>{t.operations.updating}</span>
                </span>
              ) : null}
            </div>
            {rows.length === 0 ? (
              // A filter that matched nothing is NOT an empty hotel — saying "No
              // staff yet" while a filter is active hides the way out.
              filtering ? (
                <EmptyState title={s.noMatches} hint={s.noMatchesHint} icon={SearchX} />
              ) : (
                <EmptyState
                  title={s.empty}
                  hint={s.emptyHint}
                  icon={Users}
                  action={
                    <Button icon={Plus} onClick={() => setCreateOpen(true)}>
                      {s.add}
                    </Button>
                  }
                />
              )
            ) : (
              <div className="op-grid" role="list" aria-label={s.title} aria-busy={backgroundRefreshing}>
                {rows.map((r) => (
                  <div role="listitem" key={r.id}>
                    {renderCard(r)}
                  </div>
                ))}
              </div>
            )}
            {rows.length > 0 || filtering ? (
              <Pagination
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                labels={{
                  previous: t.pagination.previous,
                  next: t.pagination.next,
                  status: t.pagination.page
                    .replace("{page}", String(page))
                    .replace("{total}", String(totalPages)),
                }}
              />
            ) : null}
          </div>
        ) : null}
      </Card>

      <CreateStaffModal
        open={createOpen}
        registry={registry}
        registryError={registryError}
        onRetryRegistry={loadRegistry}
        onClose={() => setCreateOpen(false)}
        onSaved={() => {
          setCreateOpen(false);
          notify(s.createdMsg);
          refreshAfterAction();
        }}
      />
      <LinkUserModal
        open={linkOpen}
        onClose={() => setLinkOpen(false)}
        onSaved={() => {
          setLinkOpen(false);
          notify(s.linkedMsg);
          refreshAfterAction();
        }}
      />
      <ManagePermissionsModal
        member={manageRow}
        onClose={() => setManageRow(null)}
        onSaved={() => {
          setManageRow(null);
          refreshAfterAction();
        }}
      />
      <EditStaffModal
        row={editRow}
        onClose={() => setEditRow(null)}
        onSaved={() => {
          setEditRow(null);
          notify(s.updatedMsg);
          refreshAfterAction();
        }}
      />
      <DeactivateModal
        row={deactivateRow}
        onClose={() => setDeactivateRow(null)}
        onDone={() => {
          setDeactivateRow(null);
          notify(s.deactivatedMsg);
          refreshAfterAction();
        }}
      />
      <ConfirmDialog
        open={reactivateRow !== null}
        title={s.reactivate}
        body={reactivateRow?.full_name ?? ""}
        confirmLabel={s.reactivate}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        onClose={() => setReactivateRow(null)}
        onConfirm={async () => {
          if (!reactivateRow) return;
          try {
            await reactivateStaffMember(reactivateRow.id);
            notify(s.reactivatedMsg);
            refreshAfterAction();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setReactivateRow(null);
          }
        }}
      />
      <ResetPasswordModal
        row={resetRow}
        onClose={() => setResetRow(null)}
        onDone={() => {
          setResetRow(null);
          notify(s.resetDoneMsg);
        }}
      />
      <ConfirmDialog
        open={promoteRow !== null}
        title={s.promoteTitle}
        body={s.promoteConfirm.replace("{name}", promoteRow?.full_name ?? "")}
        confirmLabel={s.promote}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        onClose={() => setPromoteRow(null)}
        onConfirm={async () => {
          if (!promoteRow) return;
          try {
            await promoteStaffMember(promoteRow.id);
            notify(s.promotedMsg);
            refreshAfterAction();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setPromoteRow(null);
          }
        }}
      />
      <ConfirmDialog
        open={demoteRow !== null}
        title={s.demoteTitle}
        body={s.demoteConfirm.replace("{name}", demoteRow?.full_name ?? "")}
        confirmLabel={s.demote}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        onClose={() => setDemoteRow(null)}
        onConfirm={async () => {
          if (!demoteRow) return;
          try {
            await demoteStaffMember(demoteRow.id);
            notify(s.demotedMsg);
            refreshAfterAction();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setDemoteRow(null);
          }
        }}
      />
      <ChangeEmailModal
        row={emailRow}
        onClose={() => setEmailRow(null)}
        onDone={() => {
          setEmailRow(null);
          notify(s.emailChangedMsg);
          refreshAfterAction();
        }}
      />
      <DeleteModal
        row={deleteRow}
        onClose={() => setDeleteRow(null)}
        onDone={(msg) => {
          setDeleteRow(null);
          notify(msg);
          refreshAfterAction();
        }}
      />
    </>
  );
}

/* ==========================================================================
 * Create — a SINGLE modal, TWO steps: (1) details + account, (2) permissions
 * grouped by hotel section. On submit, POST /staff with the chosen grants inline
 * (createStaffMember already accepts permissions[]), so the member lands with
 * their access in ONE request — no jump to a separate matrix.
 * ======================================================================== */
function CreateStaffModal({
  open,
  registry,
  registryError,
  onRetryRegistry,
  onClose,
  onSaved,
}: {
  open: boolean;
  registry: PermissionRegistrySection[] | null;
  registryError: string | null;
  onRetryRegistry: () => void;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const f = t.staff.form;
  const [step, setStep] = useState<1 | 2>(1);
  const [form, setForm] = useState<StaffCreateBody>({
    full_name: "",
    email: "",
    password: "",
  });
  const { selected, toggle, setSection, reset } = useCodeSelection();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setStep(1);
      setForm({
        full_name: "",
        email: "",
        password: "",
        phone: "",
        job_title: "",
        staff_code: "",
        notes: "",
      });
      reset([]);
      setError(null);
    }
  }, [open, reset]);

  function set<K extends keyof StaffCreateBody>(k: K, v: StaffCreateBody[K]) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (step === 1) {
      if (!form.full_name.trim()) return setError(f.nameRequired);
      if (!form.email.trim()) return setError(f.emailRequired);
      if ((form.password ?? "").length < 8) return setError(f.passwordRequired);
      setError(null);
      setStep(2);
      return;
    }
    // Step 2 → create with the collected grants inline.
    setBusy(true);
    setError(null);
    try {
      await createStaffMember({ ...form, permissions: [...selected] });
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const registryLoading = registry === null && registryError === null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={f.createTitle}
      closeLabel={t.common.close}
      size="xl"
      footer={
        step === 1 ? (
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              {t.common.cancel}
            </Button>
            <Button form="staff-create-form" type="submit">
              {f.next}
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={() => setStep(1)} disabled={busy}>
              {f.back}
            </Button>
            <Button form="staff-create-form" type="submit" loading={busy} disabled={registryLoading}>
              {f.createSubmit}
            </Button>
          </>
        )
      }
    >
      <form id="staff-create-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <p className="muted small">{step === 1 ? f.step1 : f.step2}</p>

        {step === 1 ? (
          <>
            <div className="form-grid">
              <FormField label={f.fullName} htmlFor="sc-name">
                <Input id="sc-name" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} />
              </FormField>
              <FormField label={f.email} htmlFor="sc-email">
                <Input id="sc-email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
              </FormField>
              <FormField label={f.phone} htmlFor="sc-phone">
                <Input id="sc-phone" value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} />
              </FormField>
              <FormField label={f.tempPassword} htmlFor="sc-pass" hint={f.tempPasswordHint}>
                <PasswordInput
                  id="sc-pass"
                  value={form.password}
                  showLabel={t.auth.showPassword}
                  hideLabel={t.auth.hidePassword}
                  onChange={(e) => set("password", e.target.value)}
                />
              </FormField>
              <FormField label={f.jobTitle} htmlFor="sc-title" hint={f.jobTitleHint}>
                <Input id="sc-title" value={form.job_title ?? ""} onChange={(e) => set("job_title", e.target.value)} />
              </FormField>
              <FormField label={f.staffCode} htmlFor="sc-code">
                <Input id="sc-code" value={form.staff_code ?? ""} onChange={(e) => set("staff_code", e.target.value)} />
              </FormField>
            </div>
            <FormField label={f.notes} htmlFor="sc-notes">
              <Input id="sc-notes" value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} />
            </FormField>
          </>
        ) : (
          <>
            <p className="muted small">{f.initialPermissionsHint}</p>
            {registry ? (
              <PermissionSectionsEditor
                registry={registry}
                selected={selected}
                onToggle={toggle}
                onSection={setSection}
                idPrefix="sc-perm"
              />
            ) : registryError ? (
              <ErrorState
                title={t.states.errorTitle}
                message={registryError}
                retryLabel={t.common.retry}
                onRetry={onRetryRegistry}
              />
            ) : (
              <LoadingState label={t.common.loading} />
            )}
          </>
        )}
      </form>
    </Modal>
  );
}

/* ==========================================================================
 * Manage permissions for an EXISTING member — the section-grouped switch editor
 * as a modal launched from the card. Preserves every guard: manager banner (not
 * editable), self cannot edit own grants (disabled + access.refresh on save),
 * inactive warning, and no-escalation (server-enforced — the editor offers the
 * full registry exactly as before and surfaces the server's rejection).
 * ======================================================================== */
function ManagePermissionsModal({
  member,
  onClose,
  onSaved,
}: {
  member: StaffMemberListItem | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const { notify } = useToast();
  const access = useHotelAccess();
  const m = t.staff.matrix;

  const [payload, setPayload] = useState<StaffPermissionsPayload | null>(null);
  const { selected, toggle, setSection, reset } = useCodeSelection();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!member) return;
    let cancelled = false;
    setPayload(null);
    setError(null);
    getStaffPermissions(member.id)
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
        reset(data.granted);
      })
      .catch((err) => {
        if (!cancelled) setError(messageForError(err, t));
      });
    return () => {
      cancelled = true;
    };
  }, [member, t, reset]);

  const dirty = (() => {
    if (!payload) return false;
    const granted = new Set(payload.granted);
    if (granted.size !== selected.size) return true;
    for (const code of selected) if (!granted.has(code)) return true;
    return false;
  })();

  const editable = payload !== null && !payload.is_manager && !payload.is_self;

  async function save() {
    if (!payload) return;
    setBusy(true);
    setError(null);
    try {
      await putStaffPermissions(payload.membership, [...selected]);
      // Editing your OWN grants changes what the sidebar may show. (Self-edit is
      // disabled below, so this is a safety net that matches the old matrix.)
      if (payload.is_self) access?.refresh();
      notify(m.savedMsg);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const isManager = payload?.is_manager ?? false;

  return (
    <Modal
      open={member !== null}
      onClose={onClose}
      title={m.modalTitle}
      closeLabel={t.common.close}
      size="xl"
      footer={
        payload && !isManager ? (
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              {t.common.cancel}
            </Button>
            <Button onClick={save} loading={busy} disabled={!dirty || !editable}>
              {m.save}
            </Button>
          </>
        ) : (
          <Button variant="secondary" onClick={onClose}>
            {t.common.close}
          </Button>
        )
      }
    >
      <div className="stack">
        {member ? (
          <p className="muted">{m.forMember.replace("{name}", member.full_name)}</p>
        ) : null}
        {error ? <Alert tone="error">{error}</Alert> : null}

        {payload === null && error === null ? (
          <LoadingState label={t.common.loading} />
        ) : null}

        {payload && isManager ? <Alert tone="info">{m.managerAll}</Alert> : null}

        {payload && !isManager ? (
          <>
            {payload.is_self ? <p className="muted">{m.selfCannotEdit}</p> : null}
            {!payload.is_active ? <Alert tone="warning">{m.inactiveNote}</Alert> : null}
            <PermissionSectionsEditor
              registry={payload.registry}
              selected={selected}
              onToggle={toggle}
              onSection={setSection}
              disabled={payload.is_self}
              idPrefix="mng-perm"
            />
          </>
        ) : null}
      </div>
    </Modal>
  );
}

/* ==========================================================================
 * Link an existing user (single step — permissions are managed later from the
 * member's card).
 * ======================================================================== */
function LinkUserModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const f = t.staff.form;
  const [form, setForm] = useState<LinkExistingBody>({ email: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ email: "", job_title: "", staff_code: "", notes: "" });
      setError(null);
    }
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.email.trim()) return setError(f.emailRequired);
    setBusy(true);
    setError(null);
    try {
      await linkExistingUser(form);
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
      title={f.linkTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-link-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="staff-link-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={f.email} htmlFor="sl-email">
          <Input
            id="sl-email"
            type="email"
            value={form.email}
            onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
          />
        </FormField>
        <div className="form-grid">
          <FormField label={f.jobTitle} htmlFor="sl-title" hint={f.jobTitleHint}>
            <Input
              id="sl-title"
              value={form.job_title ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, job_title: e.target.value }))}
            />
          </FormField>
          <FormField label={f.staffCode} htmlFor="sl-code">
            <Input
              id="sl-code"
              value={form.staff_code ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, staff_code: e.target.value }))}
            />
          </FormField>
        </div>
      </form>
    </Modal>
  );
}

function EditStaffModal({
  row,
  onClose,
  onSaved,
}: {
  row: StaffMemberListItem | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const f = t.staff.form;
  const [form, setForm] = useState<StaffUpdateBody>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (row) {
      setForm({
        full_name: row.full_name,
        phone: row.phone,
        job_title: row.job_title,
        staff_code: row.staff_code,
      });
      setError(null);
    }
  }, [row]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!row) return;
    if (!form.full_name?.trim()) return setError(f.nameRequired);
    setBusy(true);
    setError(null);
    try {
      await updateStaffMember(row.id, form);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={row !== null}
      onClose={onClose}
      title={f.editTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-edit-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="staff-edit-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={f.fullName} htmlFor="se-name">
            <Input
              id="se-name"
              value={form.full_name ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, full_name: e.target.value }))}
            />
          </FormField>
          <FormField label={f.phone} htmlFor="se-phone">
            <Input
              id="se-phone"
              value={form.phone ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, phone: e.target.value }))}
            />
          </FormField>
          <FormField label={f.jobTitle} htmlFor="se-title" hint={f.jobTitleHint}>
            <Input
              id="se-title"
              value={form.job_title ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, job_title: e.target.value }))}
            />
          </FormField>
          <FormField label={f.staffCode} htmlFor="se-code">
            <Input
              id="se-code"
              value={form.staff_code ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, staff_code: e.target.value }))}
            />
          </FormField>
        </div>
        <FormField label={f.notes} htmlFor="se-notes">
          <Input
            id="se-notes"
            value={form.notes ?? ""}
            onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function DeactivateModal({
  row,
  onClose,
  onDone,
}: {
  row: StaffMemberListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const s = t.staff.list;
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (row) {
      setReason("");
      setError(null);
    }
  }, [row]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!row) return;
    setBusy(true);
    setError(null);
    try {
      await deactivateStaffMember(row.id, reason.trim());
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={row !== null}
      onClose={onClose}
      title={s.deactivateTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-deactivate-form" type="submit" variant="danger" loading={busy}>
            {s.deactivate}
          </Button>
        </>
      }
    >
      <form id="staff-deactivate-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="warning">{s.deactivateWarning}</Alert>
        <FormField label={s.deactivateReason} htmlFor="sd-reason">
          <Input id="sd-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}

function ResetPasswordModal({
  row,
  onClose,
  onDone,
}: {
  row: StaffMemberListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const s = t.staff.list;
  const f = t.staff.form;
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (row) {
      setPassword("");
      setError(null);
    }
  }, [row]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!row) return;
    if (password.length < 8) return setError(f.passwordRequired);
    setBusy(true);
    setError(null);
    try {
      await resetStaffPassword(row.id, password);
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={row !== null}
      onClose={onClose}
      title={s.resetTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-reset-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="staff-reset-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="warning">{s.resetHint}</Alert>
        <FormField label={s.newPassword} htmlFor="sr-pass">
          <PasswordInput
            id="sr-pass"
            value={password}
            showLabel={t.auth.showPassword}
            hideLabel={t.auth.hidePassword}
            onChange={(e) => setPassword(e.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function ChangeEmailModal({
  row,
  onClose,
  onDone,
}: {
  row: StaffMemberListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const s = t.staff.list;
  const f = t.staff.form;
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (row) {
      setEmail(row.email);
      setError(null);
    }
  }, [row]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!row) return;
    if (!email.trim()) return setError(f.emailRequired);
    setBusy(true);
    setError(null);
    try {
      await changeStaffEmail(row.id, email.trim());
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={row !== null}
      onClose={onClose}
      title={s.changeEmailTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-email-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="staff-email-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={s.changeEmailLabel} htmlFor="sce-email">
          <Input id="sce-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}

function DeleteModal({
  row,
  onClose,
  onDone,
}: {
  row: StaffMemberListItem | null;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const { t } = useI18n();
  const s = t.staff.list;
  const [deleteUser, setDeleteUser] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (row) {
      setDeleteUser(false);
      setError(null);
    }
  }, [row]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!row) return;
    setBusy(true);
    setError(null);
    try {
      const result = await deleteStaffMember(row.id, deleteUser);
      onDone(result.user_deleted !== null ? s.deletedWithUserMsg : s.deletedMsg);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={row !== null}
      onClose={onClose}
      title={s.deleteTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="staff-delete-form" type="submit" variant="danger" loading={busy}>
            {s.deleteConfirm}
          </Button>
        </>
      }
    >
      <form id="staff-delete-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Alert tone="warning">{s.deleteWarning}</Alert>
        <Switch
          id="sd-delete-user"
          checked={deleteUser}
          onChange={setDeleteUser}
          label={s.deleteUserLabel}
        />
      </form>
    </Modal>
  );
}
