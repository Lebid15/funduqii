"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Check, Copy, Search } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  FormField,
  Input,
  Select,
  Textarea,
} from "@/components/ui";
import {
  createPublicBooking,
  getPublicAvailability,
  type PublicBooking,
  type PublicHotelDetail,
  type PublicTypeAvailability,
} from "@/lib/api/public";
import { messageForError } from "@/lib/api/errors";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * The public booking flow on a hotel page (Phase 15):
 * dates → availability (live counts from the same engine as the console) →
 * guest details → booking. On success the reference + ONE-TIME manage token
 * are shown — the token is never retrievable again.
 */
export function PublicBookingPanel({ hotel }: { hotel: PublicHotelDetail }) {
  const { t } = useI18n();

  const [checkIn, setCheckIn] = useState("");
  const [checkOut, setCheckOut] = useState("");
  const [availability, setAvailability] = useState<PublicTypeAvailability[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [availabilityError, setAvailabilityError] = useState<string | null>(null);

  const [roomTypeId, setRoomTypeId] = useState("");
  const [roomsCount, setRoomsCount] = useState("1");
  const [adults, setAdults] = useState("2");
  const [children, setChildren] = useState("0");
  const [guestName, setGuestName] = useState("");
  const [guestPhone, setGuestPhone] = useState("");
  const [guestEmail, setGuestEmail] = useState("");
  const [special, setSpecial] = useState("");
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [booking, setBooking] = useState<PublicBooking | null>(null);
  const [copied, setCopied] = useState(false);

  async function checkAvailability(event: FormEvent) {
    event.preventDefault();
    if (!checkIn || !checkOut) return;
    setChecking(true);
    setAvailabilityError(null);
    setAvailability(null);
    setRoomTypeId("");
    try {
      const result = await getPublicAvailability(hotel.slug, checkIn, checkOut);
      setAvailability(result.room_types);
      const first = result.room_types.find((row) => row.can_book);
      if (first) setRoomTypeId(String(first.id));
    } catch (err) {
      setAvailabilityError(messageForError(err, t));
    } finally {
      setChecking(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!roomTypeId) return;
    setSubmitError(null);
    setBusy(true);
    try {
      const created = await createPublicBooking(hotel.slug, {
        check_in: checkIn,
        check_out: checkOut,
        room_type: Number(roomTypeId),
        rooms_count: Number(roomsCount) || 1,
        adults: Number(adults) || 1,
        children: Number(children) || 0,
        guest_name: guestName.trim(),
        guest_phone: guestPhone.trim(),
        guest_email: guestEmail.trim(),
        special_requests: special.trim(),
        accept_terms: acceptTerms,
      });
      setBooking(created);
    } catch (err) {
      setSubmitError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  async function copyToken() {
    if (!booking?.manage_token) return;
    try {
      await navigator.clipboard.writeText(booking.manage_token);
      setCopied(true);
    } catch {
      // Clipboard unavailable — the token stays visible for manual copy.
    }
  }

  // --- Success: reference + one-time token -------------------------------
  if (booking) {
    return (
      <div className="public-booking public-booking--success">
        <h3 className="public-booking__title">{t.public.booking.successTitle}</h3>
        <Alert tone={booking.requires_confirmation ? "info" : "success"}>
          {booking.requires_confirmation
            ? t.public.booking.successHeld
            : t.public.booking.successConfirmed}
        </Alert>
        <dl className="detail-grid">
          <div>
            <dt>{t.public.booking.reference}</dt>
            <dd className="public-booking__reference" dir="ltr">{booking.reference}</dd>
          </div>
          <div>
            <dt>{t.public.manage.dates}</dt>
            <dd>{booking.check_in_date} → {booking.check_out_date}</dd>
          </div>
          <div>
            <dt>{t.public.manage.roomType}</dt>
            <dd>{booking.room_type_name}</dd>
          </div>
        </dl>
        {booking.manage_token ? (
          <div className="public-booking__token-box">
            <p className="public-booking__token-label">{t.public.booking.manageToken}</p>
            <code className="public-booking__token" dir="ltr">{booking.manage_token}</code>
            <Alert tone="warning">{t.public.booking.tokenWarning}</Alert>
            <div className="cluster">
              <Button
                variant="secondary"
                size="sm"
                icon={copied ? Check : Copy}
                onClick={copyToken}
              >
                {copied ? t.public.booking.copied : t.public.booking.copyToken}
              </Button>
              <Link
                className="btn btn--primary btn--sm"
                href={`/booking/manage?reference=${encodeURIComponent(booking.reference)}`}
              >
                {t.public.booking.goToManage}
              </Link>
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  // --- Booking disabled ----------------------------------------------------
  if (!hotel.booking_enabled) {
    return (
      <div className="public-booking">
        <h3 className="public-booking__title">{t.public.booking.title}</h3>
        <Alert tone="info">{t.public.booking.closed}</Alert>
      </div>
    );
  }

  const selectable = (availability ?? []).filter((row) => row.can_book);
  const typeOptions = selectable.map((row) => ({
    value: String(row.id),
    label: `${row.name} — ${t.public.booking.roomsLeft.replace("{count}", String(row.available_quantity))}`,
  }));

  return (
    <div className="public-booking">
      <h3 className="public-booking__title">{t.public.booking.title}</h3>

      <form className="public-booking__dates" onSubmit={checkAvailability} noValidate>
        <FormField label={t.public.booking.checkIn} htmlFor="pb-check-in">
          <Input
            id="pb-check-in"
            type="date"
            value={checkIn}
            required
            onChange={(e) => setCheckIn(e.target.value)}
          />
        </FormField>
        <FormField label={t.public.booking.checkOut} htmlFor="pb-check-out">
          <Input
            id="pb-check-out"
            type="date"
            value={checkOut}
            required
            onChange={(e) => setCheckOut(e.target.value)}
          />
        </FormField>
        <Button type="submit" icon={Search} loading={checking}>
          {t.public.booking.checkAvailability}
        </Button>
      </form>

      {availabilityError ? <Alert tone="error">{availabilityError}</Alert> : null}

      {availability !== null && !availabilityError ? (
        selectable.length === 0 ? (
          <Alert tone="warning">{t.public.booking.unavailable}</Alert>
        ) : (
          <form className="stack" onSubmit={submit} noValidate>
            <div className="public-booking__types">
              {availability.map((row) => (
                <div key={row.id} className="public-booking__type-row">
                  <span className="public-booking__type-name">{row.name}</span>
                  {row.base_price ? (
                    <span className="muted">
                      {row.base_price} {row.currency} {t.public.hotel.perNight}
                    </span>
                  ) : null}
                  <Badge tone={row.can_book ? "success" : "neutral"}>
                    {row.can_book
                      ? t.public.booking.roomsLeft.replace(
                          "{count}",
                          String(row.available_quantity),
                        )
                      : t.public.booking.soldOut}
                  </Badge>
                </div>
              ))}
            </div>

            {submitError ? <Alert tone="error">{submitError}</Alert> : null}

            <div className="form-grid">
              <FormField label={t.public.booking.selectType} htmlFor="pb-type">
                <Select
                  id="pb-type"
                  value={roomTypeId}
                  options={typeOptions}
                  onChange={(e) => setRoomTypeId(e.target.value)}
                />
              </FormField>
              <FormField label={t.public.booking.roomsCount} htmlFor="pb-rooms">
                <Input
                  id="pb-rooms"
                  type="number"
                  min="1"
                  max="5"
                  value={roomsCount}
                  onChange={(e) => setRoomsCount(e.target.value)}
                />
              </FormField>
              <FormField label={t.public.booking.adults} htmlFor="pb-adults">
                <Input
                  id="pb-adults"
                  type="number"
                  min="1"
                  value={adults}
                  onChange={(e) => setAdults(e.target.value)}
                />
              </FormField>
              <FormField label={t.public.booking.children} htmlFor="pb-children">
                <Input
                  id="pb-children"
                  type="number"
                  min="0"
                  value={children}
                  onChange={(e) => setChildren(e.target.value)}
                />
              </FormField>
              <FormField label={t.public.booking.guestName} htmlFor="pb-name">
                <Input
                  id="pb-name"
                  value={guestName}
                  required
                  onChange={(e) => setGuestName(e.target.value)}
                />
              </FormField>
              <FormField label={t.public.booking.guestPhone} htmlFor="pb-phone">
                <Input
                  id="pb-phone"
                  dir="ltr"
                  value={guestPhone}
                  required
                  onChange={(e) => setGuestPhone(e.target.value)}
                />
              </FormField>
              <FormField
                label={t.public.booking.guestEmail}
                htmlFor="pb-email"
                className="form-grid__full"
              >
                <Input
                  id="pb-email"
                  type="email"
                  dir="ltr"
                  value={guestEmail}
                  onChange={(e) => setGuestEmail(e.target.value)}
                />
              </FormField>
              <FormField
                label={t.public.booking.specialRequests}
                htmlFor="pb-special"
                className="form-grid__full"
              >
                <Textarea
                  id="pb-special"
                  value={special}
                  onChange={(e) => setSpecial(e.target.value)}
                />
              </FormField>
            </div>

            <label className="public-booking__terms">
              <input
                type="checkbox"
                checked={acceptTerms}
                onChange={(e) => setAcceptTerms(e.target.checked)}
              />
              <span>{t.public.booking.acceptTerms}</span>
            </label>

            <Alert tone="info">
              {hotel.requires_confirmation
                ? t.public.booking.confirmationNote
                : t.public.booking.instantNote}
            </Alert>

            <Button type="submit" loading={busy} disabled={!acceptTerms || !roomTypeId} block>
              {t.public.booking.submit}
            </Button>
          </form>
        )
      ) : null}
    </div>
  );
}
