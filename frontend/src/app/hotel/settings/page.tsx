"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  BedDouble,
  Building2,
  Globe,
  MapPin,
  Phone,
  SlidersHorizontal,
} from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { HotelMediaSection } from "@/components/hotel/HotelMediaSection";
import {
  Alert,
  Button,
  Card,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  PageHeader,
  SectionHeader,
  Select,
  Switch,
  Textarea,
  useToast,
} from "@/components/ui";
import { getProfile, getSettings, updateSettings } from "@/lib/api/hotel";
import { messageForError } from "@/lib/api/errors";
import type { HotelSettings } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function HotelSettingsPage() {
  const { t } = useI18n();
  const { notify } = useToast();

  const [settings, setSettings] = useState<HotelSettings | null>(null);
  const [suspended, setSuspended] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [data, profile] = await Promise.all([getSettings(), getProfile()]);
      setSettings(data);
      setSuspended(profile.hotel.status === "suspended");
      setError(null);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const reload = useCallback(() => {
    setLoading(true);
    load();
  }, [load]);

  function patch<K extends keyof HotelSettings>(key: K, value: HotelSettings[K]) {
    setSettings((s) => (s ? { ...s, [key]: value } : s));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!settings || suspended) return;
    setSaveError(null);
    setBusy(true);
    try {
      const { created_at, updated_at, ...editable } = settings;
      void created_at;
      void updated_at;
      const saved = await updateSettings(editable);
      setSettings(saved);
      notify(t.hotel.settings.saved);
    } catch (err) {
      setSaveError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const langOptions = [
    { value: "ar", label: t.language.ar },
    { value: "en", label: t.language.en },
    { value: "tr", label: t.language.tr },
  ];
  const petOptions = [
    { value: "not_allowed", label: t.hotel.settings.petNotAllowed },
    { value: "allowed", label: t.hotel.settings.petAllowed },
    { value: "on_request", label: t.hotel.settings.petOnRequest },
  ];
  const smokingOptions = [
    { value: "not_allowed", label: t.hotel.settings.smokingNotAllowed },
    { value: "allowed", label: t.hotel.settings.smokingAllowed },
    { value: "designated", label: t.hotel.settings.smokingDesignated },
  ];

  const s = settings;

  return (
    <PageContainer>
      <PageHeader
        title={t.hotel.settings.title}
        subtitle={t.hotel.settings.subtitle}
        actions={
          s && !suspended ? (
            <Button form="hotel-settings-form" type="submit" loading={busy}>
              {t.hotel.settings.save}
            </Button>
          ) : null
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

      {!loading && !error && s ? (
        <>
          {suspended ? (
            <Alert tone="error">{t.hotel.settings.readOnlySuspended}</Alert>
          ) : null}

          <form id="hotel-settings-form" className="stack" onSubmit={submit} noValidate>
            {saveError ? <Alert tone="error">{saveError}</Alert> : null}

            {/* Identity */}
            <Card className="settings-section">
              <SectionHeader
                title={t.hotel.settings.sectionIdentity}
                description={t.hotel.settings.sectionIdentityDesc}
                icon={Building2}
              />
              <div className="form-grid">
                <FormField label={t.hotel.settings.displayName} htmlFor="display_name">
                  <Input
                    id="display_name"
                    value={s.display_name}
                    disabled={suspended}
                    onChange={(e) => patch("display_name", e.target.value)}
                  />
                </FormField>
                <FormField label={t.hotel.settings.legalName} htmlFor="legal_name">
                  <Input
                    id="legal_name"
                    value={s.legal_name}
                    disabled={suspended}
                    onChange={(e) => patch("legal_name", e.target.value)}
                  />
                </FormField>
                <FormField label={t.hotel.settings.starRating} htmlFor="star_rating">
                  <Input
                    id="star_rating"
                    type="number"
                    min="1"
                    max="5"
                    value={s.star_rating ?? ""}
                    disabled={suspended}
                    onChange={(e) =>
                      patch(
                        "star_rating",
                        e.target.value === "" ? null : Number(e.target.value),
                      )
                    }
                  />
                </FormField>
                <FormField label={t.hotel.settings.timezone} htmlFor="timezone">
                  <Input
                    id="timezone"
                    value={s.timezone}
                    disabled={suspended}
                    onChange={(e) => patch("timezone", e.target.value)}
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.defaultLanguage}
                  htmlFor="default_language"
                >
                  <Select
                    id="default_language"
                    value={s.default_language}
                    options={langOptions}
                    disabled={suspended}
                    onChange={(e) =>
                      patch(
                        "default_language",
                        e.target.value as HotelSettings["default_language"],
                      )
                    }
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.defaultCurrency}
                  htmlFor="default_currency"
                >
                  <Input
                    id="default_currency"
                    maxLength={3}
                    value={s.default_currency}
                    disabled={suspended}
                    onChange={(e) =>
                      patch("default_currency", e.target.value.toUpperCase())
                    }
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.shortDescription}
                  htmlFor="short_description"
                  className="form-grid__full"
                >
                  <Input
                    id="short_description"
                    value={s.short_description}
                    maxLength={280}
                    disabled={suspended}
                    onChange={(e) => patch("short_description", e.target.value)}
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.description}
                  htmlFor="description"
                  className="form-grid__full"
                >
                  <Textarea
                    id="description"
                    value={s.description}
                    disabled={suspended}
                    onChange={(e) => patch("description", e.target.value)}
                  />
                </FormField>
              </div>
            </Card>

            {/* Contact */}
            <Card className="settings-section">
              <SectionHeader
                title={t.hotel.settings.sectionContact}
                description={t.hotel.settings.sectionContactDesc}
                icon={Phone}
              />
              <div className="form-grid">
                <FormField label={t.hotel.settings.phone} htmlFor="phone">
                  <Input
                    id="phone"
                    value={s.phone}
                    disabled={suspended}
                    onChange={(e) => patch("phone", e.target.value)}
                  />
                </FormField>
                <FormField label={t.hotel.settings.whatsapp} htmlFor="whatsapp_number">
                  <Input
                    id="whatsapp_number"
                    value={s.whatsapp_number}
                    disabled={suspended}
                    onChange={(e) => patch("whatsapp_number", e.target.value)}
                  />
                </FormField>
                <FormField label={t.hotel.settings.email} htmlFor="hotel_email">
                  <Input
                    id="hotel_email"
                    type="email"
                    value={s.email}
                    disabled={suspended}
                    onChange={(e) => patch("email", e.target.value)}
                  />
                </FormField>
                <FormField label={t.hotel.settings.website} htmlFor="website_url">
                  <Input
                    id="website_url"
                    type="url"
                    value={s.website_url}
                    disabled={suspended}
                    onChange={(e) => patch("website_url", e.target.value)}
                  />
                </FormField>
                <FormField label={t.hotel.settings.facebook} htmlFor="facebook_url">
                  <Input
                    id="facebook_url"
                    type="url"
                    value={s.facebook_url}
                    disabled={suspended}
                    onChange={(e) => patch("facebook_url", e.target.value)}
                  />
                </FormField>
                <FormField label={t.hotel.settings.instagram} htmlFor="instagram_url">
                  <Input
                    id="instagram_url"
                    type="url"
                    value={s.instagram_url}
                    disabled={suspended}
                    onChange={(e) => patch("instagram_url", e.target.value)}
                  />
                </FormField>
              </div>
            </Card>

            {/* Location */}
            <Card className="settings-section">
              <SectionHeader
                title={t.hotel.settings.sectionLocation}
                description={t.hotel.settings.sectionLocationDesc}
                icon={MapPin}
              />
              <div className="form-grid">
                <FormField label={t.hotel.settings.country} htmlFor="country">
                  <Input
                    id="country"
                    value={s.country}
                    disabled={suspended}
                    onChange={(e) => patch("country", e.target.value)}
                  />
                </FormField>
                <FormField label={t.hotel.settings.city} htmlFor="city">
                  <Input
                    id="city"
                    value={s.city}
                    disabled={suspended}
                    onChange={(e) => patch("city", e.target.value)}
                  />
                </FormField>
                <FormField label={t.hotel.settings.area} htmlFor="area">
                  <Input
                    id="area"
                    value={s.area}
                    disabled={suspended}
                    onChange={(e) => patch("area", e.target.value)}
                  />
                </FormField>
                <FormField label={t.hotel.settings.addressLine} htmlFor="address_line">
                  <Input
                    id="address_line"
                    value={s.address_line}
                    disabled={suspended}
                    onChange={(e) => patch("address_line", e.target.value)}
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.latitude}
                  htmlFor="latitude"
                  hint={t.hotel.settings.mapsFieldsHint}
                >
                  <Input
                    id="latitude"
                    inputMode="decimal"
                    value={s.latitude ?? ""}
                    disabled={suspended}
                    onChange={(e) =>
                      patch("latitude", e.target.value === "" ? null : e.target.value)
                    }
                  />
                </FormField>
                <FormField label={t.hotel.settings.longitude} htmlFor="longitude">
                  <Input
                    id="longitude"
                    inputMode="decimal"
                    value={s.longitude ?? ""}
                    disabled={suspended}
                    onChange={(e) =>
                      patch("longitude", e.target.value === "" ? null : e.target.value)
                    }
                  />
                </FormField>
                <FormField label={t.hotel.settings.mapUrl} htmlFor="map_url">
                  <Input
                    id="map_url"
                    type="url"
                    value={s.map_url}
                    disabled={suspended}
                    onChange={(e) => patch("map_url", e.target.value)}
                  />
                </FormField>
                <FormField label={t.hotel.settings.placeId} htmlFor="google_place_id">
                  <Input
                    id="google_place_id"
                    value={s.google_place_id}
                    disabled={suspended}
                    onChange={(e) => patch("google_place_id", e.target.value)}
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.locationNotes}
                  htmlFor="location_notes"
                  className="form-grid__full"
                >
                  <Input
                    id="location_notes"
                    value={s.location_notes}
                    disabled={suspended}
                    onChange={(e) => patch("location_notes", e.target.value)}
                  />
                </FormField>
              </div>
            </Card>

            {/* Policies */}
            <Card className="settings-section">
              <SectionHeader
                title={t.hotel.settings.sectionPolicies}
                description={t.hotel.settings.sectionPoliciesDesc}
                icon={BedDouble}
              />
              <div className="form-grid">
                <FormField label={t.hotel.settings.checkInTime} htmlFor="check_in_time">
                  <Input
                    id="check_in_time"
                    type="time"
                    value={(s.check_in_time ?? "").slice(0, 5)}
                    disabled={suspended}
                    onChange={(e) =>
                      patch("check_in_time", e.target.value || null)
                    }
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.checkOutTime}
                  htmlFor="check_out_time"
                >
                  <Input
                    id="check_out_time"
                    type="time"
                    value={(s.check_out_time ?? "").slice(0, 5)}
                    disabled={suspended}
                    onChange={(e) =>
                      patch("check_out_time", e.target.value || null)
                    }
                  />
                </FormField>
                <FormField label={t.hotel.settings.petPolicy} htmlFor="pet_policy">
                  <Select
                    id="pet_policy"
                    value={s.pet_policy}
                    options={petOptions}
                    disabled={suspended}
                    onChange={(e) => patch("pet_policy", e.target.value)}
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.smokingPolicy}
                  htmlFor="smoking_policy"
                >
                  <Select
                    id="smoking_policy"
                    value={s.smoking_policy}
                    options={smokingOptions}
                    disabled={suspended}
                    onChange={(e) => patch("smoking_policy", e.target.value)}
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.cancellationPolicy}
                  htmlFor="cancellation_policy"
                  className="form-grid__full"
                >
                  <Textarea
                    id="cancellation_policy"
                    value={s.cancellation_policy}
                    disabled={suspended}
                    onChange={(e) => patch("cancellation_policy", e.target.value)}
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.childPolicy}
                  htmlFor="child_policy"
                  className="form-grid__full"
                >
                  <Textarea
                    id="child_policy"
                    value={s.child_policy}
                    disabled={suspended}
                    onChange={(e) => patch("child_policy", e.target.value)}
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.extraBedPolicy}
                  htmlFor="extra_bed_policy"
                  className="form-grid__full"
                >
                  <Textarea
                    id="extra_bed_policy"
                    value={s.extra_bed_policy}
                    disabled={suspended}
                    onChange={(e) => patch("extra_bed_policy", e.target.value)}
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.importantNotes}
                  htmlFor="important_notes"
                  className="form-grid__full"
                >
                  <Textarea
                    id="important_notes"
                    value={s.important_notes}
                    disabled={suspended}
                    onChange={(e) => patch("important_notes", e.target.value)}
                  />
                </FormField>
              </div>
            </Card>

            {/* Operational defaults */}
            <Card className="settings-section">
              <SectionHeader
                title={t.hotel.settings.sectionDefaults}
                description={t.hotel.settings.sectionDefaultsDesc}
                icon={SlidersHorizontal}
              />
              <p className="field__hint" style={{ marginBottom: "var(--space-4)" }}>
                {t.hotel.settings.defaultsHint}
              </p>
              <div className="stack">
                <Switch
                  id="require_guest_phone"
                  label={t.hotel.settings.requireGuestPhone}
                  checked={s.require_guest_phone}
                  disabled={suspended}
                  onChange={(v) => patch("require_guest_phone", v)}
                />
                <Switch
                  id="require_guest_document"
                  label={t.hotel.settings.requireGuestDocument}
                  checked={s.require_guest_document}
                  disabled={suspended}
                  onChange={(v) => patch("require_guest_document", v)}
                />
                <div>
                  <Switch
                    id="housekeeping_inspection_required"
                    label={t.hotel.settings.hkInspectionRequired}
                    checked={s.housekeeping_inspection_required}
                    disabled={suspended}
                    onChange={(v) => patch("housekeeping_inspection_required", v)}
                  />
                  <p className="field__hint">
                    {t.hotel.settings.hkInspectionRequiredHint}
                  </p>
                </div>
                <div>
                  <Switch
                    id="restaurant_enabled"
                    label={t.hotel.settings.restaurantEnabled}
                    checked={s.restaurant_enabled}
                    disabled={suspended}
                    onChange={(v) => patch("restaurant_enabled", v)}
                  />
                  <p className="field__hint">
                    {t.hotel.settings.restaurantEnabledHint}
                  </p>
                </div>
                <div>
                  <Switch
                    id="cafe_enabled"
                    label={t.hotel.settings.cafeEnabled}
                    checked={s.cafe_enabled}
                    disabled={suspended}
                    onChange={(v) => patch("cafe_enabled", v)}
                  />
                  <p className="field__hint">
                    {t.hotel.settings.cafeEnabledHint}
                  </p>
                </div>
              </div>
            </Card>

            {/* Public website (Phase 15) */}
            <Card className="settings-section">
              <SectionHeader
                title={t.hotel.settings.sectionPublic}
                description={t.hotel.settings.sectionPublicDesc}
                icon={Globe}
              />
              <div className="stack">
                <Switch
                  id="public_is_listed"
                  label={t.hotel.settings.publicListed}
                  checked={s.public_is_listed}
                  disabled={suspended}
                  onChange={(v) => patch("public_is_listed", v)}
                />
                <Switch
                  id="allow_public_booking"
                  label={t.hotel.settings.allowPublicBooking}
                  checked={s.allow_public_booking}
                  disabled={suspended}
                  onChange={(v) => patch("allow_public_booking", v)}
                />
                <Switch
                  id="public_requires_confirmation"
                  label={t.hotel.settings.publicRequiresConfirmation}
                  checked={s.public_booking_requires_confirmation}
                  disabled={suspended}
                  onChange={(v) => patch("public_booking_requires_confirmation", v)}
                />
                <Switch
                  id="public_featured"
                  label={t.hotel.settings.publicFeatured}
                  checked={s.public_featured}
                  disabled={suspended}
                  onChange={(v) => patch("public_featured", v)}
                />
              </div>
              <div className="form-grid" style={{ marginTop: "var(--space-4)" }}>
                <FormField
                  label={t.hotel.settings.publicSlug}
                  htmlFor="public_slug"
                  hint={t.hotel.settings.publicSlugHint}
                >
                  <Input
                    id="public_slug"
                    dir="ltr"
                    value={s.public_slug ?? ""}
                    disabled={suspended}
                    onChange={(e) =>
                      patch("public_slug", e.target.value === "" ? null : e.target.value)
                    }
                  />
                </FormField>
                <FormField label={t.hotel.settings.publicMinNights} htmlFor="public_min_nights">
                  <Input
                    id="public_min_nights"
                    type="number"
                    min="1"
                    value={s.public_min_nights ?? ""}
                    disabled={suspended}
                    onChange={(e) =>
                      patch(
                        "public_min_nights",
                        e.target.value === "" ? null : Number(e.target.value),
                      )
                    }
                  />
                </FormField>
                <FormField label={t.hotel.settings.publicMaxNights} htmlFor="public_max_nights">
                  <Input
                    id="public_max_nights"
                    type="number"
                    min="1"
                    value={s.public_max_nights ?? ""}
                    disabled={suspended}
                    onChange={(e) =>
                      patch(
                        "public_max_nights",
                        e.target.value === "" ? null : Number(e.target.value),
                      )
                    }
                  />
                </FormField>
                <FormField
                  label={t.hotel.settings.publicTerms}
                  htmlFor="public_terms_text"
                  className="form-grid__full"
                  hint={t.hotel.settings.publicTermsHint}
                >
                  <Textarea
                    id="public_terms_text"
                    value={s.public_terms_text}
                    disabled={suspended}
                    onChange={(e) => patch("public_terms_text", e.target.value)}
                  />
                </FormField>
              </div>
            </Card>

            {!suspended ? (
              <div className="cluster">
                <Button type="submit" loading={busy}>
                  {t.hotel.settings.save}
                </Button>
              </div>
            ) : null}
          </form>

          {/* Media is managed separately from the text form. */}
          <HotelMediaSection disabled={suspended} />
        </>
      ) : null}
    </PageContainer>
  );
}
