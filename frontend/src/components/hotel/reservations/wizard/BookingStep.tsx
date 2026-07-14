"use client";

import { useEffect, useMemo, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  BedDouble,
  CalendarClock,
  ClipboardList,
  CreditCard,
  Layers,
  LogIn,
  StickyNote,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  FormField,
  Icon,
  Input,
  PaymentStatusBadge,
  Select,
  Switch,
  Textarea,
} from "@/components/ui";
import { getSettings } from "@/lib/api/hotel";
import { listFloors } from "@/lib/api/rooms";
import { getRoomAvailability, getReservationOverview } from "@/lib/api/reservations";
import type {
  Floor,
  HotelSettings,
  ReservationFinancialSummary,
  RoomAvailabilityRow,
} from "@/lib/api/types";
import { cx } from "@/lib/utils";
import { formatCapacity, formatDate, formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { useCurrentUser } from "@/lib/session/CurrentUserContext";

import { totalPersons } from "./useReservationDraft";
import type { ReservationDraftActions, ReservationDraft } from "./useReservationDraft";

/** EXACTLY the backend enum — never widen this. */
const RATE_BASES = ["base_per_payment", "payment_per_base"] as const;
const BOOKING_SOURCES = ["direct", "phone", "walk_in", "other"] as const;

/* -------------------------------------------------------------------------- */
/* Decimal helpers — money is NEVER computed with IEEE Float (§26). All        */
/* arithmetic runs on BigInt-scaled integers; the results are 2-dp decimal     */
/* STRINGS handed to `formatMoney` for display only (the backend is the        */
/* authority for the true total / remaining once the reservation is saved).    */
/* -------------------------------------------------------------------------- */

interface ParsedDecimal {
  neg: boolean;
  value: bigint;
  scale: number;
}

function parseDecimal(input: string | null | undefined): ParsedDecimal | null {
  if (input == null) return null;
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(input.trim());
  if (!match) return null;
  const frac = match[3] ?? "";
  return {
    neg: match[1] === "-",
    value: BigInt(match[2] + frac),
    scale: frac.length,
  };
}

/** Render a signed BigInt at `10^scale` as a fixed 2-dp decimal string, rounding
 * half-up when the input carries more than two fractional digits. */
function formatScaled(signed: bigint, scale: number): string {
  const neg = signed < 0n;
  let v = neg ? -signed : signed;
  if (scale > 2) {
    const divisor = 10n ** BigInt(scale - 2);
    const remainder = v % divisor;
    v = v / divisor;
    if (remainder * 2n >= divisor) v += 1n;
  } else if (scale < 2) {
    v = v * 10n ** BigInt(2 - scale);
  }
  const cents = (v % 100n).toString().padStart(2, "0");
  return `${neg ? "-" : ""}${(v / 100n).toString()}.${cents}`;
}

/** Exact `decimal × non-negative integer` (nights × nightly rate). */
function mulDecimalByInt(decimal: string | null, count: number): string | null {
  const d = parseDecimal(decimal);
  if (!d || !Number.isInteger(count) || count < 0) return null;
  const value = d.value * BigInt(count);
  return formatScaled(d.neg ? -value : value, d.scale);
}

/** `decimal × decimal`, rounded to 2 dp (FX equivalent, base_per_payment). */
function mulDecimal2(a: string, b: string): string | null {
  const x = parseDecimal(a);
  const y = parseDecimal(b);
  if (!x || !y) return null;
  const value = x.value * y.value;
  const signed = x.neg !== y.neg ? -value : value;
  return formatScaled(signed, x.scale + y.scale);
}

/** `decimal ÷ decimal`, rounded to 2 dp (FX equivalent, payment_per_base). */
function divDecimal2(a: string, b: string): string | null {
  const x = parseDecimal(a);
  const y = parseDecimal(b);
  if (!x || !y || y.value === 0n) return null;
  // result = (x.value / 10^x.scale) / (y.value / 10^y.scale). Scale to 3 dp for a
  // rounding guard digit, then round half-up down to 2 dp.
  const num = x.value * 10n ** BigInt(y.scale) * 1000n;
  const den = y.value * 10n ** BigInt(x.scale);
  let q = num / den;
  const guard = q % 10n;
  q = q / 10n;
  if (guard >= 5n) q += 1n;
  const signed = x.neg !== y.neg ? -q : q;
  return formatScaled(signed, 2);
}

/** Exact `a − b` for money strings. */
function subDecimal(a: string, b: string): string | null {
  const x = parseDecimal(a);
  const y = parseDecimal(b);
  if (!x || !y) return null;
  const scale = Math.max(x.scale, y.scale);
  const xv = (x.neg ? -x.value : x.value) * 10n ** BigInt(scale - x.scale);
  const yv = (y.neg ? -y.value : y.value) * 10n ** BigInt(scale - y.scale);
  return formatScaled(xv - yv, scale);
}

/** The base-currency equivalent of a foreign tender, per the chosen direction.
 * Canonical (base_per_payment): base = original × rate. payment_per_base: base =
 * original ÷ rate. DISPLAY-only — the backend snapshots the authoritative rate. */
function fxBaseEquivalent(
  original: string,
  rate: string,
  basis: string,
): string | null {
  if (!original.trim() || !rate.trim()) return null;
  return basis === "payment_per_base"
    ? divDecimal2(original, rate)
    : mulDecimal2(original, rate);
}

/** Half-open interval [check_in, check_out): the number of nights billed. */
function nightsBetween(checkIn: string, checkOut: string): number {
  if (!checkIn || !checkOut) return 0;
  const start = new Date(`${checkIn}T00:00:00`).getTime();
  const end = new Date(`${checkOut}T00:00:00`).getTime();
  const diff = Math.round((end - start) / 86_400_000);
  return diff > 0 ? diff : 0;
}

/** A small group heading — icon + uppercase label + hairline divider (from CSS).
 * Replaces the old boxed `SectionCard` heads for the Compact Premium layout. */
function GroupHeading({ icon, children }: { icon: LucideIcon; children: string }) {
  return (
    <h4 className="resform-book__heading">
      <Icon icon={icon} size="sm" />
      {children}
    </h4>
  );
}

/** EDIT context (§25/§33). When present the step is an EDIT of a saved
 * reservation: `reservationNumber` is the real saved number shown read-only,
 * `stayLocked` freezes the dates + room (a started stay is changed only through
 * the stay service), `allowNewDeposit` shows the new-deposit entry (a stayless
 * reservation + `finance.payment_create`), `financialSummary` is the read-only
 * record of payments already taken, and `lockedRoomLabel` names the frozen room.
 * Undefined for CREATE — the number shows a "generated on save" state instead. */
export interface BookingEditContext {
  reservationNumber: string;
  stayLocked: boolean;
  allowNewDeposit: boolean;
  financialSummary: ReservationFinancialSummary | null;
  lockedRoomLabel: string;
}

/**
 * Step 4 — Booking (§19–§32), Compact Premium layout. Dense grouped fields
 * (small heading + hairline divider + multi-column grid) instead of stacked
 * boxes: reservation info, dates & times, floor → room, immediate check-in,
 * price & real payment (with multi-currency FX), and notes. There is NO separate
 * pre-save review — Save is the final action; a compact live totals strip sits
 * inside the price group. Availability and pricing stay backend-authoritative
 * (this UI never decides bookability); money is displayed from backend Decimal
 * strings / exact estimates, never IEEE Float. In EDIT mode (`editContext`) the
 * number shows the real saved value, dates/room lock per stay status, the
 * immediate-check-in toggle is hidden, and a read-only record of existing
 * payments is shown above any new-deposit entry.
 */
export function BookingStep({
  draft,
  actions,
  editContext,
}: {
  draft: ReservationDraft;
  actions: ReservationDraftActions;
  editContext?: BookingEditContext | null;
}) {
  const { t, locale } = useI18n();
  const w = t.reservations.wizard;
  const b = w.booking;
  const me = useCurrentUser();
  const access = useHotelAccess();
  const can = (...codes: string[]) =>
    access === null || (!access.loading && access.can(...codes));

  const booking = draft.booking;
  // RESERVATIONS-AUTO-ROOM §2 — automatic is the default; the staff never pin a
  // room in this mode (the room list + "Select" are hidden below).
  const automatic = booking.room_assignment_mode === "automatic";
  const isEdit = Boolean(editContext);
  const stayLocked = editContext?.stayLocked ?? false;
  const checkInDate = booking.check_in_date;
  const checkOutDate = booking.check_out_date;
  const [settings, setSettings] = useState<HotelSettings | null>(null);
  const [floors, setFloors] = useState<Floor[]>([]);
  const [rooms, setRooms] = useState<RoomAvailabilityRow[]>([]);
  const [roomsLoading, setRoomsLoading] = useState(false);
  const [roomsError, setRoomsError] = useState(false);
  const [typeFilter, setTypeFilter] = useState("");
  const [businessDate, setBusinessDate] = useState("");
  const [selectedRoomRow, setSelectedRoomRow] = useState<RoomAvailabilityRow | null>(
    null,
  );

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

  // Floors for the SEPARATE floor picker (§23) — active floors only.
  useEffect(() => {
    let cancelled = false;
    listFloors()
      .then((data) => {
        if (!cancelled) setFloors(data.results.filter((floor) => floor.is_active));
      })
      .catch(() => {
        if (!cancelled) setFloors([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Default the arrival date to the hotel business date (client clocks differ);
  // only seeds an empty field so it never fights a user edit. Also caches the
  // business date for the immediate-check-in "today" hint (§24).
  useEffect(() => {
    let cancelled = false;
    getReservationOverview()
      .then((overview) => {
        if (cancelled) return;
        setBusinessDate(overview.business_date);
        if (!draft.booking.check_in_date) {
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

  const selectedFloorId = booking.selected_floor_id;
  const datesReady = Boolean(
    checkInDate && checkOutDate && checkOutDate > checkInDate,
  );

  // Available rooms for the SELECTED floor + period — backend-authoritative. Only
  // AVAILABLE rooms are kept (unavailable rooms are HIDDEN, never shown disabled).
  useEffect(() => {
    if (!datesReady || selectedFloorId == null) {
      setRooms([]);
      setRoomsError(false);
      return;
    }
    let cancelled = false;
    setRoomsLoading(true);
    setRoomsError(false);
    getRoomAvailability({
      check_in: checkInDate,
      check_out: checkOutDate,
      floor: selectedFloorId,
    })
      .then((rows) => {
        if (!cancelled) setRooms(rows.filter((row) => row.available));
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
  }, [checkInDate, checkOutDate, selectedFloorId, datesReady]);

  const nights = nightsBetween(checkInDate, checkOutDate);
  const baseCurrency = settings?.default_currency || "";
  const checkoutTime = settings?.check_out_time ?? null;
  const canImmediate = can("stays.check_in") && can("reservations.create");

  const staffName = me?.full_name || me?.email || "—";
  const staffRole = access?.isManager ? b.roleManager : b.roleStaff;
  const reservationNumberDisplay = isEdit
    ? editContext?.reservationNumber || "—"
    : b.numberOnSave;
  const checkoutTimeDisplay = checkoutTime ? checkoutTime.slice(0, 5) : "—";

  // Room-type filter options derived from the AVAILABLE rooms on the chosen floor.
  const typeOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const row of rooms) {
      const key = String(row.room_type_id);
      if (!seen.has(key)) seen.set(key, row.room_type_name);
    }
    return Array.from(seen, ([value, label]) => ({ value, label }));
  }, [rooms]);

  const visibleRooms = rooms.filter(
    (row) => !typeFilter || String(row.room_type_id) === typeFilter,
  );

  // RESERVATIONS-AUTO-ROOM — in AUTOMATIC mode the room-TYPE on the single line
  // is the assignment CRITERIA (not a display filter): the backend picks a room
  // of that type on the chosen floor. `autoMatchCount` is display-only
  // reassurance — how many available rooms match — never a specific room number.
  const lineType = booking.lines[0]?.room_type ?? "";
  const autoMatchCount =
    automatic && lineType
      ? rooms.filter((row) => String(row.room_type_id) === lineType).length
      : 0;

  // AUTOMATIC still needs a room-TYPE criteria on the line (the backend drops any
  // pinned room but requires the type). Default/repair it to a type available on
  // the chosen floor whenever the current value is empty or stale for that floor,
  // so an automatic booking is always valid WITHOUT a misleading room pick. Never
  // runs in manual mode and never overrides a type the floor still offers.
  useEffect(() => {
    if (!automatic || selectedFloorId == null) return;
    if (typeOptions.length === 0) return;
    if (typeOptions.some((option) => option.value === lineType)) return;
    const first = booking.lines[0] ?? { room_type: "", room: "", quantity: "1" };
    actions.patchBooking({
      lines: [
        { ...first, room_type: typeOptions[0].value, room: "", quantity: "1" },
      ],
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [automatic, selectedFloorId, typeOptions, lineType]);

  // Keep the selected room's data stable even while the staff browse another
  // floor (the availability list only holds the current floor's rooms).
  const selectedRoom =
    selectedRoomRow && selectedRoomRow.id === booking.selected_room_id
      ? selectedRoomRow
      : rooms.find((row) => row.id === booking.selected_room_id) ?? null;

  const partySize = totalPersons(draft);
  const overCapacity =
    selectedRoom !== null && partySize > selectedRoom.max_capacity;

  function selectFloor(floorId: number) {
    actions.patchBooking({ selected_floor_id: floorId });
    setTypeFilter("");
  }

  function selectRoom(row: RoomAvailabilityRow) {
    setSelectedRoomRow(row);
    actions.patchBooking({
      selected_room_id: row.id,
      lines: [
        { room_type: String(row.room_type_id), room: String(row.id), quantity: "1" },
      ],
    });
  }

  // AUTOMATIC — the room-TYPE selector sets the assignment CRITERIA on the line
  // (no specific room is ever pinned in this mode).
  function selectAutoType(value: string) {
    const first = booking.lines[0] ?? { room_type: "", room: "", quantity: "1" };
    actions.patchBooking({
      selected_room_id: null,
      lines: [{ ...first, room_type: value, room: "", quantity: "1" }],
    });
  }

  function toggleImmediate(value: boolean) {
    // §24 — an immediate check-in uses today's date. Seed the arrival date to the
    // hotel business date when turning it on (the backend clock is authoritative).
    if (value && businessDate && booking.check_in_date !== businessDate) {
      actions.patchBooking({ immediate_check_in: value, check_in_date: businessDate });
    } else {
      actions.patchBooking({ immediate_check_in: value });
    }
  }

  const immediate = booking.immediate_check_in;
  const immediateDateMismatch =
    immediate && Boolean(businessDate) && booking.check_in_date !== businessDate;

  // Estimated stay total + remaining (exact decimal, no Float). Backend derives
  // the authoritative figures on save; these are honest client-side estimates.
  // In AUTOMATIC mode no specific room is pinned, but every room of the chosen
  // type shares the same base_rate — so the nightly price / total still show (§26).
  const nightlyRate =
    selectedRoom?.base_rate ??
    (automatic && lineType
      ? rooms.find((row) => String(row.room_type_id) === lineType)?.base_rate ??
        null
      : null);
  const estimatedTotal =
    nightlyRate && nights > 0 ? mulDecimalByInt(nightlyRate, nights) : null;

  const payment = booking.payment;
  const payCurrency = payment.currency || baseCurrency;
  const isForeign = Boolean(baseCurrency) && payCurrency !== baseCurrency;
  const takesDeposit =
    payment.method === "cash" || payment.method === "internal_electronic";
  const baseEquivalent = isForeign
    ? fxBaseEquivalent(payment.original_amount, payment.exchange_rate, payment.rate_basis)
    : null;
  let paidBase = "0.00";
  if (takesDeposit) {
    if (!isForeign) {
      paidBase =
        payment.amount.trim() && Number(payment.amount) > 0
          ? payment.amount.trim()
          : "0.00";
    } else {
      paidBase = baseEquivalent ?? "0.00";
    }
  }
  const estimatedRemaining = estimatedTotal
    ? subDecimal(estimatedTotal, paidBase)
    : null;

  return (
    <div className="resform-book">
      {/* (1) Reservation information — number + staff + source, backend-owned. */}
      <section className="resform-book__group">
        <GroupHeading icon={ClipboardList}>{b.infoSection}</GroupHeading>
        <div className="resform-book__grid">
          <FormField
            label={b.reservationNumber}
            htmlFor="wiz-book-number"
            hint={isEdit ? undefined : b.autoAssignedHint}
          >
            <Input
              id="wiz-book-number"
              type="text"
              value={reservationNumberDisplay}
              readOnly
            />
          </FormField>
          <FormField label={b.staff} htmlFor="wiz-book-staff" hint={staffRole}>
            <Input id="wiz-book-staff" type="text" value={staffName} readOnly />
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
                actions.patchBooking({
                  source: e.target.value as ReservationDraft["booking"]["source"],
                })
              }
            />
          </FormField>
        </div>
      </section>

      {/* (2) Dates & times — auto nights + persons, checkout time from settings. */}
      <section className="resform-book__group">
        <GroupHeading icon={CalendarClock}>{b.datesSection}</GroupHeading>
        {stayLocked ? <Alert tone="info">{b.stayLockedDates}</Alert> : null}
        <div className="resform-book__grid">
          <FormField label={b.checkIn} htmlFor="wiz-book-in">
            <Input
              id="wiz-book-in"
              type="date"
              value={booking.check_in_date}
              disabled={stayLocked}
              onChange={(e) => actions.patchBooking({ check_in_date: e.target.value })}
            />
          </FormField>
          {!immediate ? (
            <FormField label={b.arrivalTime} htmlFor="wiz-book-arrival">
              <Input
                id="wiz-book-arrival"
                type="time"
                value={booking.expected_arrival_time}
                disabled={stayLocked}
                onChange={(e) =>
                  actions.patchBooking({ expected_arrival_time: e.target.value })
                }
              />
            </FormField>
          ) : null}
          <FormField label={b.checkOut} htmlFor="wiz-book-out">
            <Input
              id="wiz-book-out"
              type="date"
              value={booking.check_out_date}
              min={booking.check_in_date || undefined}
              disabled={stayLocked}
              onChange={(e) => actions.patchBooking({ check_out_date: e.target.value })}
            />
          </FormField>
          <FormField label={b.checkoutTime} htmlFor="wiz-book-checkout-time">
            <Input
              id="wiz-book-checkout-time"
              type="text"
              value={checkoutTimeDisplay}
              readOnly
            />
          </FormField>
          <FormField label={b.nights} htmlFor="wiz-book-nights">
            <Input id="wiz-book-nights" type="text" value={String(nights)} readOnly />
          </FormField>
          <FormField label={b.persons} htmlFor="wiz-book-persons">
            <Input
              id="wiz-book-persons"
              type="text"
              value={String(partySize)}
              readOnly
            />
          </FormField>
        </div>
      </section>

      {/* (3) Floor → room. Separate floor picker FIRST, then available rooms.
          When a stay has started the room is frozen (§33) — show it read-only. */}
      <section className="resform-book__group">
        <GroupHeading icon={BedDouble}>{b.roomSection}</GroupHeading>
        {stayLocked ? (
          <>
            <Alert tone="info">{b.stayLockedDates}</Alert>
            <div className="resform-book__grid">
              <FormField label={b.roomSection} htmlFor="wiz-book-locked-room">
                <Input
                  id="wiz-book-locked-room"
                  type="text"
                  value={editContext?.lockedRoomLabel || "—"}
                  readOnly
                />
              </FormField>
            </div>
          </>
        ) : (
          <>
            {/* AUTOMATIC (default) vs MANUAL. In automatic the individual room
                list + "Select" are hidden so no misleading pick is possible; the
                backend assigns an available room from the floor/type criteria. */}
            <Switch
              id="wiz-book-auto-room"
              checked={automatic}
              onChange={(value) =>
                actions.setRoomMode(value ? "automatic" : "manual")
              }
              label={b.autoRoomToggle}
            />

            {!datesReady ? (
              <Alert tone="info">{b.pickDatesFirst}</Alert>
            ) : (
              <>
                <FormField label={b.filterFloor}>
                  {floors.length === 0 ? (
                    <p className="muted small">{b.noFloors}</p>
                  ) : (
                    <div className="cluster">
                      {floors.map((floor) => (
                        <Button
                          key={floor.id}
                          type="button"
                          variant={
                            selectedFloorId === floor.id ? "primary" : "secondary"
                          }
                          size="sm"
                          icon={Layers}
                          onClick={() => selectFloor(floor.id)}
                        >
                          {floor.name ||
                            b.floorGroup.replace("{floor}", floor.number)}
                        </Button>
                      ))}
                    </div>
                  )}
                </FormField>

                {selectedFloorId == null ? (
                  <Alert tone="info">{b.selectFloorFirst}</Alert>
                ) : automatic ? (
                  <>
                    {/* Room-TYPE = assignment criteria (not a display filter). */}
                    {typeOptions.length > 1 ? (
                      <div className="resform-book__grid">
                        <FormField label={b.filterType} htmlFor="wiz-book-auto-type">
                          <Select
                            id="wiz-book-auto-type"
                            value={lineType}
                            options={typeOptions}
                            onChange={(e) => selectAutoType(e.target.value)}
                          />
                        </FormField>
                      </div>
                    ) : null}

                    {roomsLoading ? (
                      <p className="muted small">{b.loadingRooms}</p>
                    ) : null}
                    {!roomsLoading && roomsError ? (
                      <Alert tone="warning">{b.roomsError}</Alert>
                    ) : null}
                    {!roomsLoading && !roomsError && rooms.length === 0 ? (
                      <p className="muted small">{b.noAvailableRooms}</p>
                    ) : null}
                    {!roomsLoading && !roomsError && rooms.length > 0 ? (
                      <>
                        <Alert tone="info">{b.autoRoomBox}</Alert>
                        {autoMatchCount > 0 ? (
                          <p className="muted small">
                            {b.autoRoomCount.replace(
                              "{count}",
                              String(autoMatchCount),
                            )}
                          </p>
                        ) : null}
                      </>
                    ) : null}
                  </>
                ) : (
                  <>
                    {typeOptions.length > 1 ? (
                      <div className="resform-book__grid">
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
                    ) : null}

                    {roomsLoading ? (
                      <p className="muted small">{b.loadingRooms}</p>
                    ) : null}
                    {!roomsLoading && roomsError ? (
                      <Alert tone="warning">{b.roomsError}</Alert>
                    ) : null}
                    {!roomsLoading && !roomsError && visibleRooms.length === 0 ? (
                      <p className="muted small">{b.noAvailableRooms}</p>
                    ) : null}

                    {visibleRooms.length > 0 ? (
                      <div className="resform-book__rooms">
                        {visibleRooms.map((row) => {
                          const selected = row.id === booking.selected_room_id;
                          return (
                            <div
                              key={row.id}
                              className={cx(
                                "resform-book__room",
                                selected && "resform-book__room--selected",
                              )}
                            >
                              <span className="cluster">
                                <strong>{row.number}</strong>
                                <span className="muted small">
                                  {row.room_type_name}
                                </span>
                                <span className="muted small">
                                  {formatCapacity(
                                    row.base_capacity,
                                    row.max_capacity,
                                    t,
                                    locale,
                                  )}
                                </span>
                                <span className="muted small">
                                  {row.base_rate
                                    ? formatMoney(row.base_rate, row.currency, locale)
                                    : "—"}
                                </span>
                                {selected ? (
                                  <Badge tone="success">{b.selected}</Badge>
                                ) : null}
                              </span>
                              <Button
                                type="button"
                                variant={selected ? "primary" : "secondary"}
                                size="sm"
                                onClick={() => selectRoom(row)}
                              >
                                {selected ? b.selected : b.select}
                              </Button>
                            </div>
                          );
                        })}
                      </div>
                    ) : null}

                    {overCapacity && selectedRoom ? (
                      <Alert tone="warning">
                        {b.capacityWarning
                          .replace("{max}", String(selectedRoom.max_capacity))
                          .replace("{total}", String(partySize))}
                      </Alert>
                    ) : null}
                  </>
                )}
              </>
            )}
          </>
        )}
      </section>

      {/* (4) Immediate check-in — CREATE only (edit is never the immediate path,
          §33); gated by both permissions, default OFF. */}
      {canImmediate && !isEdit ? (
        <section className="resform-book__group">
          <GroupHeading icon={LogIn}>{b.immediateSection}</GroupHeading>
          <Switch
            id="wiz-book-immediate"
            checked={immediate}
            onChange={toggleImmediate}
            label={b.immediateToggle}
          />
          <p className="muted small">{b.immediateHint}</p>
          {immediateDateMismatch ? (
            <Alert tone="warning">{b.immediateTodayHint}</Alert>
          ) : null}
        </section>
      ) : null}

      {/* (5a) Recorded payments — read-only history (§31/§35). EDIT only: an old
          transaction is displayed, never re-submitted as a form field. */}
      {isEdit ? (
        <RecordedPaymentsCard summary={editContext?.financialSummary ?? null} />
      ) : null}

      {/* (5b) Price & payment / NEW deposit — real money, honest to the backend
          model. Hidden in edit when a stay exists or the user lacks
          finance.payment_create (a deposit then goes through the folio, §27). */}
      {!isEdit || editContext?.allowNewDeposit ? (
        <PaymentSection
          draft={draft}
          actions={actions}
          reservationCurrency={baseCurrency}
          acceptedCurrencies={settings?.accepted_currencies ?? []}
          canOverrideRate={can("exchange_rate.override")}
          immediate={immediate}
          selectedRoom={selectedRoom}
          estimatedTotal={estimatedTotal}
          estimatedRemaining={estimatedRemaining}
          baseEquivalent={baseEquivalent}
          paidBase={paidBase}
        />
      ) : null}

      {/* (6) Notes — modest height, grows within reason (CSS resize). */}
      <section className="resform-book__group">
        <GroupHeading icon={StickyNote}>{b.notesSection}</GroupHeading>
        <FormField
          label={b.notesLabel}
          htmlFor="wiz-book-notes"
          className="resform-book__full"
        >
          <Textarea
            id="wiz-book-notes"
            rows={2}
            value={booking.notes}
            placeholder={b.notesPlaceholder}
            onChange={(e) => actions.patchBooking({ notes: e.target.value })}
          />
        </FormField>
      </section>
    </div>
  );
}

/** EDIT read-only record of payments already taken on the reservation (§31/§35).
 * Money is display-only (backend Decimal strings, never Float, never editable as
 * a field). Gated server-side by finance.view — when hidden, `can_view_money` is
 * false and every money field is null. */
function RecordedPaymentsCard({
  summary,
}: {
  summary: ReservationFinancialSummary | null;
}) {
  const { t, locale } = useI18n();
  const b = t.reservations.wizard.booking;
  if (!summary) return null;

  if (!summary.can_view_money) {
    return (
      <section className="resform-book__group">
        <GroupHeading icon={CreditCard}>{b.recordedPaymentsSection}</GroupHeading>
        <p className="muted small">{b.financialHidden}</p>
      </section>
    );
  }

  const currency = summary.currency;
  const money = (value: string | null) =>
    value ? formatMoney(value, currency, locale) : "—";

  return (
    <section className="resform-book__group">
      <GroupHeading icon={CreditCard}>{b.recordedPaymentsSection}</GroupHeading>
      <p className="muted small">{b.recordedPaymentsDescription}</p>
      <div className="resform-book__grid">
        <FormField label={b.reservationTotal} htmlFor="wiz-rec-total">
          <Input
            id="wiz-rec-total"
            type="text"
            value={money(summary.reservation_total)}
            readOnly
          />
        </FormField>
        <FormField label={b.paidLabel} htmlFor="wiz-rec-paid">
          <Input id="wiz-rec-paid" type="text" value={money(summary.paid)} readOnly />
        </FormField>
        <FormField label={b.remaining} htmlFor="wiz-rec-remaining">
          <Input
            id="wiz-rec-remaining"
            type="text"
            value={money(summary.remaining)}
            readOnly
          />
        </FormField>
        <FormField label={b.paymentStatusLabel}>
          {summary.payment_status ? (
            <PaymentStatusBadge
              status={summary.payment_status}
              labels={b.paymentStatus}
            />
          ) : (
            <span className="muted">—</span>
          )}
        </FormField>
      </div>
      {summary.payments.length === 0 ? (
        <p className="muted small">{b.noPaymentsYet}</p>
      ) : (
        <ul className="stack-tight resform-payments">
          {summary.payments.map((payment) => {
            const payCurrency = payment.currency || currency;
            const showOriginal =
              payment.payment_currency !== "" &&
              payment.payment_currency !== payCurrency &&
              payment.original_amount !== null;
            return (
              <li key={payment.id} className="line-row">
                <span className="cluster">
                  <strong>{formatMoney(payment.amount, payCurrency, locale)}</strong>
                  <span className="muted small">{t.finance.methods[payment.method]}</span>
                  {showOriginal ? (
                    <span className="muted small">
                      {formatMoney(
                        payment.original_amount as string,
                        payment.payment_currency,
                        locale,
                      )}
                    </span>
                  ) : null}
                </span>
                <span className="muted small">{formatDate(payment.paid_at, locale)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** The three payment methods the desk offers (`on_room_account` shows only with
 * a real folio — i.e. immediate check-in — and records NO payment, §30). */
type UiPayMethod = "" | "cash" | "internal_electronic" | "on_room_account";

/** The price + REAL payment sub-form (§26/§28/§29/§30/§31). Shows the room price,
 * reservation currency and total, then an honest payment block that works for
 * BOTH a deposit-for-future and an immediate deposit; when the payment currency
 * differs from the reservation currency it exposes the FX rate + direction +
 * equivalent (gated by `exchange_rate.override`). A compact live totals strip
 * (total · paid · remaining) closes the group — remaining is DISPLAY-only (never
 * editable, never stored). Amount 0 ⇒ no method required, no money movement. */
function PaymentSection({
  draft,
  actions,
  reservationCurrency,
  acceptedCurrencies,
  canOverrideRate,
  immediate,
  selectedRoom,
  estimatedTotal,
  estimatedRemaining,
  baseEquivalent,
  paidBase,
}: {
  draft: ReservationDraft;
  actions: ReservationDraftActions;
  reservationCurrency: string;
  acceptedCurrencies: string[];
  canOverrideRate: boolean;
  immediate: boolean;
  selectedRoom: RoomAvailabilityRow | null;
  estimatedTotal: string | null;
  estimatedRemaining: string | null;
  baseEquivalent: string | null;
  paidBase: string;
}) {
  const { t, locale } = useI18n();
  const b = t.reservations.wizard.booking;
  const payment = draft.booking.payment;

  // `on_room_account` is a UI-only choice that records nothing; reset it when the
  // reservation is no longer an immediate check-in (no folio exists yet).
  const [onRoomAccount, setOnRoomAccount] = useState(false);
  useEffect(() => {
    if (!immediate && onRoomAccount) setOnRoomAccount(false);
  }, [immediate, onRoomAccount]);

  const methodValue: UiPayMethod = onRoomAccount
    ? "on_room_account"
    : payment.method === "cash" || payment.method === "internal_electronic"
      ? payment.method
      : "";
  const methodChoices: UiPayMethod[] = immediate
    ? ["", "cash", "internal_electronic", "on_room_account"]
    : ["", "cash", "internal_electronic"];

  function setMethod(value: UiPayMethod) {
    if (value === "cash" || value === "internal_electronic") {
      setOnRoomAccount(false);
      actions.patchPayment({ method: value });
    } else {
      // "" (no payment) or on-room-account — clear every money field.
      setOnRoomAccount(value === "on_room_account");
      actions.patchPayment({
        method: "",
        amount: "",
        original_amount: "",
        exchange_rate: "",
        rate_basis: "",
      });
    }
  }

  // Payment-currency options: the reservation/base currency is always accepted.
  const currencyOptions = useMemo(() => {
    const set = new Set<string>();
    if (reservationCurrency) set.add(reservationCurrency);
    for (const code of acceptedCurrencies) if (code) set.add(code);
    return Array.from(set, (value) => ({ value, label: value }));
  }, [reservationCurrency, acceptedCurrencies]);

  const payCurrency = payment.currency || reservationCurrency;
  const isForeign = Boolean(reservationCurrency) && payCurrency !== reservationCurrency;
  const takesDeposit =
    methodValue === "cash" || methodValue === "internal_electronic";

  function setCurrency(next: string) {
    if (next === reservationCurrency) {
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

  const hasRoom = selectedRoom !== null;
  const nightlyDisplay =
    hasRoom && selectedRoom!.base_rate
      ? formatMoney(selectedRoom!.base_rate, reservationCurrency, locale)
      : "—";
  const totalDisplay = estimatedTotal
    ? formatMoney(estimatedTotal, reservationCurrency, locale)
    : "—";
  const remainingDisplay = estimatedRemaining
    ? formatMoney(estimatedRemaining, reservationCurrency, locale)
    : "—";
  const paidDisplay = formatMoney(paidBase, reservationCurrency, locale);

  return (
    <section className="resform-book__group">
      <GroupHeading icon={CreditCard}>{b.priceSection}</GroupHeading>

      {/* Price — reservation currency, from the backend room rate (§26). */}
      <div className="resform-book__grid resform-book__grid--3">
        <FormField label={b.nightlyPrice} htmlFor="wiz-pay-nightly">
          <Input id="wiz-pay-nightly" type="text" value={nightlyDisplay} readOnly />
        </FormField>
        <FormField label={b.reservationCurrency} htmlFor="wiz-pay-res-currency">
          <Input
            id="wiz-pay-res-currency"
            type="text"
            value={reservationCurrency || "—"}
            readOnly
          />
        </FormField>
        <FormField label={b.reservationTotal} htmlFor="wiz-pay-total">
          <Input id="wiz-pay-total" type="text" value={totalDisplay} readOnly />
        </FormField>
      </div>

      {/* Payment method — real receipt (§28/§30) + tender fields on the same row. */}
      <div className="resform-book__grid">
        <FormField label={b.paymentMethod} htmlFor="wiz-pay-method" hint={b.noPaymentHint}>
          <Select
            id="wiz-pay-method"
            value={methodValue}
            options={methodChoices.map((value) => ({
              value,
              label: value === "" ? b.method.none : b.method[value],
            }))}
            onChange={(e) => setMethod(e.target.value as UiPayMethod)}
          />
        </FormField>

        {takesDeposit && currencyOptions.length > 1 ? (
          <FormField label={b.paymentCurrency} htmlFor="wiz-pay-currency">
            <Select
              id="wiz-pay-currency"
              value={payCurrency}
              options={currencyOptions}
              onChange={(e) => setCurrency(e.target.value)}
            />
          </FormField>
        ) : null}

        {takesDeposit && !isForeign ? (
          <FormField
            label={b.paidAmount.replace("{currency}", reservationCurrency || payCurrency)}
            htmlFor="wiz-pay-amount"
          >
            <Input
              id="wiz-pay-amount"
              inputMode="decimal"
              value={payment.amount}
              onChange={(e) => actions.patchPayment({ amount: e.target.value })}
            />
          </FormField>
        ) : null}

        {takesDeposit && isForeign ? (
          <>
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
            <FormField label={b.baseEquivalent} htmlFor="wiz-pay-equivalent">
              <Input
                id="wiz-pay-equivalent"
                type="text"
                value={
                  baseEquivalent
                    ? formatMoney(baseEquivalent, reservationCurrency, locale)
                    : "—"
                }
                readOnly
              />
            </FormField>
          </>
        ) : null}
      </div>

      {onRoomAccount ? <Alert tone="info">{b.onRoomAccountHint}</Alert> : null}
      {takesDeposit && !immediate ? (
        <Alert tone="info">{b.depositForFutureHint}</Alert>
      ) : null}

      {/* Compact live totals — the in-step summary replacing the old review. */}
      {estimatedTotal ? (
        <>
          <dl className="resform-book__totals">
            <div className="resform-book__total">
              <dt>{b.reservationTotal}</dt>
              <dd>{totalDisplay}</dd>
            </div>
            <div className="resform-book__total">
              <dt>{b.paidLabel}</dt>
              <dd>{paidDisplay}</dd>
            </div>
            <div className="resform-book__total resform-book__total--accent">
              <dt>{b.remaining}</dt>
              <dd>{remainingDisplay}</dd>
            </div>
          </dl>
          <p className="muted small">{b.reservationTotalEstimate}</p>
        </>
      ) : null}
    </section>
  );
}
