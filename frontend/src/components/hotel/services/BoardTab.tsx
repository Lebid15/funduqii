"use client";

import { useCallback, useEffect, useState } from "react";
import { ClipboardList, PackageCheck } from "lucide-react";

import { Badge, Button, EmptyState, ErrorState, LoadingState, useToast } from "@/components/ui";
import { listServiceOrders, setServiceOrderStatus } from "@/lib/api/services";
import { messageForError } from "@/lib/api/errors";
import type { ServiceOrderListItem } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Money-free preparation board, collapsed to the visible cycle new → delivered.
 *
 * The operational status flow no longer surfaces preparing/ready — an open order
 * (submitted, plus any legacy preparing/ready) sits in "new" and moves straight
 * to "delivered" (the backend accepts the skip). Settlement (folio / direct) is
 * money and lives on the order card in the list view; the board never shows it.
 */
export function BoardTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const [open, setOpen] = useState<ServiceOrderListItem[]>([]);
  const [delivered, setDelivered] = useState<ServiceOrderListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // "New" merges every not-yet-delivered open status (submitted + any legacy
      // preparing/ready); "delivered" keeps the money-free awaiting-settlement set.
      const [submitted, preparing, ready, deliveredRes] = await Promise.all([
        listServiceOrders({ status: "submitted" }),
        listServiceOrders({ status: "preparing" }),
        listServiceOrders({ status: "ready" }),
        listServiceOrders({ status: "delivered", settlement: "unsettled" }),
      ]);
      setOpen([...submitted.results, ...preparing.results, ...ready.results]);
      setDelivered(deliveredRes.results);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  async function markDelivered(order: ServiceOrderListItem) {
    setBusyId(order.id);
    try {
      await setServiceOrderStatus(order.id, "delivered");
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

  if (open.length === 0 && delivered.length === 0)
    return <EmptyState title={t.services.board.empty} hint={t.services.board.hint} icon={ClipboardList} />;

  const columns = [
    { key: "new", label: t.services.status.submitted, rows: open, canDeliver: true },
    { key: "delivered", label: t.services.status.delivered, rows: delivered, canDeliver: false },
  ] as const;

  return (
    <div className="board-grid">
      {columns.map((col) => (
        <section key={col.key} className="board-col" aria-label={col.label}>
          <header className="board-col__head">
            <span className="board-col__title">{col.label}</span>
            <Badge tone="neutral">{col.rows.length}</Badge>
          </header>
          <div className="board-col__body">
            {col.rows.map((order) => (
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
                {col.canDeliver ? (
                  <Button
                    size="sm"
                    icon={PackageCheck}
                    onClick={() => markDelivered(order)}
                    loading={busyId === order.id}
                  >
                    {t.services.orders.markDelivered}
                  </Button>
                ) : (
                  <span className="muted small">{t.services.board.awaitingPost}</span>
                )}
              </article>
            ))}
            {col.rows.length === 0 ? (
              <p className="muted small">{t.services.board.columnEmpty}</p>
            ) : null}
          </div>
        </section>
      ))}
    </div>
  );
}
