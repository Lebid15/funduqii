"use client";

import type { LucideIcon } from "lucide-react";

import { cx } from "@/lib/utils";

import { Icon } from "./Icon";

export interface TabItem {
  key: string;
  label: string;
  icon?: LucideIcon;
}

interface TabsProps {
  tabs: TabItem[];
  active: string;
  onChange: (key: string) => void;
}

/** Central tab bar. Labels are translated by the caller. */
export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={tab.key === active}
          className={cx("tabs__tab", tab.key === active && "tabs__tab--active")}
          onClick={() => onChange(tab.key)}
        >
          {tab.icon ? <Icon icon={tab.icon} size="sm" /> : null}
          {tab.label}
        </button>
      ))}
    </div>
  );
}
