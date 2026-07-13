"use client";

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import {
  BedDouble,
  CreditCard,
  FileText,
  Pencil,
  UserRound,
  Users,
} from "lucide-react";

import { Button, StepSummaryCard } from "@/components/ui";
import type { RoomAvailabilityRow } from "@/lib/api/types";
import { formatDate, formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

import {
  composeFullName,
  totalPersons,
  type ReservationDraft,
} from "./useReservationDraft";

/** Which step each review card jumps back to (mirrors the shell's STEPS order:
 * 0 guest · 1 companions · 2 documents · 3 booking). The stay/room and price
 * cards belong to the booking step itself (already on-screen above the review),
 * so they carry no jump-back affordance. */
const STEP_GUEST = 0;
const STEP_COMPANIONS = 1;
const STEP_DOCUMENTS = 2;

/**
 * §32 — the compact review shown as the LAST block of the booking step, leading
 * into Save. It summarizes every value the reservation is about to be created
 * with (guest, companions, documents, dates, floor + room, nights, persons,
 * nightly price, total, payment + currency, FX rate, remaining, immediate flag)
 * and offers a "jump back to edit" affordance for each earlier step. Money is
 * DISPLAY-only here (backend Decimal strings / estimates from the room rate);
 * the backend remains authoritative for the true total and remaining.
 */
export function ReservationReviewStep({
  draft,
  nights,
  selectedRoom,
  reservationCurrency,
  estimatedTotal,
  estimatedRemaining,
  onEditStep,
}: {
  draft: ReservationDraft;
  nights: number;
  selectedRoom: RoomAvailabilityRow | null;
  reservationCurrency: string;
  estimatedTotal: string | null;
  estimatedRemaining: string | null;
  onEditStep: (index: number) => void;
}) {
  const { t, locale } = useI18n();
  const r = t.reservations.wizard.review;
  const b = t.reservations.wizard.booking;

  const guest = draft.guest;
  const guestName =
    guest.full_name.trim() ||
    composeFullName(guest.first_name, guest.father_name, guest.last_name) ||
    "—";

  const adults = draft.companions.has_companions
    ? draft.companions.occupants.length
    : 0;
  const children = draft.companions.has_companions
    ? draft.companions.children
    : 0;

  const documentsCount = draft.pendingDocuments.filter(
    (doc) =>
      doc.doc_type !== "" && (doc.file !== null || doc.additionalFile !== null),
  ).length;

  const floor = selectedRoom
    ? selectedRoom.floor_name ||
      (selectedRoom.floor_number
        ? b.floorGroup.replace("{floor}", selectedRoom.floor_number)
        : b.noFloor)
    : r.noRoom;
  const room = selectedRoom ? selectedRoom.number : r.noRoom;

  const payment = draft.booking.payment;
  const hasPaid =
    payment.method !== "" &&
    ((payment.amount.trim() !== "" && Number(payment.amount) > 0) ||
      (payment.original_amount.trim() !== "" &&
        Number(payment.original_amount) > 0));
  const payCurrency = payment.currency || reservationCurrency;
  const isForeign = Boolean(reservationCurrency) && payCurrency !== reservationCurrency;

  const methodLabel =
    payment.method === "cash"
      ? b.method.cash
      : payment.method === "internal_electronic"
        ? b.method.internal_electronic
        : r.none;

  const paidValue: ReactNode = hasPaid
    ? isForeign
      ? `${formatMoney(payment.original_amount, payCurrency, locale)} · ${methodLabel}`
      : `${formatMoney(payment.amount, reservationCurrency, locale)} · ${methodLabel}`
    : r.none;

  const totalValue: ReactNode = selectedRoom
    ? estimatedTotal
      ? formatMoney(estimatedTotal, reservationCurrency, locale)
      : r.notPriced
    : r.noRoom;

  const nightlyValue: ReactNode = selectedRoom
    ? selectedRoom.base_rate
      ? formatMoney(selectedRoom.base_rate, reservationCurrency, locale)
      : r.notPriced
    : r.noRoom;

  const remainingValue: ReactNode =
    selectedRoom && estimatedRemaining
      ? formatMoney(estimatedRemaining, reservationCurrency, locale)
      : "—";

  const stayRows = [
    { label: r.checkIn, value: formatDate(draft.booking.check_in_date || null, locale) },
    { label: r.checkOut, value: formatDate(draft.booking.check_out_date || null, locale) },
    { label: r.floor, value: floor },
    { label: r.room, value: room },
    { label: r.nights, value: String(nights) },
    { label: r.persons, value: String(totalPersons(draft)) },
  ];

  const financialRows = [
    { label: r.nightlyPrice, value: nightlyValue },
    { label: r.total, value: totalValue },
    { label: r.paid, value: paidValue },
    ...(isForeign && hasPaid
      ? [
          { label: r.paymentCurrency, value: payCurrency },
          {
            label: r.exchangeRate,
            value: payment.exchange_rate.trim() || "—",
          },
        ]
      : []),
    { label: r.remaining, value: remainingValue },
    {
      label: r.immediate,
      value: draft.booking.immediate_check_in ? r.yes : r.no,
    },
  ];

  return (
    <div className="stack">
      <EditableSummary
        title={r.guestSection}
        icon={UserRound}
        rows={[
          { label: r.guestName, value: guestName },
          { label: r.phone, value: guest.phone.trim() || "—" },
        ]}
        editIndex={STEP_GUEST}
        editLabel={r.edit}
        onEditStep={onEditStep}
      />
      <EditableSummary
        title={r.companionsSection}
        icon={Users}
        rows={[
          { label: r.adults, value: String(adults) },
          { label: r.children, value: String(children) },
        ]}
        editIndex={STEP_COMPANIONS}
        editLabel={r.edit}
        onEditStep={onEditStep}
      />
      <EditableSummary
        title={r.documentsSection}
        icon={FileText}
        rows={[{ label: r.documentsCount, value: String(documentsCount) }]}
        editIndex={STEP_DOCUMENTS}
        editLabel={r.edit}
        onEditStep={onEditStep}
      />
      <StepSummaryCard title={r.staySection} icon={BedDouble} rows={stayRows} />
      <StepSummaryCard
        title={r.financialSection}
        icon={CreditCard}
        rows={financialRows}
        hint={b.reservationTotalEstimate}
      />
    </div>
  );
}

/** A summary card with a "jump back to edit" affordance beneath it. */
function EditableSummary({
  title,
  icon,
  rows,
  editIndex,
  editLabel,
  onEditStep,
}: {
  title: string;
  icon: LucideIcon;
  rows: { label: string; value: ReactNode }[];
  editIndex: number;
  editLabel: string;
  onEditStep: (index: number) => void;
}) {
  return (
    <div className="stack-tight">
      <StepSummaryCard title={title} icon={icon} rows={rows} />
      <div className="cluster">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          icon={Pencil}
          onClick={() => onEditStep(editIndex)}
        >
          {editLabel}
        </Button>
      </div>
    </div>
  );
}
