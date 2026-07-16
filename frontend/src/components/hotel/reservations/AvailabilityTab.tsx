"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { CalendarSearch, Search } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  FilterBar,
  FormField,
  Input,
  Select,
  SectionHeader,
} from "@/components/ui";
import { cx } from "@/lib/utils";
import { checkAvailability, type AvailabilityParams } from "@/lib/api/reservations";
import { listRoomTypes } from "@/lib/api/rooms";
import { messageForError } from "@/lib/api/errors";
import type { RoomType, TypeAvailability } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** Backend-driven availability checker. The server computes availability; this
 * only renders the result — it never decides bookability itself. */
export function AvailabilityTab({
  refreshSignal = 0,
}: {
  refreshSignal?: number;
}) {
  const { t } = useI18n();
  const [types, setTypes] = useState<RoomType[]>([]);
  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [adults, setAdults] = useState("2");
  const [children, setChildren] = useState("0");
  const [roomType, setRoomType] = useState("");
  const [results, setResults] = useState<TypeAvailability[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRoomTypes()
      .then((r) => setTypes(r.results))
      .catch(() => setTypes([]));
  }, []);

  // The exact criteria of the LAST executed search. A tab-return refetch re-runs
  // THIS query (not the half-edited form inputs), so the grid stays in sync with
  // what the operator actually asked for. Null until the first search → nothing
  // can fire on mount (availability needs the user's dates first).
  const lastQuery = useRef<AvailabilityParams | null>(null);

  // One request path for both the user's submit and the background tab-return
  // refetch. `background` makes failure NON-DESTRUCTIVE: the previously shown
  // results stay on screen and only the error Alert updates; a user-initiated
  // submit keeps its original behavior of clearing results on error.
  const runSearch = useCallback(
    async (params: AvailabilityParams, opts?: { background?: boolean }) => {
      setError(null);
      setBusy(true);
      try {
        const res = await checkAvailability(params);
        setResults(res.results);
      } catch (err) {
        setError(messageForError(err, t));
        if (!opts?.background) setResults(null);
      } finally {
        setBusy(false);
      }
    },
    [t],
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!checkIn || !checkOut) {
      setError(t.errors.validation);
      return;
    }
    const params: AvailabilityParams = {
      check_in_date: checkIn,
      check_out_date: checkOut,
      adults: Number(adults) || undefined,
      children: Number(children) || undefined,
      room_type: roomType ? Number(roomType) : undefined,
    };
    // Record the SUBMITTED criteria as the "last query" before running it, so a
    // later tab-return re-runs exactly this (not whatever the form holds then).
    lastQuery.current = params;
    runSearch(params);
  }

  // The page pulses `refreshSignal` when the operator returns to this tab
  // (visibilitychange). IF a search has already run, re-run THAT exact query in
  // place — no remount, no form/filter reset, last results kept on failure.
  // Consume real increments only (the initial value must not fire on mount). If a
  // signal lands WHILE a request is in flight it is intentionally skipped, not
  // queued: that in-flight request is already fetching fresh data, so a second
  // pass would be a redundant/overlapping request. The next tab-return refreshes.
  const lastRefreshSignal = useRef(refreshSignal);
  useEffect(() => {
    if (refreshSignal !== lastRefreshSignal.current) {
      lastRefreshSignal.current = refreshSignal;
      if (lastQuery.current && !busy) {
        runSearch(lastQuery.current, { background: true });
      }
    }
  }, [refreshSignal, busy, runSearch]);

  const typeOptions = types.map((ty) => ({ value: String(ty.id), label: ty.name }));

  return (
    <div className="stack">
      <SectionHeader title={t.reservations.availability.title} icon={CalendarSearch} />
      <Card>
        <form onSubmit={submit}>
          <FilterBar>
            <FormField label={t.reservations.availability.checkIn} htmlFor="av-in">
              <Input id="av-in" type="date" value={checkIn} required onChange={(e) => setCheckIn(e.target.value)} />
            </FormField>
            <FormField label={t.reservations.availability.checkOut} htmlFor="av-out">
              <Input id="av-out" type="date" value={checkOut} required onChange={(e) => setCheckOut(e.target.value)} />
            </FormField>
            <FormField label={t.reservations.availability.adults} htmlFor="av-adults">
              <Input id="av-adults" type="number" min="0" value={adults} onChange={(e) => setAdults(e.target.value)} />
            </FormField>
            <FormField label={t.reservations.availability.children} htmlFor="av-children">
              <Input id="av-children" type="number" min="0" value={children} onChange={(e) => setChildren(e.target.value)} />
            </FormField>
            <FormField label={t.reservations.availability.roomType} htmlFor="av-type">
              <Select id="av-type" value={roomType} placeholder={t.reservations.availability.allTypes} options={typeOptions} onChange={(e) => setRoomType(e.target.value)} />
            </FormField>
            <div className="filter-bar__actions cluster">
              <Button type="submit" icon={Search} loading={busy}>
                {busy ? t.reservations.availability.checking : t.reservations.availability.check}
              </Button>
            </div>
          </FilterBar>
        </form>
      </Card>

      {error ? <Alert tone="error">{error}</Alert> : null}

      {results === null ? (
        <EmptyState
          title={t.reservations.availability.empty}
          hint={t.reservations.availability.emptyHint}
          icon={CalendarSearch}
        />
      ) : (
        <div className="avail-grid">
          {results.map((row) => (
            <article
              key={row.room_type}
              className={cx("avail-card", row.can_book ? "avail-card--ok" : "avail-card--full")}
            >
              <div className="avail-card__head">
                <span className="avail-card__name">{row.room_type_name}</span>
                <Badge tone={row.can_book ? "success" : "danger"}>
                  {row.can_book
                    ? t.reservations.availability.canBook
                    : t.reservations.availability.cannotBook}
                </Badge>
              </div>
              <div className="avail-card__figure">
                <span className="avail-card__available">{row.available_quantity}</span>
                <span className="muted">/ {row.total_rooms} {t.reservations.availability.total}</span>
              </div>
              <dl className="avail-card__stats">
                <div><dt>{t.reservations.availability.reserved}</dt><dd>{row.reserved_quantity}</dd></div>
                <div><dt>{t.reservations.availability.blocked}</dt><dd>{row.blocked_rooms}</dd></div>
              </dl>
              {!row.can_book && row.reason ? (
                <p className="avail-card__reason">
                  {t.reservations.availability.reasons[
                    row.reason as keyof typeof t.reservations.availability.reasons
                  ] ?? row.reason}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
