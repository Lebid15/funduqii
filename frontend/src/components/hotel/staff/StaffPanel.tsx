"use client";

import { useState } from "react";
import { BookOpenCheck, LayoutDashboard, ShieldCheck, Users } from "lucide-react";

import { Tabs, type TabItem } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { OverviewTab } from "./OverviewTab";
import { PermissionsMatrixTab } from "./PermissionsMatrixTab";
import { RegistryTab } from "./RegistryTab";
import { StaffListTab } from "./StaffListTab";

export function StaffPanel() {
  const { t } = useI18n();
  const [tab, setTab] = useState("overview");
  const [matrixTarget, setMatrixTarget] = useState<number | null>(null);

  const tabs: TabItem[] = [
    { key: "overview", label: t.staff.tabs.overview, icon: LayoutDashboard },
    { key: "list", label: t.staff.tabs.list, icon: Users },
    { key: "matrix", label: t.staff.tabs.matrix, icon: ShieldCheck },
    { key: "registry", label: t.staff.tabs.registry, icon: BookOpenCheck },
  ];

  return (
    <>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <OverviewTab /> : null}
      {tab === "list" ? (
        <StaffListTab
          onOpenPermissions={(membershipId) => {
            setMatrixTarget(membershipId);
            setTab("matrix");
          }}
        />
      ) : null}
      {tab === "matrix" ? <PermissionsMatrixTab initialTarget={matrixTarget} /> : null}
      {tab === "registry" ? <RegistryTab /> : null}
    </>
  );
}
