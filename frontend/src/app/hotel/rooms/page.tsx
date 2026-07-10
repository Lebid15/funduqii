"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BedDouble,
  Building2,
  Layers,
  LayoutDashboard,
  Package,
  Plus,
  RefreshCw,
  Rows3,
} from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { Button, PageHeader, Tabs, type TabItem } from "@/components/ui";
import {
  BulkRoomCreateModal,
  FloorsManagerModal,
  FloorsTab,
  RoomFormModal,
  RoomOperationalBoard,
  RoomTypesManagerModal,
  RoomTypesTab,
  RoomsTab,
} from "@/components/hotel/rooms";
import { listFloors, listRoomTypes } from "@/lib/api/rooms";
import type { Floor, RoomType } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

/**
 * Rooms console (owner UX round): a page-level action toolbar (room types /
 * floors / add room / add range / refresh) above the OPERATIONAL board tab,
 * then the management tabs exactly as before. The toolbar hosts the quick
 * modals; saving anything (or pressing refresh) remounts the active tab so
 * every list refetches.
 */
export default function RoomsPage() {
  const { t } = useI18n();
  const access = useHotelAccess();
  const b = t.rooms.board;
  const [tab, setTab] = useState("overview");
  const [refreshKey, setRefreshKey] = useState(0);

  const [floors, setFloors] = useState<Floor[]>([]);
  const [types, setTypes] = useState<RoomType[]>([]);
  const [typesOpen, setTypesOpen] = useState(false);
  const [floorsOpen, setFloorsOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);

  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
  const canManage = can("rooms.create", "rooms.update");
  const canCreate = can("rooms.create");

  const loadLists = useCallback(async () => {
    try {
      const [f, ty] = await Promise.all([listFloors(), listRoomTypes()]);
      setFloors(f.results);
      setTypes(ty.results);
    } catch {
      // The tabs surface their own load errors; the toolbar degrades quietly.
    }
  }, []);

  useEffect(() => {
    loadLists();
  }, [loadLists]);

  function refresh() {
    loadLists();
    setRefreshKey((k) => k + 1);
  }

  const tabs: TabItem[] = [
    { key: "overview", label: b.tabTitle, icon: LayoutDashboard },
    { key: "floors", label: t.rooms.tabs.floors, icon: Building2 },
    { key: "types", label: t.rooms.tabs.types, icon: Package },
    { key: "rooms", label: t.rooms.tabs.rooms, icon: BedDouble },
  ];

  return (
    <PageContainer>
      <PageHeader title={t.rooms.title} subtitle={t.rooms.subtitle} />

      {/* Owner spec: the operations toolbar sits at the very top of the
          page — visible on every tab, permission-aware, wraps on mobile. */}
      <div className="page-toolbar" role="toolbar" aria-label={t.rooms.title}>
        {canManage ? (
          <Button variant="secondary" icon={Package} onClick={() => setTypesOpen(true)}>
            {b.roomTypes}
          </Button>
        ) : null}
        {canManage ? (
          <Button variant="secondary" icon={Layers} onClick={() => setFloorsOpen(true)}>
            {b.editFloors}
          </Button>
        ) : null}
        {canCreate ? (
          <Button icon={Plus} onClick={() => setAddOpen(true)}>
            {b.addRoomUnit}
          </Button>
        ) : null}
        {canCreate ? (
          <Button variant="secondary" icon={Rows3} onClick={() => setBulkOpen(true)}>
            {b.addRoomRange}
          </Button>
        ) : null}
        <Button variant="ghost" icon={RefreshCw} onClick={refresh}>
          {b.refresh}
        </Button>
      </div>

      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "overview" ? <RoomOperationalBoard key={refreshKey} /> : null}
      {tab === "floors" ? <FloorsTab key={refreshKey} /> : null}
      {tab === "types" ? <RoomTypesTab key={refreshKey} /> : null}
      {tab === "rooms" ? <RoomsTab key={refreshKey} /> : null}

      <RoomTypesManagerModal
        open={typesOpen}
        types={types}
        onClose={() => {
          setTypesOpen(false);
          refresh();
        }}
        onChanged={loadLists}
      />
      <FloorsManagerModal
        open={floorsOpen}
        floors={floors}
        onClose={() => setFloorsOpen(false)}
        onChanged={refresh}
      />
      <RoomFormModal
        open={addOpen}
        floors={floors}
        types={types}
        onClose={() => setAddOpen(false)}
        onSaved={() => {
          setAddOpen(false);
          refresh();
        }}
      />
      <BulkRoomCreateModal
        open={bulkOpen}
        floors={floors}
        types={types}
        onClose={() => setBulkOpen(false)}
        onCreated={refresh}
      />
    </PageContainer>
  );
}
