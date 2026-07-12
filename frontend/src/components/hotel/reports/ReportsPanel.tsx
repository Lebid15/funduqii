"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeftRight,
  Banknote,
  BarChart3,
  BedDouble,
  CalendarCheck,
  CalendarClock,
  ClipboardList,
  CreditCard,
  FileText,
  Percent,
  TrendingUp,
  Users,
  UtensilsCrossed,
  Wallet,
} from "lucide-react";

import { Button, Card, FilterBar, FormField, Input, Tabs, type TabItem } from "@/components/ui";
import { getOverviewReport, type ReportRange } from "@/lib/api/reports";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { DailyCloseTab } from "./DailyCloseTab";
import { ExpensesTab } from "./ExpensesTab";
import { FinanceOverviewTab } from "./FinanceOverviewTab";
import { FoliosTab } from "./FoliosTab";
import { GuestsTab } from "./GuestsTab";
import { OccupancyTab } from "./OccupancyTab";
import { OperationsTab } from "./OperationsTab";
import { OverviewTab } from "./OverviewTab";
import { PaymentsTab } from "./PaymentsTab";
import { ReservationsTab } from "./ReservationsTab";
import { RestaurantCafeTab } from "./RestaurantCafeTab";
import { RevenueTab } from "./RevenueTab";
import { ShiftsTab } from "./ShiftsTab";
import { TaxesTab } from "./TaxesTab";

/** Format a Date as YYYY-MM-DD from its LOCAL parts (no UTC shift). */
function fmtLocal(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Parse a YYYY-MM-DD string into a local Date (no UTC shift). */
function parseIsoDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

export function ReportsPanel() {
  const { t } = useI18n();
  const access = useHotelAccess();
  const f = t.reports.filters;

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [applied, setApplied] = useState<ReportRange>({});
  const [tab, setTab] = useState("overview");
  // Quick ranges are anchored to the hotel's CURRENT BUSINESS DATE (server),
  // never the browser clock. Fetched once from the operational overview whose
  // default `date_to` equals the business date; falls back to the local clock
  // only until it arrives.
  const [businessDate, setBusinessDate] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getOverviewReport()
      .then((data) => {
        if (!cancelled) setBusinessDate(data.date_to);
      })
      .catch(() => {
        // Non-fatal: quick ranges fall back to the local clock.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function apply(from: string, to: string) {
    setDateFrom(from);
    setDateTo(to);
    setApplied(from && to ? { date_from: from, date_to: to } : {});
  }

  function quick(range: "today" | "last7" | "thisMonth" | "lastMonth") {
    const base = businessDate ? parseIsoDate(businessDate) : new Date();
    if (range === "today") {
      apply(fmtLocal(base), fmtLocal(base));
    } else if (range === "last7") {
      const from = new Date(base);
      from.setDate(base.getDate() - 6);
      apply(fmtLocal(from), fmtLocal(base));
    } else if (range === "thisMonth") {
      apply(fmtLocal(new Date(base.getFullYear(), base.getMonth(), 1)), fmtLocal(base));
    } else {
      const first = new Date(base.getFullYear(), base.getMonth() - 1, 1);
      const last = new Date(base.getFullYear(), base.getMonth(), 0);
      apply(fmtLocal(first), fmtLocal(last));
    }
  }

  const allTabs: Array<TabItem & { required?: string[] }> = [
    { key: "overview", label: t.reports.tabs.overview, icon: BarChart3 },
    {
      key: "finance",
      label: t.reports.tabs.finance,
      icon: Wallet,
      required: ["reports.finance"],
    },
    {
      key: "revenue",
      label: t.reports.tabs.revenue,
      icon: TrendingUp,
      required: ["reports.finance"],
    },
    {
      key: "payments",
      label: t.reports.tabs.payments,
      icon: Banknote,
      required: ["reports.finance"],
    },
    {
      key: "expenses",
      label: t.reports.tabs.expenses,
      icon: CreditCard,
      required: ["reports.finance"],
    },
    {
      key: "taxes",
      label: t.reports.tabs.taxes,
      icon: Percent,
      required: ["reports.finance"],
    },
    {
      key: "folios",
      label: t.reports.tabs.folios,
      icon: FileText,
      required: ["reports.finance"],
    },
    {
      key: "restaurantCafe",
      label: t.reports.tabs.restaurantCafe,
      icon: UtensilsCrossed,
      required: ["reports.finance"],
    },
    { key: "occupancy", label: t.reports.tabs.occupancy, icon: BedDouble },
    {
      key: "shifts",
      label: t.reports.tabs.shifts,
      icon: ArrowLeftRight,
      required: ["reports.shifts"],
    },
    {
      key: "dailyClose",
      label: t.reports.tabs.dailyClose,
      icon: CalendarClock,
      required: ["reports.shifts"],
    },
    {
      key: "operations",
      label: t.reports.tabs.operations,
      icon: ClipboardList,
      required: ["reports.operations"],
    },
    { key: "reservations", label: t.reports.tabs.reservations, icon: CalendarCheck },
    { key: "guests", label: t.reports.tabs.guests, icon: Users },
  ];
  const tabs = useMemo(
    () =>
      allTabs.filter(
        (item) => !item.required || !access || access.can(...item.required),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [access, t],
  );

  return (
    <>
      <Card>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            apply(dateFrom, dateTo);
          }}
        >
          <FilterBar>
            <FormField label={f.dateFrom} htmlFor="rp-from">
              <Input
                id="rp-from"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </FormField>
            <FormField label={f.dateTo} htmlFor="rp-to">
              <Input
                id="rp-to"
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </FormField>
          </FilterBar>
          <div className="cluster">
            <Button type="submit" size="sm">
              {f.apply}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => apply("", "")}>
              {f.reset}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => quick("today")}>
              {f.today}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => quick("last7")}>
              {f.last7}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => quick("thisMonth")}>
              {f.thisMonth}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => quick("lastMonth")}>
              {f.lastMonth}
            </Button>
          </div>
        </form>
      </Card>

      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <OverviewTab range={applied} /> : null}
      {tab === "finance" ? <FinanceOverviewTab range={applied} /> : null}
      {tab === "revenue" ? <RevenueTab range={applied} /> : null}
      {tab === "payments" ? <PaymentsTab range={applied} /> : null}
      {tab === "expenses" ? <ExpensesTab range={applied} /> : null}
      {tab === "taxes" ? <TaxesTab range={applied} /> : null}
      {tab === "folios" ? <FoliosTab range={applied} /> : null}
      {tab === "restaurantCafe" ? <RestaurantCafeTab range={applied} /> : null}
      {tab === "occupancy" ? <OccupancyTab range={applied} /> : null}
      {tab === "shifts" ? <ShiftsTab range={applied} /> : null}
      {tab === "dailyClose" ? <DailyCloseTab range={applied} /> : null}
      {tab === "operations" ? <OperationsTab range={applied} /> : null}
      {tab === "reservations" ? <ReservationsTab range={applied} /> : null}
      {tab === "guests" ? <GuestsTab range={applied} /> : null}
    </>
  );
}
