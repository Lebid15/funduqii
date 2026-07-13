"use client";

import { useEffect, useMemo, useState } from "react";
import { BedDouble, CalendarClock, CreditCard, LogIn } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  FormField,
  Input,
  SectionCard,
  Select,
  Switch,
} from "@/components/ui";
import { AmenityChips } from "@/components/hotel/rooms/AmenityChips";
import { getSettings } from "@/lib/api/hotel";
import { getRoomAvailability, getReservationOverview } from "@/lib/api/reservations";
import type {
  ExpectedPaymentMethod,
  HotelSettings,
  RoomAvailabilityRow,
} from "@/lib/api/types";
import { formatCapacity, formatDate, formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useCurrentUser } from "@/lib/session/CurrentUserContext";

import { totalPersons } from "./useReservationDraft";
import type { ReservationDraftActions, ReservationDraft } from "./useReservationDraft";

/** The three payment methods the desk offers. `on_room_account` is a UI choice
 * that records NO payment (the charge is deferred to the folio) — it maps to an
 * empty deposit method so the body builder omits the deposit entirely. The two
 * real methods are valid `ReservationDepositMethod` values. */
type UiPayMethod = "cash" | "internal_electronic" | "on_room_account";
/** EXACTLY the backend enum — never widen this. */
const RATE_BASES = ["base_per_payment", "payment_per_base"] as const;
const BOOKING_SOURCES = ["direct", "phone", "walk_in", "other"] as const;
/** The backend `ExpectedPaymentMethod` choices (informational, future
 * reservations) — NOT the deposit methods. Kept in sync with the backend enum so
 * the selector never offers a value the create body would drop. */
const EXPECTED_METHODS = ["cash", "card", "bank_transfer", "other"] as const;

/** Half-open interval [check_in, check_out): the number of nights billed. */
function nightsBetween(checkIn: string, checkOut: string): number {
  if (!checkIn || !checkOut) return 0;
  const start = new Date(`${checkIn}T00:00:00`).getTime();
  const end = new Date(`${checkOut}T00:00:00`).getTime();
  const diff = Math.round((end - start) / 86_400_000);
  return diff > 0 ? diff : 0;
}

/**
 * Step 4 — Booking. Dates + times with auto nights, a floor→room availability
 * picker (backend-authoritative availability + pricing), the immediate atomic
 * check-in toggle, and an HONEST payment section: informational-only before
 * check-in, a real deposit (with optional multi-currency FX) when checking in
 * now. Everything writes `draft.booking` via the existing actions; the wizard's
 * submit maps it through the body builders.
 */
