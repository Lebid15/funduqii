"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  BedDouble,
  Building2,
  CalendarRange,
  ClipboardList,
  HandCoins,
  ListChecks,
  Lock,
  Plus,
  Receipt,
  Users,
  Wallet,
} from "lucide-react";

import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  Pagination,
  SectionHeader,
  useToast,
} from "@/components/ui";
import {
  OperationCard,
  type OperationFact,
  type OperationMenuItem,
} from "@/components/hotel/operations/OperationCard";
import { StatCards, type OperationStat } from "@/components/hotel/operations/StatCards";
import { listFolioDirectory } from "@/lib/api/guestServices";
import { messageForError } from "@/lib/api/errors";
import type { GuestFolioDirectoryRow } from "@/lib/api/types";
import { folioStatusTone, formatDate, formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

import { AddServiceModal } from "./AddServiceModal";
import { ViewServicesModal } from "./ViewServicesModal";
import { useCan, useCanSeeMoney } from "./shared";

const PAGE_SIZE = 25;

export function FolioDirectoryTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const g = t.guestFolio;
  const can = useCan();
  const canSeeMoney = useCanSeeMoney();

  const [rows, setRows] = useState<GuestFolioDirectoryRow[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Flips true after the FIRST settled load — the initial load owns the full
  // LoadingState/ErrorState; later fetches keep the cards mounted (a11y).
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  const [addStay, setAddStay] = useState<GuestFolioDirectoryRow | null>(null);
  const [viewStay, setViewStay] = useState<GuestFolioDirectoryRow | null>(null);

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
      const data = await listFolioDirectory({ page });
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
  }, [page, t, notify]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // After an ACTION-triggered reload settles, restore focus to the stable
  // results anchor if the acting control unmounted.
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

  // Client-side filter over the loaded page (the directory endpoint has no
  // search param). Matches guest name or room number.
  const query = search.trim().toLowerCase();
  const visibleRows = query
    ? rows.filter((row) =>
        `${row.guest_name} ${row.room_number}`.toLowerCase().includes(query),
      )
    : rows;

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const withServices = rows.filter((row) => row.service_count > 0).length;

  const statCards: OperationStat[] = [
    {
      key: "inHouse",
      label: g.stats.inHouse,
      value: hasLoadedOnce ? count : null,
      icon: Users,
      tone: "info",
    },
    {
      key: "withServices",
      label: g.stats.withServices,
      value: hasLoadedOnce ? withServices : null,
      icon: ClipboardList,
      tone: "primary",
    },
  ];

  const showInitialLoading = loading && !hasLoadedOnce;
  const showInitialError = !showInitialLoading && !hasLoadedOnce && error !== null;
  const backgroundRefreshing = loading && hasLoadedOnce;
  const resultsAnnouncement =
    !loading && hasLoadedOnce
      ? visibleRows.length === 0
        ? t.operations.noResults
        : t.operations.resultsCount.replace("{count}", String(visibleRows.length))
      : "";

  function renderCard(row: GuestFolioDirectoryRow) {
    const showMoney = canSeeMoney && row.service_total !== undefined;

    const facts: OperationFact[] = [
      {
        key: "roomType",
        label: g.card.roomType,
        value: <bdi>{row.room_type_name}</bdi>,
        icon: BedDouble,
      },
      {
        key: "floor",
        label: g.card.floor,
        value: (
          <span>
            <bdi>{row.floor_name}</bdi>
            {row.floor_number ? (
              <>
                {" · "}
                <bdi dir="ltr">{row.floor_number}</bdi>
              </>
            ) : null}
          </span>
        ),
        icon: Building2,
      },
      {
        key: "dates",
        label: g.card.stayDates,
        value: (
          <span>
            {formatDate(row.check_in_date, locale)}
            {" – "}
            {formatDate(row.check_out_date, locale)}
          </span>
        ),
        icon: CalendarRange,
      },
    ];

    if (showMoney) {
      facts.push(
        {
          key: "serviceTotal",
          label: g.card.serviceTotal,
          value: (
            <bdi dir="ltr">
              {formatMoney(row.service_total ?? null, row.currency ?? "", locale)}
            </bdi>
          ),
          icon: Receipt,
        },
        {
          key: "balance",
          label: g.card.balance,
          value: (
            <bdi dir="ltr">
              {formatMoney(row.balance ?? null, row.currency ?? "", locale)}
            </bdi>
          ),
          icon: Wallet,
        },
        {
          key: "paid",
          label: g.card.paid,
          value: (
            <bdi dir="ltr">
              {formatMoney(row.total_payments ?? null, row.currency ?? "", locale)}
            </bdi>
          ),
          icon: HandCoins,
        },
      );
    } else {
      // Money is OMITTED server-side without finance.view — show a "hidden"
      // affordance, NEVER a fabricated zero.
      facts.push({
        key: "hidden",
        label: g.card.financials,
        value: <span className="muted">{g.card.detailsHidden}</span>,
        icon: Lock,
      });
    }

    let primary: React.ComponentProps<typeof OperationCard>["primary"] = null;
    const menu: OperationMenuItem[] = [];
    if (can("service_orders.create")) {
      primary = {
        label: g.card.addService,
        icon: Plus,
        onClick: () => setAddStay(row),
      };
      menu.push({
        key: "view",
        label: g.card.viewServices,
        icon: ListChecks,
        onSelect: () => setViewStay(row),
      });
    } else {
      primary = {
        label: g.card.viewServices,
        icon: ListChecks,
        onClick: () => setViewStay(row),
      };
    }

    return (
      <OperationCard
        accent={row.folio_status ? folioStatusTone(row.folio_status) : "primary"}
        number={row.room_number}
        title={row.guest_name}
        ariaLabel={`${g.title} ${row.room_number}`}
        moreLabel={g.card.more}
        badges={
          <>
            {row.folio_status ? (
              <Badge tone={folioStatusTone(row.folio_status)}>
                {t.finance.folioStatus[row.folio_status]}
              </Badge>
            ) : null}
            <Badge tone="neutral" variant="outline" icon={ClipboardList}>
              {g.card.serviceCount.replace("{count}", String(row.service_count))}
            </Badge>
          </>
        }
        facts={facts}
        primary={primary}
        menu={menu}
      />
    );
  }

  return (
    <>
      <StatCards stats={statCards} loading={loading} ariaLabel={g.title} />

      <Card>
        <SectionHeader title={g.title} />
        <form
          onSubmit={(e) => {
            e.preventDefault();
          }}
        >
          <FilterBar>
            <FormField label={t.common.search} htmlFor="gf-search">
              <Input
                id="gf-search"
                value={search}
                placeholder={g.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
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
          data-testid="gf-results-announce"
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
          <div
            className="op-results"
            ref={resultsRef}
            tabIndex={-1}
            aria-label={g.title}
          >
            <div className="op-results__status" role="status" aria-live="polite">
              {backgroundRefreshing ? (
                <span className="op-results__searching">
                  <span className="spinner" aria-hidden="true" />
                  <span>{t.operations.updating}</span>
                </span>
              ) : null}
            </div>
            {visibleRows.length === 0 ? (
              <EmptyState title={g.empty} hint={g.emptyHint} icon={Users} />
            ) : (
              <>
                <div
                  className="op-grid"
                  role="list"
                  aria-label={g.title}
                  aria-busy={backgroundRefreshing}
                >
                  {visibleRows.map((row) => (
                    <div role="listitem" key={row.stay_id}>
                      {renderCard(row)}
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

      <AddServiceModal
        stay={addStay}
        canCharge={can("finance.charge_create")}
        onClose={() => setAddStay(null)}
        onAdded={() => {
          setAddStay(null);
          notify(g.addModal.added);
          reloadAfterAction();
        }}
      />
      <ViewServicesModal
        stay={viewStay}
        canVoid={can("finance.charge_void")}
        onClose={() => setViewStay(null)}
        onChanged={() => {
          notify(g.viewModal.voided);
          reloadAfterAction();
        }}
      />
    </>
  );
}
