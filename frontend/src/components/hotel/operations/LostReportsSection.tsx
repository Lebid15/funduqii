"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  Ban,
  Check,
  Clock,
  FileSearch,
  HandCoins,
  Link2,
  Link2Off,
  MapPin,
  Package,
  PackageSearch,
  Search,
  Ticket,
  User,
  XCircle,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  Modal,
  Pagination,
  SectionHeader,
  Select,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  cancelLostReport,
  closeUnfoundLostReport,
  createLostReport,
  handoverLostReport,
  listLostReportCandidates,
  listLostReports,
  matchLostReport,
  setLostReportStatus,
  unmatchLostReport,
  type LostReportCreateBody,
} from "@/lib/api/operations";
import { listGuests } from "@/lib/api/guests";
import { messageForError } from "@/lib/api/errors";
import type {
  Guest,
  LostFoundCategory,
  LostFoundClaimProofType,
  LostFoundItemListItem,
  LostReportListItem,
  LostReportStatus,
} from "@/lib/api/types";
import { formatDateTime, lostReportStatusTone } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

import {
  OperationCard,
  type OperationMenuItem,
  type OperationPrimaryAction,
} from "./OperationCard";
import { StatCards, type OperationStat } from "./StatCards";
import { useCan } from "./operationsShared";

const PAGE_SIZE = 25;
const CATEGORIES: LostFoundCategory[] = [
  "electronics",
  "documents",
  "clothing",
  "jewelry",
  "money",
  "luggage",
  "other",
];
const STATUSES: LostReportStatus[] = [
  "open",
  "searching",
  "matched",
  "returned",
  "closed_unfound",
  "cancelled",
];
const PROOF_TYPES: LostFoundClaimProofType[] = [
  "identity_last4",
  "receipt_reference",
  "ownership_description",
  "other",
];

interface LrStats {
  open: number | null;
  searching: number | null;
  matched: number | null;
  returned: number | null;
}

/**
 * One lost-report record as an OperationCard. A standalone component (mirrors
 * HousekeepingTab's HkCard extraction) so the list never calls a render helper
 * that reaches parent refs during render — every action is a plain prop the
 * parent wires to its state / ref-touching runners. State-computes ONE primary
 * plus a "More" menu from (status, permission); terminal reports render
 * read-only (no primary, no menu).
 */
