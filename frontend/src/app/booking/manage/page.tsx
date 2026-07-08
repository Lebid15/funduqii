"use client";

import { Suspense, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { Search, TicketCheck } from "lucide-react";

import { PublicShell } from "@/components/public/PublicShell";
import {
  Alert,
  Badge,
  Button,
  FormField,
  Input,
  SectionHeader,
  Textarea,
} from "@/components/ui";
import {
  getPublicBooking,
  requestPublicCancellation,
  type PublicBooking,
} from "@/lib/api/public";
import { messageForError } from "@/lib/api/errors";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Public "manage my booking" page (Phase 15). The visitor enters the booking
 * reference + the one-time manage token (or arrives with ?reference=... from
 * the success screen). A wrong reference and a wrong token are deliberately
 * indistinguishable (both 404).
 */
export default function ManageBookingPage() {
  return (
    <PublicShell>
      <Suspense fallback={null}>
        <ManageBookingContent />
      </Suspense>
    </PublicShell>
  );
}

function ManageBookingContent() {
  const { t } = useI18n();
  const params = useSearchParams();

  const [reference, setReference] = useState(params.get("reference") ?? "");
  const [token, setToken] = useState("");
  const [booking, setBooking] = useState<PublicBooking | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [cancelReason, setCancelReason] = useState("");
  const [cancelBusy, setCancelBusy] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  async function lookup(event: FormEvent) {
    event.preventDefault();
    if (!reference.trim() || !token.trim()) return;
    setBusy(true);
    setError(null);
    setBooking(null);
    try {
      setBooking(await getPublicBooking(reference.trim(), token.trim()));
    } catch (err) {
      const status = (err as { status?: number }).status;
      setError(
        status === 404 ? t.public.manage.notFoundError : messageForError(err, t),
      );
    } finally {
      setBusy(false);
    }
  }

  async function submitCancelRequest(event: FormEvent) {
    event.preventDefault();
    if (!booking) return;
    setCancelBusy(true);
    setCancelError(null);
    try {
      setBooking(
        await requestPublicCancellation(
          booking.reference,
          token.trim(),
          cancelReason.trim(),
        ),
      );
    } catch (err) {
      setCancelError(messageForError(err, t));
    } finally {
      setCancelBusy(false);
    }
  }

  const statusLabel =
    t.public.status[booking?.status as keyof typeof t.public.status] ??
    booking?.status ??
    "";
  const statusTone =
    booking?.status === "confirmed"
      ? "success"
      : booking?.status === "held"
        ? "info"
        : "neutral";

  return (
    <section className="public-section public-section--narrow">
      <SectionHeader
        title={t.public.manage.title}
        description={t.public.manage.subtitle}
        icon={TicketCheck}
      />

      <form className="public-panel stack" onSubmit={lookup} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.public.manage.reference} htmlFor="mb-reference">
            <Input
              id="mb-reference"
              dir="ltr"
              value={reference}
              required
              onChange={(e) => setReference(e.target.value)}
            />
          </FormField>
          <FormField
            label={t.public.manage.token}
            htmlFor="mb-token"
            hint={t.public.manage.tokenHint}
          >
            <Input
              id="mb-token"
              dir="ltr"
              value={token}
              required
              onChange={(e) => setToken(e.target.value)}
            />
          </FormField>
        </div>
        <Button type="submit" icon={Search} loading={busy}>
          {t.public.manage.view}
        </Button>
      </form>

      {booking ? (
        <div className="public-panel stack">
          <div className="cluster">
            <Badge tone={statusTone}>{statusLabel}</Badge>
            {booking.status === "held" ? (
              <span className="muted">{t.public.manage.heldNote}</span>
            ) : null}
          </div>

          {booking.cancel_requested_at ? (
            <Alert tone="warning">{t.public.manage.cancelRequested}</Alert>
          ) : null}

          <dl className="detail-grid">
            <div>
              <dt>{t.public.manage.reference}</dt>
              <dd dir="ltr">{booking.reference}</dd>
            </div>
            <div>
              <dt>{t.public.manage.hotel}</dt>
              <dd>{booking.hotel_name}</dd>
            </div>
            <div>
              <dt>{t.public.manage.dates}</dt>
              <dd>
                {booking.check_in_date} → {booking.check_out_date} (
                {booking.nights} {t.public.hotel.nights})
              </dd>
            </div>
            <div>
              <dt>{t.public.manage.roomType}</dt>
              <dd>{booking.room_type_name}</dd>
            </div>
            <div>
              <dt>{t.public.manage.roomsCount}</dt>
              <dd>{booking.rooms_count}</dd>
            </div>
            <div>
              <dt>{t.public.manage.guests}</dt>
              <dd>
                {booking.adults} + {booking.children}
              </dd>
            </div>
            <div>
              <dt>{t.public.booking.guestName}</dt>
              <dd>{booking.guest_name}</dd>
            </div>
          </dl>

          {booking.special_requests ? (
            <div>
              <h4>{t.public.manage.requests}</h4>
              <p className="muted public-prewrap">{booking.special_requests}</p>
            </div>
          ) : null}

          {!booking.cancel_requested_at &&
          (booking.status === "held" || booking.status === "confirmed") ? (
            <form className="stack" onSubmit={submitCancelRequest} noValidate>
              <h4>{t.public.manage.cancelTitle}</h4>
              <p className="muted">{t.public.manage.cancelNote}</p>
              {cancelError ? <Alert tone="error">{cancelError}</Alert> : null}
              <FormField label={t.public.manage.cancelReason} htmlFor="mb-cancel-reason">
                <Textarea
                  id="mb-cancel-reason"
                  value={cancelReason}
                  onChange={(e) => setCancelReason(e.target.value)}
                />
              </FormField>
              <Button type="submit" variant="danger" loading={cancelBusy}>
                {t.public.manage.cancelSubmit}
              </Button>
            </form>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
