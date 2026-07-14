import type { LucideIcon } from "lucide-react";
import {
  CircleAlert,
  CircleArrowUp,
  CircleCheck,
  CircleDollarSign,
  CircleHelp,
  Undo2,
} from "lucide-react";

import type { ReservationPaymentStatus } from "@/lib/api/types";

import { Badge, type BadgeTone } from "./Badge";

/**
 * Every payment-status value the UI may receive. The backend union is currently
 * `unpaid | partial | paid` (see {@link ReservationPaymentStatus}); `refunded`
 * and `overpaid` are pre-mapped so the component stays forward-compatible if the
 * backend ever returns them — no status is invented on the client.
 */
export type PaymentStatusValue =
  | ReservationPaymentStatus
  | "refunded"
  | "overpaid";

interface PaymentStatusMeta {
  tone: BadgeTone;
  icon: LucideIcon;
}

/**
 * SINGLE SOURCE OF TRUTH for the payment-status visual meaning (variant + icon).
 * The value always comes from backend data — never recomputed on the client.
 * Every entry pairs a colour with a distinct icon so meaning is never conveyed
 * by colour alone (§13/§20). Rendered as a FILLED badge (white text + icon).
 */
export const PAYMENT_STATUS_META: Record<string, PaymentStatusMeta> = {
  paid: { tone: "success", icon: CircleCheck },
  partial: { tone: "warning", icon: CircleDollarSign },
  unpaid: { tone: "danger", icon: CircleAlert },
  refunded: { tone: "info", icon: Undo2 },
  overpaid: { tone: "primary", icon: CircleArrowUp },
};

const FALLBACK_META: PaymentStatusMeta = { tone: "neutral", icon: CircleHelp };

interface PaymentStatusBadgeProps {
  /** Backend payment-status value (never computed on the client). */
  status: PaymentStatusValue | null | undefined;
  /**
   * Translated labels keyed by status — already localized by the caller (e.g.
   * `t.reservations.card.paymentStatus`). Keeps this DS component decoupled from
   * any feature dictionary while text stays translated, never hardcoded.
   */
  labels: Partial<Record<PaymentStatusValue, string>>;
  className?: string;
}

/**
 * Central payment-status pill. Maps a backend `payment_status` to a filled Badge
 * with the right semantic tone + icon + translated label. Renders nothing when
 * the status is absent so callers can pass a nullable value directly.
 */
export function PaymentStatusBadge({
  status,
  labels,
  className,
}: PaymentStatusBadgeProps) {
  if (!status) return null;
  const meta = PAYMENT_STATUS_META[status] ?? FALLBACK_META;
  const label = labels[status] ?? status;
  return (
    <Badge tone={meta.tone} variant="filled" icon={meta.icon} className={className}>
      {label}
    </Badge>
  );
}