function LrCard({
  report,
  canStatus,
  busy,
  onMatch,
  onStartSearching,
  onCloseUnfound,
  onCancel,
  onHandover,
  onUnmatch,
}: {
  report: LostReportListItem;
  canStatus: boolean;
  busy: boolean;
  onMatch: () => void;
  onStartSearching: () => void;
  onCloseUnfound: () => void;
  onCancel: () => void;
  onHandover: () => void;
  onUnmatch: () => void;
}) {
  const { t, locale } = useI18n();
  const lr = t.operations.lr;
  const lf = t.operations.lf;
  const summary = report.matched_found_item_summary;

  let primary: OperationPrimaryAction | null = null;
  const menu: OperationMenuItem[] = [];

  if ((report.status === "open" || report.status === "searching") && canStatus) {
    // While a start-searching action is in flight for this card, show the busy
    // state on the primary and lock the menu (a11y N-2, matches the found tab).
    primary = { label: lr.match, icon: Link2, onClick: onMatch, loading: busy, disabled: busy };
    if (report.status === "open") {
      menu.push({
        key: "start",
        label: lr.startSearching,
        icon: Search,
        onSelect: onStartSearching,
        disabled: busy,
      });
    }
    menu.push({
      key: "close-unfound",
      label: lr.closeUnfound,
      icon: XCircle,
      onSelect: onCloseUnfound,
      disabled: busy,
    });
    menu.push({
      key: "cancel",
      label: lr.cancel,
      icon: Ban,
      danger: true,
      onSelect: onCancel,
      disabled: busy,
    });
  } else if (report.status === "matched" && canStatus) {
    primary = { label: lr.handover, icon: HandCoins, onClick: onHandover };
    menu.push({
      key: "unmatch",
      label: lr.unmatch,
      icon: Link2Off,
      onSelect: onUnmatch,
    });
  }

  return (
    <OperationCard
      accent={lostReportStatusTone(report.status)}
      number={report.report_number}
      title={lf.categories[report.category]}
      note={report.description?.trim() ? report.description : null}
      ariaLabel={`${lr.title} ${report.report_number}`}
      moreLabel={t.operations.moreActions}
      badges={
        <>
          <Badge tone={lostReportStatusTone(report.status)} variant="filled">
            {lr.status[report.status]}
          </Badge>
          <Badge tone="neutral">{lf.categories[report.category]}</Badge>
          <Badge tone="neutral" variant="outline" icon={PackageSearch}>
            {lr.badge.lostReport}
          </Badge>
        </>
      }
      facts={[
        {
          key: "reporter",
          label: lr.reporterName,
          value: report.reporter_name || "—",
          icon: User,
        },
        {
          key: "lastSeen",
          label: lr.lastSeenLocation,
          value: report.last_seen_location || "—",
          icon: MapPin,
        },
        {
          key: "lostAt",
          label: lr.lostAt,
          value: formatDateTime(report.lost_at, locale),
          icon: Clock,
        },
        ...(report.guest_name
          ? [{ key: "guest", label: lr.guest, value: report.guest_name, icon: User }]
          : []),
        ...(report.reservation_number
          ? [
              {
                key: "reservation",
                label: lr.reservation,
                value: <bdi dir="ltr">{report.reservation_number}</bdi>,
                icon: Ticket,
              },
            ]
          : []),
        ...(summary
          ? [
              {
                key: "matched",
                label: lr.matchedItem,
                value: (
                  <span>
                    <bdi dir="ltr">{summary.item_number}</bdi>
                    {` · ${summary.title}`}
                  </span>
                ),
                icon: Package,
              },
            ]
          : []),
      ]}
      primary={primary}
      menu={menu}
    />
  );
}

/** A guest-reported lost-item cycle (open → searching → matched → returned, or a
 * terminal close-unfound / cancel), matched by hand to an existing found item.
 * Self-contained: owns its list, stat tiles, filters and all action modals. The
 * only lifted state is the CREATE modal's open flag — its trigger button lives in
 * the shared type bar (LostFoundTab), so the parent drives it via `createOpen`. */
