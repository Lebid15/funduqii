"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { Ban, Check, XCircle } from "lucide-react";

import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  type Column,
} from "@/components/ui";
import { VoidDialog } from "@/components/hotel/finance/shared";
import { voidCharge } from "@/lib/api/finance";
import { listStayServiceLines } from "@/lib/api/guestServices";
import { messageForError } from "@/lib/api/errors";
import type { GuestFolioDirectoryRow, GuestServiceLine } from "@/lib/api/types";
import { formatDateTime, formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Read the stay's OPEN-folio SERVICE line items (guest extra services + posted
 * service orders), INCLUDING voided ones (void history is operational). A
 * charge-level Void — gated on `finance.charge_void` — reuses the EXISTING
 * finance `voidCharge` endpoint with the line's `id` (= FolioCharge id).
 *
 * This surface deliberately offers NOTHING else financial: no record-payment,
 * settle, refund, close/reopen folio, void-whole-folio, invoice, adjustment,
 * discount, edit-room-charge or add-folio.
 */
/**
 * A voided line no longer counts toward the folio, so its amounts are struck
 * through and muted rather than reading as live money. This is ADDITIVE to the
 * explicit "Voided" badge + reason + actor already rendered in the status cell —
 * never colour/decoration alone.
 */
function voidedTextStyle(line: GuestServiceLine): CSSProperties | undefined {
  if (line.status !== "voided") return undefined;
  return { textDecoration: "line-through", opacity: 0.65 };
}

