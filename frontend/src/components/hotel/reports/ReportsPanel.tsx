"use client";

import { useMemo, useState } from "react";
import {
  ArrowLeftRight,
  BarChart3,
  BedDouble,
  CalendarCheck,
  ClipboardList,
  Receipt,
  Users,
  UtensilsCrossed,
} from "lucide-react";

import { Button, Card, FilterBar, FormField, Input, Tabs, type TabItem } from "@/components/ui";
import type { ReportRange } from "@/lib/api/reports";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { FinanceTab } from "./FinanceTab";
import { GuestsTab } from "./GuestsTab";
import { OccupancyTab } from "./OccupancyTab";
import { OperationsTab } from "./OperationsTab";
import { OverviewTab } from "./OverviewTab";
import { ReservationsTab } from "./ReservationsTab";
import { ServicesTab } from "./ServicesTab";
import { ShiftsTab } from "./ShiftsTab";

function iso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function ReportsPanel() {
  const { t } = useI18n();
  const access = useHotelAccess();
  const f = t.reports.filters;

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [applied, setApplied] = useState<ReportRange>({});
  const [tab, setTab] = useState("overview");

  function apply(from: string, to: string) {
    setDateFrom(from);
    setDateTo(to);
    setApplied(from && to ? { date_from: from, date_to: to } : {});
  }

  function quick(range: "today" | "last7" | "thisMonth" | "lastMonth") {
    const now = new Date();
    if (range === "today") {
      apply(iso(now), iso(now));
    } else if (range === "last7") {
      const from = new Date(now);
      from.setDate(now.getDate() - 6);
      apply(iso(from), iso(now));
    } else if (range === "thisMonth") {
      apply(iso(new Date(now.getFullYear(), now.getMonth(), 1)), iso(now));
    } else {
      const first = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const last = new Date(now.getFullYear(), now.getMonth(), 0);
      apply(iso(first), iso(last));
    }
  }

  const allTabs: Array<TabItem & { required?: string[] }> = [
    { key: "overview", label: t.reports.tabs.overview, icon: BarChart3 },
    { key: "reservations", label: t.reports.tabs.reservations, icon: CalendarCheck },
    { key: "occupancy", label: t.reports.tabs.occupancy, icon: BedDouble },
    { key: "guests", label: t.reports.tabs.guests, icon: Users },
    {
      key: "finance",
      label: t.reports.tabs.finance,
      icon: Receipt,
      required: ["reports.finance"],
    },
    { key: "services", label: t.reports.tabs.services, icon: UtensilsCrossed },
    {
      key: "operations",
      label: t.reports.tabs.operations,
      icon: ClipboardList,
      required: ["reports.operations"],
    },
    {
      key: "shifts",
      label: t.reports.tabs.shifts,
      icon: ArrowLeftRight,
      required: ["reports.shifts"],
    },
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
      {tab === "reservations" ? <ReservationsTab range={applied} /> : null}
      {tab === "occupancy" ? <OccupancyTab range={applied} /> : null}
      {tab === "guests" ? <GuestsTab range={applied} /> : null}
      {tab === "finance" ? <FinanceTab range={applied} /> : null}
      {tab === "services" ? <ServicesTab range={applied} /> : null}
      {tab === "operations" ? <OperationsTab range={applied} /> : null}
      {tab === "shifts" ? <ShiftsTab range={applied} /> : null}
    </>
  );
}