export function BookingStep({
  draft,
  actions,
}: {
  draft: ReservationDraft;
  actions: ReservationDraftActions;
}) {
  const { t, locale } = useI18n();
  const w = t.reservations.wizard;
  const b = w.booking;
  const me = useCurrentUser();
  const access = useHotelAccess();
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));

  const booking = draft.booking;
  const checkInDate = booking.check_in_date;
  const checkOutDate = booking.check_out_date;
  const [settings, setSettings] = useState<HotelSettings | null>(null);
  const [rooms, setRooms] = useState<RoomAvailabilityRow[]>([]);
  const [roomsLoading, setRoomsLoading] = useState(false);
  const [roomsError, setRoomsError] = useState(false);
  const [floorFilter, setFloorFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  // Hotel settings (payment currencies + checkout time) once per mount.
  useEffect(() => {
    let cancelled = false;
    getSettings()
      .then((data) => {
        if (!cancelled) setSettings(data);
      })
      .catch(() => {
        if (!cancelled) setSettings(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Default the arrival date to the hotel business date (client clocks differ);
  // only seeds an empty field so it never fights a user edit.
  useEffect(() => {
    if (booking.check_in_date) return;
    let cancelled = false;
    getReservationOverview()
      .then((overview) => {
        if (!cancelled && !draft.booking.check_in_date) {
          actions.patchBooking({ check_in_date: overview.business_date });
        }
      })
      .catch(() => {
        /* The picker still works; the user selects a date manually. */
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Live per-room availability for the chosen period — backend-authoritative.
  useEffect(() => {
    if (!checkInDate || !checkOutDate || checkOutDate <= checkInDate) {
      setRooms([]);
      setRoomsError(false);
      return;
    }
    let cancelled = false;
    setRoomsLoading(true);
    setRoomsError(false);
    getRoomAvailability({ check_in: checkInDate, check_out: checkOutDate })
      .then((rows) => {
        if (!cancelled) setRooms(rows);
      })
      .catch(() => {
        if (!cancelled) {
          setRooms([]);
          setRoomsError(true);
        }
      })
      .finally(() => {
        if (!cancelled) setRoomsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [checkInDate, checkOutDate]);

  const nights = nightsBetween(checkInDate, checkOutDate);
  const baseCurrency = settings?.default_currency || "";
  const checkoutTime = settings?.check_out_time ?? null;
  const canImmediate = can("stays.check_in") && can("reservations.create");

  const staffName = me?.full_name || me?.email || "—";
  const expectedDeparture =
    booking.check_out_date
      ? `${formatDate(booking.check_out_date, locale)}${checkoutTime ? ` · ${checkoutTime.slice(0, 5)}` : ""}`
      : "—";

  // Floor + type filter option sets are derived from the returned rows (no
  // extra fetch); the endpoint's availability is what drives the list.
  const floorOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const row of rooms) {
      const key = row.floor_number ?? "";
      if (!seen.has(key)) {
        seen.set(
          key,
          row.floor_name ||
            (row.floor_number ? b.floorGroup.replace("{floor}", row.floor_number) : b.noFloor),
        );
      }
    }
    return Array.from(seen, ([value, label]) => ({ value, label }));
  }, [rooms, b]);

  const typeOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const row of rooms) {
      const key = String(row.room_type_id);
      if (!seen.has(key)) seen.set(key, row.room_type_name);
    }
    return Array.from(seen, ([value, label]) => ({ value, label }));
  }, [rooms]);

  const filteredRooms = rooms.filter(
    (row) =>
      (!floorFilter || (row.floor_number ?? "") === floorFilter) &&
      (!typeFilter || String(row.room_type_id) === typeFilter),
  );

  // Group the visible rooms by floor for the picker.
  const floorGroups = useMemo(() => {
    const groups = new Map<string, { label: string; rows: RoomAvailabilityRow[] }>();
    for (const row of filteredRooms) {
      const key = row.floor_number ?? "__none__";
      const label =
        row.floor_name ||
        (row.floor_number ? b.floorGroup.replace("{floor}", row.floor_number) : b.noFloor);
      const group = groups.get(key);
      if (group) group.rows.push(row);
      else groups.set(key, { label, rows: [row] });
    }
    return Array.from(groups.values());
  }, [filteredRooms, b]);

  const selectedRoom = rooms.find((row) => row.id === booking.selected_room_id) ?? null;

  // Client-side capacity hint: the backend stays authoritative and re-validates,
  // but warn early (localized) when the drafted party exceeds the chosen room's
  // max capacity so staff aren't surprised by a raw server error at submit.
  const partySize = totalPersons(draft);
  const overCapacity =
    selectedRoom !== null && partySize > selectedRoom.max_capacity;

  function selectRoom(row: RoomAvailabilityRow) {
    actions.patchBooking({
      selected_room_id: row.id,
      lines: [{ room_type: String(row.room_type_id), room: String(row.id), quantity: "1" }],
    });
  }

  const datesReady = Boolean(
    booking.check_in_date && booking.check_out_date && booking.check_out_date > booking.check_in_date,
  );

  return (
    <div className="stack">
      {/* Staff + reservation number — both backend-owned, shown read-only. */}
      <SectionCard title={b.title} icon={CalendarClock} description={b.description}>
        <div className="form-grid">
          <FormField label={b.staff} htmlFor="wiz-book-staff">
            <Input id="wiz-book-staff" value={staffName} disabled readOnly />
          </FormField>
          <FormField
            label={b.reservationNumber}
            htmlFor="wiz-book-number"
            hint={b.autoAssignedHint}
          >
            <Input id="wiz-book-number" value={b.autoAssigned} disabled readOnly />
          </FormField>
        </div>

        <div className="form-grid">
          <FormField label={b.checkIn} htmlFor="wiz-book-in">
            <Input
              id="wiz-book-in"
              type="date"
              value={booking.check_in_date}
              onChange={(e) => actions.patchBooking({ check_in_date: e.target.value })}
            />
          </FormField>
          <FormField label={b.checkOut} htmlFor="wiz-book-out">
            <Input
              id="wiz-book-out"
              type="date"
              value={booking.check_out_date}
              min={booking.check_in_date || undefined}
              onChange={(e) => actions.patchBooking({ check_out_date: e.target.value })}
            />
          </FormField>
          <FormField label={b.arrivalTime} htmlFor="wiz-book-arrival">
            <Input
              id="wiz-book-arrival"
              type="time"
              value={booking.expected_arrival_time}
              onChange={(e) => actions.patchBooking({ expected_arrival_time: e.target.value })}
            />
          </FormField>
          <FormField label={b.nights} htmlFor="wiz-book-nights">
            <Input id="wiz-book-nights" value={String(nights)} disabled readOnly />
          </FormField>
          <FormField label={b.expectedDeparture} htmlFor="wiz-book-departure">
            <Input id="wiz-book-departure" value={expectedDeparture} disabled readOnly />
          </FormField>
          <FormField label={b.source} htmlFor="wiz-book-source">
            <Select
              id="wiz-book-source"
              value={booking.source}
              options={BOOKING_SOURCES.map((value) => ({
                value,
                label: t.reservations.source[value],
              }))}
              onChange={(e) =>
                actions.patchBooking({ source: e.target.value as ReservationDraft["booking"]["source"] })
              }
            />
          </FormField>
        </div>
      </SectionCard>

      {/* Floor → room availability picker. */}
      <SectionCard title={b.roomSection} icon={BedDouble} description={b.roomHint}>
        {!datesReady ? (
          <Alert tone="info">{b.pickDatesFirst}</Alert>
        ) : (
          <>
            <div className="form-grid">
              <FormField label={b.filterFloor} htmlFor="wiz-book-floor">
                <Select
                  id="wiz-book-floor"
                  value={floorFilter}
                  placeholder={b.allFloors}
                  options={floorOptions}
                  onChange={(e) => setFloorFilter(e.target.value)}
                />
              </FormField>
              <FormField label={b.filterType} htmlFor="wiz-book-type">
                <Select
                  id="wiz-book-type"
                  value={typeFilter}
                  placeholder={b.allTypes}
                  options={typeOptions}
                  onChange={(e) => setTypeFilter(e.target.value)}
                />
              </FormField>
            </div>

            {roomsLoading ? <p className="muted small">{b.loadingRooms}</p> : null}
            {!roomsLoading && roomsError ? (
              <Alert tone="warning">{b.roomsError}</Alert>
            ) : null}
            {!roomsLoading && !roomsError && floorGroups.length === 0 ? (
              <p className="muted small">{b.noRooms}</p>
            ) : null}

            {floorGroups.map((group) => (
              <div className="stack-tight" key={group.label} aria-label={group.label}>
                <p className="field__label">{group.label}</p>
                {group.rows.map((row) => {
                  const selected = row.id === booking.selected_room_id;
                  return (
                    <div className="stack-tight" key={row.id}>
                      <div className="line-row">
                        <span className="cluster">
                          <strong>{row.number}</strong>
                          <span className="muted small">{row.room_type_name}</span>
                          <span className="muted small">
                            {formatCapacity(row.base_capacity, row.max_capacity, t, locale)}
                          </span>
                          <span className="muted small">
                            {row.base_rate
                              ? formatMoney(row.base_rate, row.currency, locale)
                              : "—"}
                          </span>
                          {selected ? (
                            <Badge tone="success">{b.selected}</Badge>
                          ) : !row.available ? (
                            <Badge tone="neutral">{b.unavailable}</Badge>
                          ) : null}
                        </span>
                        <Button
                          type="button"
                          variant={selected ? "primary" : "secondary"}
                          size="sm"
                          disabled={!row.available}
                          onClick={() => selectRoom(row)}
                        >
                          {selected ? b.selected : b.select}
                        </Button>
                      </div>
                      {row.amenities.length > 0 ? (
                        <AmenityChips amenities={row.amenities} max={6} />
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ))}

            {overCapacity && selectedRoom ? (
              <Alert tone="warning">
                {b.capacityWarning
                  .replace("{max}", String(selectedRoom.max_capacity))
                  .replace("{total}", String(partySize))}
              </Alert>
            ) : null}
          </>
        )}
      </SectionCard>

      {/* Immediate check-in — gated by both permissions. */}
      {canImmediate ? (
        <SectionCard title={b.immediateSection} icon={LogIn}>
          <Switch
            id="wiz-book-immediate"
            checked={booking.immediate_check_in}
            onChange={(value) => actions.patchBooking({ immediate_check_in: value })}
            label={b.immediateToggle}
          />
          <p className="muted small">{b.immediateHint}</p>
        </SectionCard>
      ) : null}

      {/* Payment — honest to the backend money model. */}
      <PaymentSection
        draft={draft}
        actions={actions}
        baseCurrency={baseCurrency}
        acceptedCurrencies={settings?.accepted_currencies ?? []}
        nights={nights}
        selectedRoom={selectedRoom}
        canOverrideRate={can("exchange_rate.override")}
      />
    </div>
  );
}

/** The payment sub-form. Split out to keep the booking body readable; it reads
 * and writes `draft.booking.payment` only through `actions.patchPayment`. */
function PaymentSection({
  draft,
  actions,
  baseCurrency,
  acceptedCurrencies,
  nights,
  selectedRoom,
  canOverrideRate,
}: {
  draft: ReservationDraft;
  actions: ReservationDraftActions;
  baseCurrency: string;
  acceptedCurrencies: string[];
  nights: number;
  selectedRoom: RoomAvailabilityRow | null;
  canOverrideRate: boolean;
}) {
  const { t, locale } = useI18n();
  const b = t.reservations.wizard.booking;
  const payment = draft.booking.payment;
  const immediate = draft.booking.immediate_check_in;

  const methodValue: UiPayMethod =
    payment.method === "cash"
      ? "cash"
      : payment.method === "internal_electronic"
        ? "internal_electronic"
        : "on_room_account";

  const methodOptions = (["cash", "internal_electronic", "on_room_account"] as UiPayMethod[]).map(
    (value) => ({ value, label: b.method[value] }),
  );

  function setMethod(value: UiPayMethod) {
    if (value === "on_room_account") {
      // No deposit is recorded — clear every money field.
      actions.patchPayment({
        method: "",
        amount: "",
        original_amount: "",
        exchange_rate: "",
        rate_basis: "",
      });
    } else {
      actions.patchPayment({ method: value });
    }
  }

  // Payment-currency options: default currency is always implicitly accepted.
  const currencyOptions = useMemo(() => {
    const set = new Set<string>();
    if (baseCurrency) set.add(baseCurrency);
    for (const code of acceptedCurrencies) if (code) set.add(code);
    return Array.from(set, (value) => ({ value, label: value }));
  }, [baseCurrency, acceptedCurrencies]);

  const payCurrency = payment.currency || baseCurrency;
  const isForeign = Boolean(baseCurrency) && payCurrency !== baseCurrency;
  const takesDeposit = methodValue === "cash" || methodValue === "internal_electronic";

  function setCurrency(next: string) {
    if (next === baseCurrency) {
      actions.patchPayment({
        currency: next,
        original_amount: "",
        exchange_rate: "",
        rate_basis: "",
      });
    } else {
      actions.patchPayment({ currency: next, amount: "" });
    }
  }

  // DISPLAY-ONLY equivalents. Backend derives the ledger amount authoritatively;
  // these never leave the client and never invent pricing (the estimate uses the
  // backend room `base_rate`).
  const original = Number(payment.original_amount);
  const rate = Number(payment.exchange_rate);
  let baseEquivalent = 0;
  if (isForeign && original > 0 && rate > 0) {
    baseEquivalent =
      payment.rate_basis === "payment_per_base" ? original / rate : original * rate;
  }
  // Indicative subtotal only (nights × room rate). Deliberately NOT a "remaining"
  // figure: it ignores tax, quantity and any prior postings, so presenting a
  // balance here would mislead staff — the folio balance is the authority.
  const estimatedTotal =
    selectedRoom && selectedRoom.base_rate ? nights * Number(selectedRoom.base_rate) : null;

  return (
    <SectionCard title={b.paymentSection} icon={CreditCard}>
      {!immediate ? (
        /* No folio exists before check-in — this is an informational note that
         * IS persisted (`expected_payment_method`). It is constrained to the
         * backend enum, distinct from the deposit method, so the choice is never
         * silently dropped. */
        <FormField
          label={b.expectedMethodLabel}
          htmlFor="wiz-pay-expected"
          hint={b.expectedMethodHint}
        >
          <Select
            id="wiz-pay-expected"
            value={draft.booking.expected_payment_method}
            placeholder={b.expectedMethodPlaceholder}
            options={EXPECTED_METHODS.map((value) => ({
              value,
              label: t.reservations.expectedPayment[value],
            }))}
            onChange={(e) =>
              actions.patchBooking({
                expected_payment_method: e.target.value as ExpectedPaymentMethod,
              })
            }
          />
        </FormField>
      ) : (
        <>
          <FormField label={b.depositMethodLabel} htmlFor="wiz-pay-method">
            <Select
              id="wiz-pay-method"
              value={methodValue}
              options={methodOptions}
              onChange={(e) => setMethod(e.target.value as UiPayMethod)}
            />
          </FormField>

          {methodValue === "on_room_account" ? (
            <Alert tone="info">{b.onRoomAccountHint}</Alert>
          ) : null}

          {takesDeposit ? (
            <>
              {currencyOptions.length > 1 ? (
                <FormField label={b.paymentCurrency} htmlFor="wiz-pay-currency">
                  <Select
                    id="wiz-pay-currency"
                    value={payCurrency}
                    options={currencyOptions}
                    onChange={(e) => setCurrency(e.target.value)}
                  />
                </FormField>
              ) : null}

              {!isForeign ? (
                <FormField
                  label={b.amount.replace("{currency}", baseCurrency || payCurrency)}
                  htmlFor="wiz-pay-amount"
                >
                  <Input
                    id="wiz-pay-amount"
                    inputMode="decimal"
                    value={payment.amount}
                    onChange={(e) => actions.patchPayment({ amount: e.target.value })}
                  />
                </FormField>
              ) : (
                <>
                  <div className="form-grid">
                    <FormField
                      label={b.originalAmount.replace("{currency}", payCurrency)}
                      htmlFor="wiz-pay-original"
                    >
                      <Input
                        id="wiz-pay-original"
                        inputMode="decimal"
                        value={payment.original_amount}
                        onChange={(e) =>
                          actions.patchPayment({ original_amount: e.target.value })
                        }
                      />
                    </FormField>
                    <FormField
                      label={b.exchangeRate}
                      htmlFor="wiz-pay-rate"
                      hint={!canOverrideRate ? b.fxPermissionHint : undefined}
                    >
                      <Input
                        id="wiz-pay-rate"
                        inputMode="decimal"
                        value={payment.exchange_rate}
                        disabled={!canOverrideRate}
                        onChange={(e) => actions.patchPayment({ exchange_rate: e.target.value })}
                      />
                    </FormField>
                    <FormField label={b.rateBasis} htmlFor="wiz-pay-basis">
                      <Select
                        id="wiz-pay-basis"
                        value={payment.rate_basis}
                        placeholder={b.rateBasisPlaceholder}
                        disabled={!canOverrideRate}
                        options={RATE_BASES.map((value) => ({
                          value,
                          label: b.rateBasisOptions[value],
                        }))}
                        onChange={(e) => actions.patchPayment({ rate_basis: e.target.value })}
                      />
                    </FormField>
                  </div>
                  {baseEquivalent > 0 ? (
                    <p className="muted small">
                      {b.baseEquivalent}:{" "}
                      <strong>{formatMoney(baseEquivalent, baseCurrency, locale)}</strong>
                    </p>
                  ) : null}
                </>
              )}

              {estimatedTotal !== null ? (
                <Alert tone="info">
                  <span className="stack-tight">
                    <span>
                      {b.estimatedTotal}:{" "}
                      <strong>{formatMoney(estimatedTotal, baseCurrency, locale)}</strong>
                    </span>
                    <span className="muted small">{b.estimateNote}</span>
                  </span>
                </Alert>
              ) : null}
            </>
          ) : null}
        </>
      )}
    </SectionCard>
  );
}