export function LostReportsSection({
  createOpen,
  onCreateClose,
}: {
  createOpen: boolean;
  onCreateClose: () => void;
}) {
  const { t } = useI18n();
  const { notify } = useToast();
  const lr = t.operations.lr;
  const lf = t.operations.lf;
  const can = useCan();

  const [rows, setRows] = useState<LostReportListItem[]>([]);
  const [count, setCount] = useState(0);
  const [stats, setStats] = useState<LrStats>({
    open: null,
    searching: null,
    matched: null,
    returned: null,
  });
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Flips true after the FIRST settled load — the initial load owns the full
  // LoadingState / ErrorState, later fetches keep the cards mounted (a11y M1).
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  // The report id of the in-flight card action (start-searching) — gives that
  // card a busy/loading treatment, matching the found tab (a11y N-2).
  const [busyId, setBusyId] = useState<number | null>(null);

  const loadedOnceRef = useRef(false);
  const mountedRef = useRef(true);
  const seqRef = useRef(0);
  const resultsRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef(false);

  const [matchTarget, setMatchTarget] = useState<LostReportListItem | null>(null);
  const [handoverTarget, setHandoverTarget] = useState<LostReportListItem | null>(null);
  const [reasonAction, setReasonAction] = useState<{
    report: LostReportListItem;
    kind: "unmatch" | "closeUnfound" | "cancel";
  } | null>(null);

  const load = useCallback(async () => {
    const seq = (seqRef.current += 1);
    setLoading(true);
    setError(null);
    try {
      const [items, open, searching, matched, returned] = await Promise.all([
        listLostReports({
          page,
          search: query || undefined,
          status: status || undefined,
          category: category || undefined,
        }),
        listLostReports({ status: "open", page: 1 }),
        listLostReports({ status: "searching", page: 1 }),
        listLostReports({ status: "matched", page: 1 }),
        listLostReports({ status: "returned", page: 1 }),
      ]);
      if (seqRef.current !== seq) return;
      setRows(items.results);
      setCount(items.count);
      setStats({
        open: open.count,
        searching: searching.count,
        matched: matched.count,
        returned: returned.count,
      });
      loadedOnceRef.current = true;
      setHasLoadedOnce(true);
    } catch (err) {
      if (seqRef.current !== seq) return;
      const message = messageForError(err, t);
      // BACKGROUND refetch failure — keep the cards, surface a non-blocking toast;
      // the full ErrorState + retry is reserved for the initial load.
      if (loadedOnceRef.current) notify(message, "error");
      else setError(message);
    } finally {
      if (mountedRef.current && seqRef.current === seq) setLoading(false);
    }
  }, [page, query, status, category, t, notify]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // a11y M1 — after an ACTION-triggered reload settles, restore focus to the
  // stable results anchor if the acting control unmounted. Keyed on `rows` (a
  // fresh array per successful load) so it fires even when React coalesces the
  // loading toggle.
  useEffect(() => {
    if (loading || !restoreFocusRef.current) return;
    restoreFocusRef.current = false;
    const active = document.activeElement as HTMLElement | null;
    if (!active || active === document.body || !active.isConnected) {
      resultsRef.current?.focus();
    }
  }, [rows, loading]);

  const reloadAfterAction = useCallback(() => {
    restoreFocusRef.current = true;
    return load();
  }, [load]);

  async function run(id: number, action: () => Promise<unknown>, msg: string) {
    setBusyId(id);
    try {
      await action();
      notify(msg);
      await reloadAfterAction();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusyId(null);
    }
  }

  function applyStatusFilter(next: LostReportStatus) {
    setPage(1);
    setStatus((current) => (current === next ? "" : next));
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const statusOptions = STATUSES.map((s) => ({ value: s, label: lr.status[s] }));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: lf.categories[c] }));

  const statCards: OperationStat[] = [
    {
      key: "open",
      label: lr.stats.open,
      value: stats.open,
      icon: FileSearch,
      // Tile tone MIRRORS lostReportStatusTone("open") = "info" (owner decision 3
      // counter→card thread). SmartStatTone excludes `vip`, so the value is set
      // explicitly rather than derived from the BadgeTone-returning helper.
      tone: "info",
      active: status === "open",
      onFilter: () => applyStatusFilter("open"),
    },
    {
      key: "searching",
      label: lr.stats.searching,
      value: stats.searching,
      icon: Search,
      // Mirrors lostReportStatusTone("searching") = "warning".
      tone: "warning",
      active: status === "searching",
      onFilter: () => applyStatusFilter("searching"),
    },
    {
      key: "matched",
      label: lr.stats.matched,
      value: stats.matched,
      icon: Link2,
      // Mirrors lostReportStatusTone("matched") = "primary".
      tone: "primary",
      active: status === "matched",
      onFilter: () => applyStatusFilter("matched"),
    },
    {
      key: "returned",
      label: lr.stats.returned,
      value: stats.returned,
      icon: Check,
      tone: "success",
      active: status === "returned",
      onFilter: () => applyStatusFilter("returned"),
    },
  ];

  const showInitialLoading = loading && !hasLoadedOnce;
  const showInitialError = !showInitialLoading && !hasLoadedOnce && error !== null;
  const backgroundRefreshing = loading && hasLoadedOnce;
  const resultsAnnouncement =
    !loading && hasLoadedOnce
      ? count === 0
        ? t.operations.noResults
        : t.operations.resultsCount.replace("{count}", String(count))
      : "";

  const canStatus = can("lost_found.status_update");

  const reasonModalCopy = reasonAction
    ? {
        unmatch: {
          title: lr.unmatchTitle,
          submit: lr.unmatch,
          danger: false,
          message: lr.unmatchedMsg,
          action: (id: number, reason: string) => unmatchLostReport(id, reason),
        },
        closeUnfound: {
          title: lr.closeUnfoundTitle,
          submit: lr.closeUnfound,
          danger: false,
          message: lr.closedUnfoundMsg,
          action: (id: number, reason: string) => closeUnfoundLostReport(id, reason),
        },
        cancel: {
          title: lr.cancelTitle,
          submit: lr.cancel,
          danger: true,
          message: lr.cancelledMsg,
          action: (id: number, reason: string) => cancelLostReport(id, reason),
        },
      }[reasonAction.kind]
    : null;

  return (
    <>
      <StatCards stats={statCards} loading={loading} ariaLabel={lr.title} />

      <Card>
        <SectionHeader title={lr.title} />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            setQuery(search);
          }}
        >
          <FilterBar>
            <FormField label={t.common.search} htmlFor="lr-search">
              <Input
                id="lr-search"
                value={search}
                placeholder={lr.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
              />
            </FormField>
            <FormField label={t.common.status} htmlFor="lr-status">
              <Select
                id="lr-status"
                value={status}
                placeholder={t.common.all}
                options={statusOptions}
                onChange={(e) => {
                  setPage(1);
                  setStatus(e.target.value);
                }}
              />
            </FormField>
            <FormField label={lr.categoryLabel} htmlFor="lr-category">
              <Select
                id="lr-category"
                value={category}
                placeholder={t.common.all}
                options={categoryOptions}
                onChange={(e) => {
                  setPage(1);
                  setCategory(e.target.value);
                }}
              />
            </FormField>
          </FilterBar>
        </form>

        {/* STABLE polite live region — always mounted; announces the settled
            result count by a text change (a11y M1). */}
        <div
          className="sr-only"
          aria-live="polite"
          aria-atomic="true"
          data-testid="lr-results-announce"
        >
          {resultsAnnouncement}
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
          <div className="op-results" ref={resultsRef} tabIndex={-1} aria-label={lr.title}>
            <div className="op-results__status" role="status" aria-live="polite">
              {backgroundRefreshing ? (
                <span className="op-results__searching">
                  <span className="spinner" aria-hidden="true" />
                  <span>{t.operations.updating}</span>
                </span>
              ) : null}
            </div>
            {rows.length === 0 ? (
              <EmptyState title={lr.empty} hint={lr.emptyHint} icon={PackageSearch} />
            ) : (
              <>
                <div
                  className="op-grid"
                  role="list"
                  aria-label={lr.title}
                  aria-busy={backgroundRefreshing}
                >
                  {rows.map((row) => (
                    <div role="listitem" key={row.id}>
                      <LrCard
                        report={row}
                        canStatus={canStatus}
                        busy={busyId === row.id}
                        onMatch={() => setMatchTarget(row)}
                        onStartSearching={() =>
                          run(
                            row.id,
                            () => setLostReportStatus(row.id, "searching"),
                            lr.startedSearchingMsg,
                          )
                        }
                        onCloseUnfound={() =>
                          setReasonAction({ report: row, kind: "closeUnfound" })
                        }
                        onCancel={() => setReasonAction({ report: row, kind: "cancel" })}
                        onHandover={() => setHandoverTarget(row)}
                        onUnmatch={() => setReasonAction({ report: row, kind: "unmatch" })}
                      />
                    </div>
                  ))}
                </div>
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
              </>
            )}
          </div>
        ) : null}
      </Card>

      <CreateLostReportModal
        open={createOpen}
        onClose={onCreateClose}
        onSaved={() => {
          onCreateClose();
          notify(lr.created);
          reloadAfterAction();
        }}
      />
      <CandidatePickerModal
        report={matchTarget}
        onClose={() => setMatchTarget(null)}
        onMatched={() => {
          setMatchTarget(null);
          notify(lr.matchedMsg);
          reloadAfterAction();
        }}
      />
      <LrHandoverModal
        report={handoverTarget}
        onClose={() => setHandoverTarget(null)}
        onDone={() => {
          setHandoverTarget(null);
          notify(lr.handedOverMsg);
          reloadAfterAction();
        }}
      />
      {reasonAction && reasonModalCopy ? (
        <ReasonModal
          open
          title={reasonModalCopy.title}
          submitLabel={reasonModalCopy.submit}
          danger={reasonModalCopy.danger}
          reportId={reasonAction.report.id}
          action={reasonModalCopy.action}
          onClose={() => setReasonAction(null)}
          onDone={() => {
            const message = reasonModalCopy.message;
            setReasonAction(null);
            notify(message);
            reloadAfterAction();
          }}
        />
      ) : null}
    </>
  );
}

