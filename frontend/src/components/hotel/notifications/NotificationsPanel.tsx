"use client";

import { useState } from "react";
import { Activity, Bell, LayoutDashboard } from "lucide-react";

import { Tabs, type TabItem } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { ActivityTab } from "./ActivityTab";
import { InboxTab } from "./InboxTab";
import { OverviewTab } from "./OverviewTab";

export function NotificationsPanel() {
  const { t } = useI18n();
  const access = useHotelAccess();
  const [tab, setTab] = useState("overview");

  const allTabs: Array<TabItem & { required?: string[] }> = [
    {
      key: "overview",
      label: t.notifications.tabs.overview,
      icon: LayoutDashboard,
      required: ["notifications.view"],
    },
    {
      key: "inbox",
      label: t.notifications.tabs.inbox,
      icon: Bell,
      required: ["notifications.view"],
    },
    {
      key: "activity",
      label: t.notifications.tabs.activity,
      icon: Activity,
      required: ["activity.view"],
    },
  ];
  const tabs = allTabs.filter(
    (item) => !item.required || !access || access.can(...item.required),
  );
  const active = tabs.some((item) => item.key === tab) ? tab : tabs[0]?.key ?? "overview";

  return (
    <>
      <Tabs tabs={tabs} active={active} onChange={setTab} />
      {active === "overview" ? <OverviewTab /> : null}
      {active === "inbox" ? <InboxTab /> : null}
      {active === "activity" ? <ActivityTab /> : null}
    </>
  );
}
