"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Armchair, Ban, Pencil, Plus, RotateCcw, Trash2 } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  Modal,
  Pagination,
  Select,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import {
  createTable,
  deleteTable,
  listTables,
  setTableStatus,
  updateTable,
} from "@/lib/api/services";
import { isApiError, messageForError } from "@/lib/api/errors";
import type { RestaurantTable, ServiceOutlet } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { OrderCreateModal } from "./OrdersTab";
import { useEnabledOutlets } from "./useOutlets";

const PAGE_SIZE = 25;
const TABLE_STATUSES = ["available", "out_of_service"] as const;

/** Cosmetic permission gate — every API re-checks server-side regardless. */
function useCan() {
  const access = useHotelAccess();
  return (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));
}

export function TablesTab() {
  const { t } = useI18n();
  const { notify } = useToast();
  const can = useCan();
  const enabledOutlets = useEnabledOutlets();

  const [rows, setRows] = useState<RestaurantTable[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [outletFilter, setOutletFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [tableModal, setTableModal] = useState<{ open: boolean; edit: RestaurantTable | null }>({
    open: false,
    edit: null,
  });
  const [outOfService, setOutOfService] = useState<RestaurantTable | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RestaurantTable | null>(null);
  const [orderTable, setOrderTable] = useState<RestaurantTable | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const canManage = can("services.tables_manage");
  const canCreateOrder = can("service_orders.create");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listTables({
        page,
        outlet: outletFilter || undefined,
        status: statusFilter || undefined,
      });
      setRows(data.results);
      setCount(data.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, outletFilter, statusFilter, t]);

  useEffect(() => {
    load();
  }, [load]);

  async function backToService(table: RestaurantTable) {
    setBusyId(table.id);
    try {
      await setTableStatus(table.id, "available");
      notify(t.services.saved);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusyId(null);
    }
  }

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const outletOptions = enabledOutlets.map((o) => ({ value: o, label: t.services.outlets[o] }));
  const statusOptions = TABLE_STATUSES.map((s) => ({
    value: s,
    label: t.services.tables.statuses[s],
  }));

  const columns: Column<RestaurantTable>[] = [
    { key: "number", header: t.services.tables.number },
    { key: "name", header: t.services.tables.name, render: (r) => r.name || "—" },
    { key: "capacity", header: t.services.tables.capacity },
    {
      key: "outlet",
      header: t.services.outlet,
      render: (r) => t.services.outlets[r.outlet],
    },
    {
      key: "status",
      header: t.common.status,
      render: (r) => (
        <div className="cluster">
          <Badge tone={r.status === "available" ? "success" : "neutral"}>
            {t.services.tables.statuses[r.status]}
          </Badge>
          {r.status === "available" ? (
            <Badge tone={r.is_occupied ? "warning" : "neutral"}>
              {r.is_occupied ? t.services.tables.occupied : t.services.tables.free}
            </Badge>
          ) : null}
        </div>
      ),
    },
    {
      key: "open_order",
      header: t.services.tables.openOrder,
      render: (r) =>
        r.open_order ? (
          <span>
            {r.open_order.order_number}
            <span className="muted small">
              {" "}
              {r.open_order.customer_name || r.open_order.guest_name || ""}
            </span>
          </span>
        ) : (
          "—"
        ),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => (
        <div className="table__actions">
          {canCreateOrder && r.status === "available" && !r.is_occupied ? (
            <Button size="sm" icon={Plus} onClick={() => setOrderTable(r)}>
              {t.services.tables.newOrder}
            </Button>
          ) : null}
          {canManage ? (
            <>
              <Button
                size="sm"
                variant="secondary"
                icon={Pencil}
                onClick={() => setTableModal({ open: true, edit: r })}
              >
                {t.common.edit}
              </Button>
              {r.status === "available" ? (
                <Button size="sm" variant="secondary" icon={Ban} onClick={() => setOutOfService(r)}>
                  {t.services.tables.takeOutOfService}
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={RotateCcw}
                  loading={busyId === r.id}
                  onClick={() => backToService(r)}
                >
                  {t.services.tables.backToService}
                </Button>
              )}
              <Button size="sm" variant="danger" icon={Trash2} onClick={() => setDeleteTarget(r)}>
                {t.common.delete}
              </Button>
            </>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <Card>
        <FilterBar>
          <FormField label={t.services.outlet} htmlFor="tbl-outlet">
            <Select
              id="tbl-outlet"
              value={outletFilter}
              placeholder={t.common.all}
              options={outletOptions}
              onChange={(e) => {
                setPage(1);
                setOutletFilter(e.target.value);
              }}
            />
          </FormField>
          <FormField label={t.common.status} htmlFor="tbl-status">
            <Select
              id="tbl-status"
              value={statusFilter}
              placeholder={t.common.all}
              options={statusOptions}
              onChange={(e) => {
                setPage(1);
                setStatusFilter(e.target.value);
              }}
            />
          </FormField>
          {canManage ? (
            <div className="filter-bar__actions cluster">
              <Button icon={Plus} onClick={() => setTableModal({ open: true, edit: null })}>
                {t.services.tables.addTable}
              </Button>
            </div>
          ) : null}
        </FilterBar>
      </Card>

      {loading ? <LoadingState label={t.common.loading} /> : null}
      {!loading && error ? (
        <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} />
      ) : null}
      {!loading && !error ? (
        rows.length === 0 ? (
          <EmptyState
            title={t.services.tables.empty}
            hint={t.services.tables.emptyHint}
            icon={Armchair}
            action={
              canManage ? (
                <Button icon={Plus} onClick={() => setTableModal({ open: true, edit: null })}>
                  {t.services.tables.addTable}
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            <DataTable caption={t.services.tabs.tables} columns={columns} rows={rows} rowKey={(r) => r.id} />
            <Pagination
              page={page}
              totalPages={totalPages}
              onPageChange={setPage}
              labels={{
                previous: t.pagination.previous,
                next: t.pagination.next,
                status: t.pagination.page.replace("{page}", String(page)).replace("{total}", String(totalPages)),
              }}
            />
          </>
        )
      ) : null}

      <TableModal
        open={tableModal.open}
        edit={tableModal.edit}
        enabledOutlets={enabledOutlets}
        onClose={() => setTableModal({ open: false, edit: null })}
        onSaved={() => {
          setTableModal({ open: false, edit: null });
          notify(t.services.saved);
          load();
        }}
      />

      <OutOfServiceModal
        table={outOfService}
        onClose={() => setOutOfService(null)}
        onSaved={() => {
          setOutOfService(null);
          notify(t.services.saved);
          load();
        }}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t.services.tables.deleteTable}
        body={t.services.tables.deleteConfirm}
        confirmLabel={t.common.delete}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        onClose={() => setDeleteTarget(null)}
        onConfirm={async () => {
          if (!deleteTarget) return;
          try {
            await deleteTable(deleteTarget.id);
            notify(t.services.saved);
            load();
          } catch (err) {
            // Ever used in an order → history keeps it; suggest out-of-service.
            if (isApiError(err) && err.code === "resource_in_use") {
              notify(t.services.tables.deleteInUse, "error");
            } else {
              notify(messageForError(err, t), "error");
            }
          } finally {
            setDeleteTarget(null);
          }
        }}
      />

      <OrderCreateModal
        open={orderTable !== null}
        initialOutlet={orderTable?.outlet}
        initialTable={orderTable?.id}
        onClose={() => setOrderTable(null)}
        onSaved={() => {
          setOrderTable(null);
          notify(t.services.saved);
          load();
        }}
      />
    </>
  );
}

/* ------------------------------------------------------------------------- */
/* Create / edit                                                               */
/* ------------------------------------------------------------------------- */

function TableModal({
  open,
  edit,
  enabledOutlets,
  onClose,
  onSaved,
}: {
  open: boolean;
  edit: RestaurantTable | null;
  enabledOutlets: ServiceOutlet[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [outlet, setOutlet] = useState<ServiceOutlet>("restaurant");
  const [number, setNumber] = useState("");
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState("2");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setOutlet(edit ? edit.outlet : enabledOutlets[0] ?? "restaurant");
    setNumber(edit ? edit.number : "");
    setName(edit ? edit.name : "");
    setCapacity(edit ? String(edit.capacity) : "2");
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when (re)opened
  }, [open, edit]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!number.trim()) return setError(t.errors.validation);
    const cap = Number(capacity);
    if (!Number.isFinite(cap) || cap < 1) return setError(t.errors.validation);
    setBusy(true);
    setError(null);
    try {
      if (edit) {
        // The outlet is immutable after creation — only these fields change.
        await updateTable(edit.id, { number: number.trim(), name: name.trim(), capacity: cap });
      } else {
        await createTable({ outlet, number: number.trim(), name: name.trim(), capacity: cap });
      }
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const outletOptions = enabledOutlets.map((o) => ({ value: o, label: t.services.outlets[o] }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={edit ? t.services.tables.editTable : t.services.tables.addTable}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="svc-table-form" type="submit" loading={busy}>{t.common.save}</Button>
        </>
      }
    >
      <form id="svc-table-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          {edit ? (
            <FormField label={t.services.outlet} htmlFor="tb-outlet-fixed">
              <div className="cluster" id="tb-outlet-fixed">
                <Badge tone="neutral">{t.services.outlets[edit.outlet]}</Badge>
                <span className="muted small">{t.services.catalog.outletLocked}</span>
              </div>
            </FormField>
          ) : (
            <FormField label={t.services.outlet} htmlFor="tb-outlet">
              <Select
                id="tb-outlet"
                value={outlet}
                options={outletOptions}
                onChange={(e) => setOutlet(e.target.value as ServiceOutlet)}
              />
            </FormField>
          )}
          <FormField label={t.services.tables.number} htmlFor="tb-number">
            <Input id="tb-number" value={number} onChange={(e) => setNumber(e.target.value)} />
          </FormField>
          <FormField label={t.services.tables.name} htmlFor="tb-name">
            <Input id="tb-name" value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField label={t.services.tables.capacity} htmlFor="tb-capacity">
            <Input
              id="tb-capacity"
              type="number"
              min="1"
              step="1"
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
            />
          </FormField>
        </div>
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------------- */
/* Out of service (reason required)                                            */
/* ------------------------------------------------------------------------- */

function OutOfServiceModal({
  table,
  onClose,
  onSaved,
}: {
  table: RestaurantTable | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (table) {
      setReason("");
      setError(null);
    }
  }, [table]);

  if (!table) return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return setError(t.errors.validation);
    setBusy(true);
    setError(null);
    try {
      await setTableStatus(table!.id, "out_of_service", reason.trim());
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={t.services.tables.outOfServiceTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="svc-table-oos-form" type="submit" variant="danger" loading={busy}>
            {t.services.tables.takeOutOfService}
          </Button>
        </>
      }
    >
      <form id="svc-table-oos-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <p>{table.name ? `${table.number} — ${table.name}` : table.number}</p>
        <FormField label={t.services.tables.outOfServiceReason} htmlFor="tb-oos-reason">
          <Textarea id="tb-oos-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
      </form>
    </Modal>
  );
}