/**
 * File a lost report (the guest-reported cycle). A reporter name is REQUIRED
 * (the backend rejects a blank one with 422 `claimant_required`); an optional
 * linked guest ties the report to a stay/guest for later matching.
 */
function CreateLostReportModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const lr = t.operations.lr;
  const lf = t.operations.lf;
  const [form, setForm] = useState<LostReportCreateBody>({ reporter_name: "" });
  const [guests, setGuests] = useState<Guest[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm({ reporter_name: "", category: "other", description: "" });
      setError(null);
      listGuests({ page_size: 100 })
        .then((res) => setGuests(res.results))
        .catch(() => setGuests([]));
    }
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.reporter_name.trim()) return setError(lr.reporterNameRequired);
    setBusy(true);
    setError(null);
    try {
      await createLostReport({
        ...form,
        reporter_name: form.reporter_name.trim(),
        lost_at: form.lost_at ? new Date(form.lost_at).toISOString() : null,
      });
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const guestOptions = guests.map((g) => ({ value: String(g.id), label: g.full_name }));
  const categoryOptions = CATEGORIES.map((c) => ({ value: c, label: lf.categories[c] }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={lr.createTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="lr-create-form" type="submit" loading={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="lr-create-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <p className="muted">{lr.createHint}</p>
        <FormField label={lr.reporterName} htmlFor="lrc-reporter">
          <Input
            id="lrc-reporter"
            value={form.reporter_name}
            onChange={(e) => setForm((p) => ({ ...p, reporter_name: e.target.value }))}
          />
        </FormField>
        <FormField label={lr.reporterPhone} htmlFor="lrc-phone">
          <Input
            id="lrc-phone"
            value={form.reporter_phone ?? ""}
            onChange={(e) => setForm((p) => ({ ...p, reporter_phone: e.target.value }))}
          />
        </FormField>
        <FormField label={lr.description} htmlFor="lrc-desc">
          <Textarea
            id="lrc-desc"
            rows={2}
            value={form.description ?? ""}
            onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
          />
        </FormField>
        <div className="form-grid">
          <FormField label={lr.categoryLabel} htmlFor="lrc-category">
            <Select
              id="lrc-category"
              value={form.category ?? "other"}
              options={categoryOptions}
              onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}
            />
          </FormField>
          <FormField label={lr.distinctiveMarks} htmlFor="lrc-marks">
            <Input
              id="lrc-marks"
              value={form.distinctive_marks ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, distinctive_marks: e.target.value }))}
            />
          </FormField>
          <FormField label={lr.lastSeenLocation} htmlFor="lrc-lastseen">
            <Input
              id="lrc-lastseen"
              value={form.last_seen_location ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, last_seen_location: e.target.value }))}
            />
          </FormField>
          <FormField label={lr.lostAt} htmlFor="lrc-lostat">
            <Input
              id="lrc-lostat"
              type="datetime-local"
              value={form.lost_at ?? ""}
              onChange={(e) => setForm((p) => ({ ...p, lost_at: e.target.value }))}
            />
          </FormField>
          <FormField label={lr.guest} htmlFor="lrc-guest">
            <Select
              id="lrc-guest"
              value={form.guest ? String(form.guest) : ""}
              placeholder={lr.noGuest}
              options={guestOptions}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  guest: e.target.value ? Number(e.target.value) : null,
                }))
              }
            />
          </FormField>
        </div>
        <FormField label={lr.internalNotes} htmlFor="lrc-notes">
          <Input
            id="lrc-notes"
            value={form.internal_notes ?? ""}
            onChange={(e) => setForm((p) => ({ ...p, internal_notes: e.target.value }))}
          />
        </FormField>
      </form>
    </Modal>
  );
}

