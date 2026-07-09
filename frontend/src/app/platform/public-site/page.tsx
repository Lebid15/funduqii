"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Globe, Link2, MessageSquareQuote, PanelTop, Phone } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
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
  Switch,
  Textarea,
} from "@/components/ui";
import { useToast } from "@/components/ui";
import {
  getPublicSiteSettings,
  updatePublicSiteSettings,
} from "@/lib/api/platform";
import { messageForError } from "@/lib/api/errors";
import type { I18nText, PlatformPublicSettings } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Phase 16 — the platform owner's admin controls for the PUBLIC website:
 * header links/buttons (visibility + per-locale label overrides), hero texts,
 * platform contact info and the footer. Deliberately NOT a CMS.
 */
export default function PublicSitePage() {
  const { t } = useI18n();
  const { notify } = useToast();

  const [settings, setSettings] = useState<PlatformPublicSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setSettings(await getPublicSiteSettings());
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

  function patch<K extends keyof PlatformPublicSettings>(
    key: K,
    value: PlatformPublicSettings[K],
  ) {
    setSettings((current) => (current ? { ...current, [key]: value } : current));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setSaveError(null);
    setBusy(true);
    try {
      const { updated_at, ...editable } = settings;
      void updated_at;
      setSettings(await updatePublicSiteSettings(editable));
      notify(t.publicSiteAdmin.saved);
    } catch (err) {
      setSaveError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const s = settings;

  return (
    <PageContainer>
      <PageHeader
        title={t.publicSiteAdmin.title}
        subtitle={t.publicSiteAdmin.subtitle}
        actions={
          s ? (
            <Button form="public-site-form" type="submit" loading={busy}>
              {t.common.save}
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
          onRetry={() => {
            setLoading(true);
            load();
          }}
        />
      ) : null}

      {!loading && !error && s ? (
        <form id="public-site-form" className="stack" onSubmit={submit} noValidate>
          {saveError ? <Alert tone="error">{saveError}</Alert> : null}

          {/* Header links & buttons */}
          <Card className="settings-section">
            <SectionHeader
              title={t.publicSiteAdmin.sectionHeader}
              description={t.publicSiteAdmin.sectionHeaderDesc}
              icon={PanelTop}
            />
            <div className="stack">
              <Switch
                id="show-home"
                label={t.publicSiteAdmin.showHome}
                checked={s.show_home_link}
                onChange={(v) => patch("show_home_link", v)}
              />
              <Switch
                id="show-hotels"
                label={t.publicSiteAdmin.showHotels}
                checked={s.show_hotels_link}
                onChange={(v) => patch("show_hotels_link", v)}
              />
              <Switch
                id="show-contact"
                label={t.publicSiteAdmin.showContact}
                checked={s.show_contact_link}
                onChange={(v) => patch("show_contact_link", v)}
              />
              <Switch
                id="show-book-now"
                label={t.publicSiteAdmin.showBookNow}
                checked={s.show_book_now_button}
                onChange={(v) => patch("show_book_now_button", v)}
              />
              <Switch
                id="show-trial"
                label={t.publicSiteAdmin.showTrial}
                checked={s.show_trial_button}
                onChange={(v) => patch("show_trial_button", v)}
              />
            </div>
            <I18nField
              id="label-home"
              label={t.publicSiteAdmin.homeLabel}
              value={s.header_home_label}
              onChange={(v) => patch("header_home_label", v)}
            />
            <I18nField
              id="label-hotels"
              label={t.publicSiteAdmin.hotelsLabel}
              value={s.header_hotels_label}
              onChange={(v) => patch("header_hotels_label", v)}
            />
            <I18nField
              id="label-contact"
              label={t.publicSiteAdmin.contactLabel}
              value={s.header_contact_label}
              onChange={(v) => patch("header_contact_label", v)}
            />
            <I18nField
              id="label-book-now"
              label={t.publicSiteAdmin.bookNowLabel}
              value={s.header_book_now_label}
              onChange={(v) => patch("header_book_now_label", v)}
            />
            <I18nField
              id="label-trial"
              label={t.publicSiteAdmin.trialLabel}
              value={s.header_trial_label}
              onChange={(v) => patch("header_trial_label", v)}
            />
          </Card>

          {/* Hero */}
          <Card className="settings-section">
            <SectionHeader
              title={t.publicSiteAdmin.sectionHero}
              description={t.publicSiteAdmin.sectionHeroDesc}
              icon={MessageSquareQuote}
            />
            <I18nField
              id="hero-title"
              label={t.publicSiteAdmin.heroTitle}
              value={s.hero_title}
              onChange={(v) => patch("hero_title", v)}
            />
            <I18nField
              id="hero-subtitle"
              label={t.publicSiteAdmin.heroSubtitle}
              value={s.hero_subtitle}
              onChange={(v) => patch("hero_subtitle", v)}
            />
            <I18nField
              id="hero-primary-label"
              label={t.publicSiteAdmin.heroPrimaryLabel}
              value={s.hero_primary_button_label}
              onChange={(v) => patch("hero_primary_button_label", v)}
            />
            <div className="form-grid">
              <FormField
                label={t.publicSiteAdmin.heroPrimaryUrl}
                htmlFor="hero-primary-url"
                hint={t.publicSiteAdmin.urlHint}
              >
                <Input
                  id="hero-primary-url"
                  dir="ltr"
                  value={s.hero_primary_button_url}
                  onChange={(e) => patch("hero_primary_button_url", e.target.value)}
                />
              </FormField>
              <FormField
                label={t.publicSiteAdmin.heroSecondaryUrl}
                htmlFor="hero-secondary-url"
                hint={t.publicSiteAdmin.urlHint}
              >
                <Input
                  id="hero-secondary-url"
                  dir="ltr"
                  value={s.hero_secondary_button_url}
                  onChange={(e) =>
                    patch("hero_secondary_button_url", e.target.value)
                  }
                />
              </FormField>
            </div>
            <I18nField
              id="hero-secondary-label"
              label={t.publicSiteAdmin.heroSecondaryLabel}
              value={s.hero_secondary_button_label}
              onChange={(v) => patch("hero_secondary_button_label", v)}
            />
          </Card>

          {/* Contact */}
          <Card className="settings-section">
            <SectionHeader
              title={t.publicSiteAdmin.sectionContact}
              description={t.publicSiteAdmin.sectionContactDesc}
              icon={Phone}
            />
            <div className="form-grid">
              <FormField label={t.publicSiteAdmin.phone} htmlFor="ps-phone">
                <Input
                  id="ps-phone"
                  dir="ltr"
                  value={s.public_phone}
                  onChange={(e) => patch("public_phone", e.target.value)}
                />
              </FormField>
              <FormField label={t.publicSiteAdmin.whatsapp} htmlFor="ps-whatsapp">
                <Input
                  id="ps-whatsapp"
                  dir="ltr"
                  value={s.public_whatsapp_display}
                  onChange={(e) => patch("public_whatsapp_display", e.target.value)}
                />
              </FormField>
              <FormField label={t.publicSiteAdmin.email} htmlFor="ps-email">
                <Input
                  id="ps-email"
                  type="email"
                  dir="ltr"
                  value={s.public_email}
                  onChange={(e) => patch("public_email", e.target.value)}
                />
              </FormField>
              <FormField label={t.publicSiteAdmin.address} htmlFor="ps-address">
                <Input
                  id="ps-address"
                  value={s.public_address}
                  onChange={(e) => patch("public_address", e.target.value)}
                />
              </FormField>
              <FormField label={t.publicSiteAdmin.facebook} htmlFor="ps-facebook">
                <Input
                  id="ps-facebook"
                  type="url"
                  dir="ltr"
                  value={s.facebook_url}
                  onChange={(e) => patch("facebook_url", e.target.value)}
                />
              </FormField>
              <FormField label={t.publicSiteAdmin.instagram} htmlFor="ps-instagram">
                <Input
                  id="ps-instagram"
                  type="url"
                  dir="ltr"
                  value={s.instagram_url}
                  onChange={(e) => patch("instagram_url", e.target.value)}
                />
              </FormField>
              <FormField label={t.publicSiteAdmin.website} htmlFor="ps-website">
                <Input
                  id="ps-website"
                  type="url"
                  dir="ltr"
                  value={s.website_url}
                  onChange={(e) => patch("website_url", e.target.value)}
                />
              </FormField>
            </div>
          </Card>

          {/* Footer */}
          <Card className="settings-section">
            <SectionHeader
              title={t.publicSiteAdmin.sectionFooter}
              description={t.publicSiteAdmin.sectionFooterDesc}
              icon={Link2}
            />
            <I18nField
              id="footer-text"
              label={t.publicSiteAdmin.footerText}
              value={s.footer_text}
              onChange={(v) => patch("footer_text", v)}
              textarea
            />
          </Card>

          <div className="cluster">
            <Button type="submit" loading={busy} icon={Globe}>
              {t.common.save}
            </Button>
          </div>
        </form>
      ) : null}
    </PageContainer>
  );
}

/** One translatable override: three inputs (ar/en/tr). Empty = use the
 * built-in dictionary translation on the public site. */
function I18nField({
  id,
  label,
  value,
  onChange,
  textarea = false,
}: {
  id: string;
  label: string;
  value: I18nText;
  onChange: (value: I18nText) => void;
  textarea?: boolean;
}) {
  const { t } = useI18n();
  const locales: (keyof I18nText)[] = ["ar", "en", "tr"];
  return (
    <div className="form-grid" role="group" aria-label={label}>
      {locales.map((locale) => {
        const fieldId = `${id}-${locale}`;
        const fieldLabel = `${label} (${t.language[locale]})`;
        return (
          <FormField
            key={locale}
            label={fieldLabel}
            htmlFor={fieldId}
            hint={t.publicSiteAdmin.overrideHint}
          >
            {textarea ? (
              <Textarea
                id={fieldId}
                value={value[locale]}
                dir={locale === "ar" ? "rtl" : "ltr"}
                onChange={(e) => onChange({ ...value, [locale]: e.target.value })}
              />
            ) : (
              <Input
                id={fieldId}
                value={value[locale]}
                dir={locale === "ar" ? "rtl" : "ltr"}
                onChange={(e) => onChange({ ...value, [locale]: e.target.value })}
              />
            )}
          </FormField>
        );
      })}
    </div>
  );
}