export function ViewServicesModal({
  stay,
  canVoid,
  onClose,
  onChanged,
}: {
  stay: GuestFolioDirectoryRow | null;
  /** Resolved `finance.charge_void` — enables the per-line Void action. */
  canVoid: boolean;
  onClose: () => void;
  /** Fired after a successful void so the directory can refetch totals/counts. */
  onChanged: () => void;
}) {
  const { t, locale } = useI18n();
  const g = t.guestFolio;
  const open = stay !== null;
  const stayId = stay?.stay_id ?? null;

  const [lines, setLines] = useState<GuestServiceLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voidLine, setVoidLine] = useState<GuestServiceLine | null>(null);
  const seqRef = useRef(0);
  const contentRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef(false);

  const load = useCallback(async () => {
    if (stayId === null) return;
    const seq = (seqRef.current += 1);
    setLoading(true);
    setError(null);
    try {
      const rows = await listStayServiceLines(stayId);
      if (seqRef.current !== seq) return;
      setLines(rows);
    } catch (err) {
      if (seqRef.current !== seq) return;
      setError(messageForError(err, t));
    } finally {
      if (seqRef.current === seq) setLoading(false);
    }
  }, [stayId, t]);

  useEffect(() => {
    if (open) {
      setVoidLine(null);
      load();
    }
  }, [open, load]);

  // After a void-triggered reload settles, focus would otherwise be LOST: the
  // VoidDialog restores focus to the Void button, then the reload re-renders that
  // line as voided and the Void button unmounts, dropping focus to document.body
  // while this modal is still open. Same restore pattern as FolioDirectoryTab.
  useEffect(() => {
    if (loading || !restoreFocusRef.current) return;
    restoreFocusRef.current = false;
    const active = document.activeElement as HTMLElement | null;
    if (!active || active === document.body || !active.isConnected) {
      contentRef.current?.focus();
    }
  }, [lines, loading]);

  async function confirmVoid(reason: string) {
    if (!voidLine) return;
    // Reuse the EXISTING finance void-charge endpoint on the line's charge id.
    await voidCharge(voidLine.id, reason);
    setVoidLine(null);
    restoreFocusRef.current = true;
    await load();
    onChanged();
  }

  const columns: Column<GuestServiceLine>[] = [
    {
      key: "description",
      header: g.viewModal.item,
      render: (line) => (
        <div className="stack" style={{ gap: "0.2rem" }}>
          <bdi style={voidedTextStyle(line)}>
            {line.service_name_snapshot || line.description}
          </bdi>
          {/* A VARIABLE-priced line posted with a unit-price override carries the
              mandatory reason it was changed — show it, otherwise the amount
              looks unexplained next to the catalogue price. */}
          {line.price_override_reason ? (
            <span className="muted small">
              {g.viewModal.overrideReason}: <bdi>{line.price_override_reason}</bdi>
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: "quantity",
      header: g.viewModal.quantity,
      align: "end",
      render: (line) => (
        <bdi dir="ltr" style={voidedTextStyle(line)}>
          {line.quantity}
        </bdi>
      ),
    },
    {
      key: "unit_amount",
      header: g.viewModal.unitAmount,
      align: "end",
      render: (line) => (
        <bdi dir="ltr" style={voidedTextStyle(line)}>
          {formatMoney(line.unit_amount, line.currency, locale)}
        </bdi>
      ),
    },
    {
      key: "tax",
      header: g.viewModal.tax,
      align: "end",
      render: (line) => (
        <bdi dir="ltr" style={voidedTextStyle(line)}>
          {formatMoney(line.tax_amount, line.currency, locale)}
        </bdi>
      ),
    },
    {
      key: "total_amount",
      header: g.viewModal.total,
      align: "end",
      render: (line) => (
        <bdi dir="ltr" style={voidedTextStyle(line)}>
          {formatMoney(line.total_amount, line.currency, locale)}
        </bdi>
      ),
    },
    {
      key: "created_by",
      header: g.viewModal.staff,
      render: (line) => line.created_by || t.common.notAvailable,
    },
    {
      key: "created_at",
      header: g.viewModal.time,
      render: (line) => formatDateTime(line.created_at, locale),
    },
    {
      key: "status",
      header: t.common.status,
      render: (line) => {
        const voided = line.status === "voided";
        return (
          <div className="stack" style={{ gap: "0.2rem" }}>
            <Badge
              tone={voided ? "danger" : "success"}
              icon={voided ? XCircle : Check}
            >
              {voided ? g.viewModal.statusVoided : g.viewModal.statusPosted}
            </Badge>
            {voided && line.void_reason ? (
              <span className="muted small">
                {g.viewModal.voidReason}: {line.void_reason}
              </span>
            ) : null}
            {voided && line.voided_by ? (
              <span className="muted small">
                {g.viewModal.voidedBy}: {line.voided_by}
              </span>
            ) : null}
          </div>
        );
      },
    },
  ];

  if (canVoid) {
    columns.push({
      key: "actions",
      header: g.viewModal.actions,
      align: "end",
      render: (line) =>
        line.status === "posted" ? (
          <Button
            size="sm"
            variant="dangerSoft"
            icon={Ban}
            onClick={() => setVoidLine(line)}
          >
            {g.viewModal.void}
          </Button>
        ) : null,
    });
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={g.viewModal.title}
        closeLabel={t.common.close}
        size="xl"
        footer={
          <Button variant="secondary" onClick={onClose}>
            {t.common.close}
          </Button>
        }
      >
        {/* Stable focusable anchor: survives every reload, so focus always has
            somewhere to land inside the modal when the acting control unmounts. */}
        <div className="stack" ref={contentRef} tabIndex={-1}>
          {stay ? (
            <p className="muted small">
              {g.viewModal.forGuest.replace("{guest}", stay.guest_name)}{" "}
              <bdi dir="ltr">{stay.room_number}</bdi>
            </p>
          ) : null}
          {loading ? <LoadingState label={t.common.loading} /> : null}
          {!loading && error ? (
            <ErrorState
              title={t.states.errorTitle}
              message={error}
              retryLabel={t.common.retry}
              onRetry={load}
            />
          ) : null}
          {!loading && !error && lines.length === 0 ? (
            <EmptyState title={g.viewModal.empty} hint={g.viewModal.emptyHint} />
          ) : null}
          {!loading && !error && lines.length > 0 ? (
            <DataTable
              columns={columns}
              rows={lines}
              rowKey={(line) => line.id}
              caption={g.viewModal.title}
            />
          ) : null}
        </div>
      </Modal>

      <VoidDialog
        open={voidLine !== null}
        title={g.viewModal.voidTitle}
        description={g.viewModal.voidHint}
        confirmLabel={g.viewModal.void}
        onClose={() => setVoidLine(null)}
        onConfirm={confirmVoid}
      />
    </>
  );
}