/**
 * The MATCH flow: server-searchable picker of found items eligible to satisfy
 * this report. Selecting one posts `matchLostReport`; the backend enforces every
 * eligibility rule and surfaces conflicts (already matched / actively matched /
 * not matchable) as translated 409s, shown here as a toast.
 */
function CandidatePickerModal({
  report,
  onClose,
  onMatched,
}: {
  report: LostReportListItem | null;
  onClose: () => void;
  onMatched: () => void;
}) {
  const { t } = useI18n();
  const { notify } = useToast();
  const lr = t.operations.lr;
  const lf = t.operations.lf;
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  // The category filter FOLLOWS the report's own category by default
  // (override === null) but is switchable / clearable to "" (= any category), so
  // staff can surface a found item filed under a DIFFERENT category than the
  // report (code Low / design L4).
  const [categoryOverride, setCategoryOverride] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<LostFoundItemListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  // Bumped by "retry" to re-run the fetch after a network failure.
  const [reloadKey, setReloadKey] = useState(0);
  const requestSeq = useRef(0);

  const reportId = report?.id ?? null;
  // Derived so the seeded category is correct on the FIRST render (no double
  // fetch on open); `null` override means "follow the report's category".
  const category = categoryOverride ?? report?.category ?? "";

  // Reset the picker each time it opens for a new report.
  useEffect(() => {
    if (report) {
      setSearch("");
      setDebounced("");
      setCategoryOverride(null);
      setBusyId(null);
      setError(null);
      setReloadKey(0);
    }
  }, [report]);

  // Debounce the free-text search (server-side match).
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(handle);
  }, [search]);

  // Fetch eligible candidates whenever the picker is open / the search or
  // category changes / a retry is requested. A network failure surfaces a
  // DISTINCT error state (with retry) instead of masquerading as "no matches".
  useEffect(() => {
    if (reportId === null) {
      setCandidates([]);
      return;
    }
    const seq = (requestSeq.current += 1);
    setLoading(true);
    setError(null);
    listLostReportCandidates(reportId, {
      search: debounced || undefined,
      category: category || undefined,
    })
      .then((rows) => {
        if (seq !== requestSeq.current) return;
        setCandidates(rows);
      })
      .catch((err) => {
        if (seq !== requestSeq.current) return;
        setCandidates([]);
        setError(messageForError(err, t));
      })
      .finally(() => {
        if (seq === requestSeq.current) setLoading(false);
      });
  }, [reportId, category, debounced, reloadKey, t]);

  async function pick(itemId: number) {
    if (reportId === null) return;
    setBusyId(itemId);
    try {
      await matchLostReport(reportId, itemId);
      onMatched();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusyId(null);
    }
  }

  const candidateCategoryOptions = CATEGORIES.map((c) => ({
    value: c,
    label: lf.categories[c],
  }));

  return (
    <Modal
      open={report !== null}
      onClose={onClose}
      title={lr.matchTitle}
      closeLabel={t.common.close}
      footer={
        <Button variant="secondary" onClick={onClose} disabled={busyId !== null}>
          {t.common.close}
        </Button>
      }
    >
      <div className="stack">
        <p className="muted">{lr.matchHint}</p>
        <div className="form-grid">
          <FormField label={t.common.search} htmlFor="lr-candidate-search">
            <Input
              id="lr-candidate-search"
              value={search}
              placeholder={lr.candidateSearchPlaceholder}
              onChange={(e) => setSearch(e.target.value)}
            />
          </FormField>
          <FormField label={lr.categoryLabel} htmlFor="lr-candidate-category">
            <Select
              id="lr-candidate-category"
              value={category}
              placeholder={t.common.all}
              options={candidateCategoryOptions}
              onChange={(e) => setCategoryOverride(e.target.value)}
            />
          </FormField>
        </div>
        {/* Polite region: error > loading > empty > the settled candidate COUNT
            (reusing the found list's resultsCount key) — a11y L-1. */}
        <div className="sr-only" role="status" aria-live="polite">
          {error
            ? error
            : loading
              ? t.common.loading
              : candidates.length === 0
                ? lr.candidateEmpty
                : t.operations.resultsCount.replace("{count}", String(candidates.length))}
        </div>
        {error ? (
          <ErrorState
            title={t.states.errorTitle}
            message={error}
            retryLabel={t.common.retry}
            onRetry={() => setReloadKey((k) => k + 1)}
          />
        ) : loading && candidates.length === 0 ? (
          <LoadingState label={t.common.loading} />
        ) : candidates.length === 0 ? (
          <EmptyState title={lr.candidateEmpty} icon={PackageSearch} />
        ) : (
          <ul className="op-candidates" role="list">
            {candidates.map((item) => (
              <li key={item.id} className="op-candidate" role="listitem">
                <div className="op-candidate__body">
                  <span className="op-candidate__title">{item.title}</span>
                  <span className="op-candidate__meta">
                    <bdi dir="ltr">{item.item_number}</bdi>
                    {` · ${lf.categories[item.category]}`}
                    {item.stored_location ? ` · ${item.stored_location}` : ""}
                  </span>
                </div>
                <Button
                  type="button"
                  size="sm"
                  icon={Link2}
                  loading={busyId === item.id}
                  disabled={busyId !== null}
                  // Item-specific accessible name (WCAG 2.4.6 / 4.1.2) — the
                  // visible label stays the short "Select"/"اختيار"/"Seç".
                  aria-label={`${lr.candidateSelect}: ${item.title} ${item.item_number}`}
                  onClick={() => pick(item.id)}
                >
                  {lr.candidateSelect}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}

/**
 * Hand over the matched item to its owner — the SAME contract as the found-item
 * HandOverModal. A recipient name is always required; a recipient phone is
 * required UNLESS the report is linked to a known guest. Sensitivity comes from
 * the MATCHED item (`matched_found_item_summary.requires_strong_claim_proof`),
 * NOT the report's own category: for a sensitive match the proof fields are
 * shown and required, for a normal match there is no proof section at all. The
 * backend re-enforces every rule (422 `claimant_required` /
 * `recipient_contact_required` / `claim_proof_required`), surfaced here as a
 * translated error.
 */
function LrHandoverModal({
  report,
  onClose,
  onDone,
}: {
  report: LostReportListItem | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const lr = t.operations.lr;
  const lf = t.operations.lf;
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [proofType, setProofType] = useState<LostFoundClaimProofType>("identity_last4");
  const [proofReference, setProofReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Sensitivity is the MATCHED item's flag, never the report's own category. A
  // report linked to a known guest makes the recipient phone optional (mirrors
  // the found-item HandOverModal's `hasLinkedGuest`).
  const sensitive = report?.matched_found_item_summary?.requires_strong_claim_proof === true;
  const hasLinkedGuest = report?.guest != null;

  useEffect(() => {
    if (report) {
      setName("");
      setPhone("");
      setNote("");
      setProofType("identity_last4");
      setProofReference("");
      setError(null);
    }
  }, [report]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!report) return;
    // Recipient name is always required; a phone is required unless the report
    // is tied to a linked guest; sensitive matches additionally need proof.
    if (!name.trim()) return setError(t.operations.errors.claimantRequired);
    if (!phone.trim() && !hasLinkedGuest)
      return setError(t.operations.errors.recipientContactRequired);
    if (sensitive && (!proofType || !proofReference.trim())) {
      return setError(lf.proofRequired);
    }
    setBusy(true);
    setError(null);
    try {
      await handoverLostReport(report.id, {
        recipient_name: name.trim(),
        recipient_phone: phone.trim(),
        note: note.trim(),
        // Proof travels ONLY for a sensitive match; the backend re-checks the
        // matched item's own flag (claim_proof_required 422).
        ...(sensitive
          ? { claim_proof_type: proofType, claim_proof_reference: proofReference.trim() }
          : {}),
      });
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const proofOptions = PROOF_TYPES.map((p) => ({ value: p, label: lf.proofTypes[p] }));

  return (
    <Modal
      open={report !== null}
      onClose={onClose}
      title={lr.handoverTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="lr-handover-form" type="submit" loading={busy}>
            {lr.handover}
          </Button>
        </>
      }
    >
      <form id="lr-handover-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <p className="muted">{lr.handoverHint}</p>
        {hasLinkedGuest ? (
          <Alert tone="info">
            {lf.linkedGuest}
            {report?.guest_name ? `: ${report.guest_name}` : ""}
          </Alert>
        ) : null}
        <div className="form-grid">
          <FormField label={lr.recipientName} htmlFor="lr-ho-name">
            <Input id="lr-ho-name" value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField label={lr.recipientPhone} htmlFor="lr-ho-phone">
            <Input id="lr-ho-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </FormField>
        </div>
        {/* Faint contact rule (mirrors the found HandOverModal): phone-or-guest. */}
        <p className="muted small">{lf.handoverContactHint}</p>
        <FormField label={lr.note} htmlFor="lr-ho-note">
          <Input id="lr-ho-note" value={note} onChange={(e) => setNote(e.target.value)} />
        </FormField>
        {/* Proof section ONLY for a sensitive MATCHED item — mirrors the
            found-item HandOverModal (warning tone + required proof). */}
        {sensitive ? (
          <>
            <Alert tone="warning">{lf.sensitiveHint}</Alert>
            <div className="form-grid">
              <FormField label={lf.proofTypeLabel} htmlFor="lr-ho-prooftype">
                <Select
                  id="lr-ho-prooftype"
                  value={proofType}
                  options={proofOptions}
                  onChange={(e) => setProofType(e.target.value as LostFoundClaimProofType)}
                />
              </FormField>
              <FormField label={lf.proofReference} htmlFor="lr-ho-proofref">
                <Input
                  id="lr-ho-proofref"
                  value={proofReference}
                  onChange={(e) => setProofReference(e.target.value)}
                />
              </FormField>
            </div>
          </>
        ) : null}
      </form>
    </Modal>
  );
}

/** Shared reason-required modal for unmatch / close-unfound / cancel — each
 * needs a single mandatory reason and posts a distinct action. */
function ReasonModal({
  open,
  title,
  submitLabel,
  danger,
  reportId,
  action,
  onClose,
  onDone,
}: {
  open: boolean;
  title: string;
  submitLabel: string;
  danger: boolean;
  reportId: number;
  action: (id: number, reason: string) => Promise<unknown>;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const lr = t.operations.lr;
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
    if (!reason.trim()) return setError(lr.reasonRequired);
    setBusy(true);
    setError(null);
    try {
      await action(reportId, reason.trim());
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
      title={title}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button
            form="lr-reason-form"
            type="submit"
            variant={danger ? "danger" : "primary"}
            loading={busy}
          >
            {submitLabel}
          </Button>
        </>
      }
    >
      <form id="lr-reason-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={lr.reason} htmlFor="lr-reason">
          <Input id="lr-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}
