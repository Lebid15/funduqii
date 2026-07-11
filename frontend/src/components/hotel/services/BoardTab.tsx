"use client";

import { useCallback, useEffect, useState } from "react";
import { BellRing, ChefHat, ClipboardList, PackageCheck } from "lucide-react";

import { Badge, Button, EmptyState, ErrorState, LoadingState, useToast } from "@/components/ui";
import { listServiceOrders, setServiceOrderStatus } from "@/lib/api/services";
import { messageForError } from "@/lib/api/errors";
import type { ServiceOrderListItem, ServiceOrderStatus } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** Simple preparation board: four status columns with explicit action buttons —
 * no drag/drop; the backend validates every transition. */
export function BoardTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [columns, setColumns] = useState<Record<string, ServiceOrderListItem[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [submitted, preparing, ready, delivered] = await Promise.all([
        listServiceOrders({ status: "submitted" }),
        listServiceOrders({ status: "preparing" }),
        listServiceOrders({ status: "ready" }),
        // Final closure: "awaiting settlement" replaces "not posted" —
        // direct-settled orders leave the board too.
        listServiceOrders({ status: "delivered", settlement: "unsettled" }),
      ]);
      setColumns({
        submitted: submitted.results,
        preparing: preparing.results,
        ready: ready.results,
        delivered: delivered.results,
      });
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  async function advance(order: ServiceOrderListItem, next: ServiceOrderStatus) {
    setBusyId(order.id);
    try {
      await setServiceOrderStatus(order.id, next);
      notify(t.services.saved);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <LoadingState label={t.common.loading} />;
  if (error)
    return (
      <ErrorState
        title={t.states.errorTitle}
        message={error}
        retryLabel={t.common.retry}
        onRetry={load}
      />
    );

  const defs = [
    { key: "submitted", icon: ClipboardList, next: "preparing" as const, nextLabel: t.services.orders.markPreparing },
    { key: "preparing", icon: ChefHat, next: "ready" as const, nextLabel: t.services.orders.markReady },
    { key: "ready", icon: BellRing, next: "delivered" as const, nextLabel: t.services.orders.markDelivered },
    { key: "delivered", icon: PackageCheck, next: null, nextLabel: "" },
  ];

  const empty = defs.every((d) => (columns[d.key] ?? []).length === 0);
  if (empty)
    return <EmptyState title={t.services.board.empty} hint={t.services.board.hint} icon={ChefHat} />;

  return (
    <div className="board-grid">
      {defs.map((def) => (
        <section key={def.key} className="board-col" aria-label={t.services.status[def.key as ServiceOrderStatus]}>
          <header className="board-col__head">
            <span className="board-col__title">{t.services.status[def.key as ServiceOrderStatus]}</span>
            <Badge tone="neutral">{(columns[def.key] ?? []).length}</Badge>
          </header>
          <div className="board-col__body">
            {(columns[def.key] ?? []).map((order) => (
              <article key={order.id} className="board-card">
                <div className="board-card__head">
                  <strong>{order.order_number}</strong>
                  <span className="muted small">
                    {order.room_number
                      ? `${t.services.orders.room} ${order.room_number}`
                      : order.table_number
                        ? `${t.services.orders.table} ${order.table_number}`
                        : order.customer_name || t.services.orders.walkIn}
                  </span>
                </div>
                <span className="muted small">{formatDateTime(order.ordered_at, locale)}</span>
                {def.next ? (
                  <Button
                    size="sm"
                    onClick={() => advance(order, def.next!)}
                    loading={busyId === order.id}
                  >
                    {def.nextLabel}
                  </Button>
                ) : (
                  <span className="muted small">{t.services.board.awaitingPost}</span>
                )}
              </article>
            ))}
            {(columns[def.key] ?? []).length === 0 ? (
              <p className="muted small">{t.services.board.columnEmpty}</p>
            ) : null}
          </div>
        </section>
      ))}
    </div>
  );
}
