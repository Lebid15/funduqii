"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { PageContainer } from "@/components/layout/PageContainer";
import {
  Alert,
  Badge,
  Button,
  Card,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  PageHeader,
  PasswordInput,
  SectionHeader,
  Select,
  useToast,
} from "@/components/ui";
import { getHotel, setHotelManager, updateHotel } from "@/lib/api/platform";
import { messageForError } from "@/lib/api/errors";
import type { Hotel } from "@/lib/api/types";
import {
  formatDate,
  hotelStatusLabel,
  hotelStatusTone,
  subscriptionStatusLabel,
  subscriptionStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function HotelDetailPage() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const params = useParams<{ id: string }>();
  const hotelId = Number(params.id);

  const [hotel, setHotel] = useState<Hotel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Await-first: no synchronous setState on the effect tick.
  const load = useCallback(async () => {
    try {
      const data = await getHotel(hotelId);
      setHotel(data);
      setError(null);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [hotelId, t]);

  useEffect(() => {
    load();
  }, [load]);

  const reload = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);

  return (
    <PageContainer>
      <PageHeader
        title={t.hotels.detailTitle}
        actions={
          <Link className="btn btn--secondary btn--sm" href="/platform/hotels">
            {t.hotels.backToList}
          </Link>
        }
      />

      {loading ? <LoadingState label={t.common.loading} /> : null}

      {!loading && error ? (
        <ErrorState
          title={t.states.errorTitle}
          message={error}
          retryLabel={t.common.retry}
          onRetry={reload}
        />
      ) : null}

      {!loading && !error && hotel ? (
        <>
          <Card>
            <div className="detail-grid">
              <div className="detail-item">
                <span className="detail-item__label">{t.hotels.name}</span>
                <span className="detail-item__value">{hotel.name}</span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">{t.hotels.slug}</span>
                <span className="detail-item__value">{hotel.slug}</span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">{t.common.status}</span>
                <span>
                  <Badge tone={hotelStatusTone(hotel.status)}>
                    {hotelStatusLabel(hotel.status, t)}
                  </Badge>
                </span>
              </div>
              <div className="detail-item">
                <span className="detail-item__label">{t.common.createdAt}</span>
                <span className="detail-item__value">
                  {formatDate(hotel.created_at, locale)}
                </span>
              </div>
            </div>
          </Card>

          <Card>
            <SectionHeader title={t.hotels.currentSubscription} />
            {hotel.current_subscription ? (
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-item__label">{t.subscriptions.plan}</span>
                  <span className="detail-item__value">
                    {hotel.current_subscription.plan_name}
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-item__label">{t.common.status}</span>
                  <span>
                    <Badge
                      tone={subscriptionStatusTone(
                        hotel.current_subscription.status,
                      )}
                    >
                      {subscriptionStatusLabel(
                        hotel.current_subscription.status,
                        t,
                      )}
                    </Badge>
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-item__label">
                    {t.subscriptions.startsAt}
                  </span>
                  <span className="detail-item__value">
                    {formatDate(hotel.current_subscription.starts_at, locale)}
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-item__label">
                    {t.subscriptions.endsAt}
                  </span>
                  <span className="detail-item__value">
                    {formatDate(hotel.current_subscription.ends_at, locale)}
                  </span>
                </div>
              </div>
            ) : (
              <p className="muted">{t.hotels.noSubscription}</p>
            )}
          </Card>

          <EditHotelCard hotel={hotel} onSaved={load} onNotify={notify} />
          <ManagerCard hotel={hotel} onSaved={load} onNotify={notify} />
        </>
      ) : null}
    </PageContainer>
  );
}

function EditHotelCard({
  hotel,
  onSaved,
  onNotify,
}: {
  hotel: Hotel;
  onSaved: () => void;
  onNotify: (message: string, tone?: "success" | "error") => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(hotel.name);
  const [slug, setSlug] = useState(hotel.slug);
  const [status, setStatus] = useState(hotel.status);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await updateHotel(hotel.id, { name, slug, status });
      onNotify(t.settings.saved);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionHeader title={t.hotels.editTitle} />
      <form className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.hotels.name} htmlFor="edit-name">
            <Input
              id="edit-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </FormField>
          <FormField label={t.hotels.slug} htmlFor="edit-slug">
            <Input
              id="edit-slug"
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
            />
          </FormField>
          <FormField label={t.common.status} htmlFor="edit-status">
            <Select
              id="edit-status"
              value={status}
              options={[
                { value: "setup", label: t.hotels.statusSetup },
                { value: "active", label: t.hotels.statusActive },
                { value: "suspended", label: t.hotels.statusSuspended },
              ]}
              onChange={(event) =>
                setStatus(event.target.value as Hotel["status"])
              }
            />
          </FormField>
        </div>
        <div className="cluster">
          <Button type="submit" disabled={busy}>
            {busy ? t.common.saving : t.common.save}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ManagerCard({
  hotel,
  onSaved,
  onNotify,
}: {
  hotel: Hotel;
  onSaved: () => void;
  onNotify: (message: string, tone?: "success" | "error") => void;
}) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await setHotelManager(hotel.id, {
        email: email.trim(),
        full_name: fullName.trim(),
        password,
      });
      setEmail("");
      setFullName("");
      setPassword("");
      onNotify(t.settings.saved);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionHeader title={t.hotels.managerSection} />
      {hotel.primary_manager ? (
        <p className="muted">
          {hotel.primary_manager.full_name} · {hotel.primary_manager.email}
        </p>
      ) : (
        <p className="muted">{t.hotels.noManager}</p>
      )}
      <form className="stack" onSubmit={submit} noValidate style={{ marginTop: "var(--space-4)" }}>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.hotels.managerFullName} htmlFor="mgr-name">
            <Input
              id="mgr-name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
            />
          </FormField>
          <FormField label={t.hotels.managerEmail} htmlFor="mgr-email">
            <Input
              id="mgr-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </FormField>
          <FormField label={t.hotels.managerPassword} htmlFor="mgr-pass">
            <PasswordInput
              id="mgr-pass"
              value={password}
              showLabel={t.auth.showPassword}
              hideLabel={t.auth.hidePassword}
              onChange={(event) => setPassword(event.target.value)}
            />
          </FormField>
        </div>
        <div className="cluster">
          <Button type="submit" variant="secondary" disabled={busy}>
            {busy ? t.common.saving : t.hotels.assignManager}
          </Button>
        </div>
      </form>
    </Card>
  );
}
