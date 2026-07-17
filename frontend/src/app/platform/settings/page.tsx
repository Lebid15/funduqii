"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  Globe,
  History,
  LifeBuoy,
  SlidersHorizontal,
  ToggleRight,
} from "lucide-react";

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
  Select,
  Switch,
  useToast,
} from "@/components/ui";
import {
  getPlatformSettingsAudit,
  getSettings,
  updateSettings,
} from "@/lib/api/platform";
import { messageForError } from "@/lib/api/errors";
import type { PlatformSettings, SettingsAuditLog } from "@/lib/api/types";
import { formatDateTime, settingsSectionLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function SettingsPage() {
  const { t } = useI18n();
  const { notify } = useToast();

  const [settings, setSettings] = useState<PlatformSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Await-first: no synchronous setState on the effect tick.
  const load = useCallback(async () => {
    try {
      const data = await getSettings();
      setSettings(data);
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

  function patch<K extends keyof PlatformSettings>(
    key: K,
    value: PlatformSettings[K],
  ) {
    setSettings((current) => (current ? { ...current, [key]: value } : current));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setSaveError(null);
    setBusy(true);
    try {
      const saved = await updateSettings({
        platform_name: settings.platform_name,
        support_email: settings.support_email,
        support_phone: settings.support_phone,
        support_whatsapp: settings.support_whatsapp,
        website_url: settings.website_url,
        default_language: settings.default_language,
        default_currency: settings.default_currency,
        default_trial_days: settings.default_trial_days,
        allow_public_registration: settings.allow_public_registration,
        maintenance_mode: settings.maintenance_mode,
      });
      setSettings(saved);
      notify(t.settings.saved);
    } catch (err) {
      setSaveError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageContainer>
      <PageHeader title={t.settings.title} subtitle={t.settings.subtitle} />

      {loading ? <LoadingState label={t.common.loading} /> : null}

      {!loading && error ? (
        <ErrorState
          title={t.states.errorTitle}
          message={error}
          retryLabel={t.common.retry}
          onRetry={reload}
        />
      ) : null}

      {!loading && !error && settings ? (
        <form className="stack" onSubmit={submit} noValidate>
          {saveError ? <Alert tone="error">{saveError}</Alert> : null}

          <Card className="settings-section">
            <SectionHeader
              title={t.settings.sectionGeneral}
              description={t.settings.descGeneral}
              icon={Globe}
            />
            <div className="form-grid">
              <FormField label={t.settings.platformName} htmlFor="set-name">
                <Input
                  id="set-name"
                  value={settings.platform_name}
                  onChange={(e) => patch("platform_name", e.target.value)}
                />
              </FormField>
              <FormField label={t.settings.websiteUrl} htmlFor="set-web">
                <Input
                  id="set-web"
                  type="url"
                  value={settings.website_url}
                  onChange={(e) => patch("website_url", e.target.value)}
                />
              </FormField>
            </div>
          </Card>

          <Card className="settings-section">
            <SectionHeader
              title={t.settings.sectionSupport}
              description={t.settings.descSupport}
              icon={LifeBuoy}
            />
            <div className="form-grid">
              <FormField label={t.settings.supportEmail} htmlFor="set-email">
                <Input
                  id="set-email"
                  type="email"
                  value={settings.support_email}
                  onChange={(e) => patch("support_email", e.target.value)}
                />
              </FormField>
              <FormField label={t.settings.supportPhone} htmlFor="set-phone">
                <Input
                  id="set-phone"
                  value={settings.support_phone}
                  onChange={(e) => patch("support_phone", e.target.value)}
                />
              </FormField>
              <FormField label={t.settings.supportWhatsapp} htmlFor="set-wa">
                <Input
                  id="set-wa"
                  value={settings.support_whatsapp}
                  onChange={(e) => patch("support_whatsapp", e.target.value)}
                />
              </FormField>
            </div>
          </Card>

          <Card className="settings-section">
            <SectionHeader
              title={t.settings.sectionDefaults}
              description={t.settings.descDefaults}
              icon={SlidersHorizontal}
            />
            <div className="form-grid">
              <FormField label={t.settings.defaultLanguage} htmlFor="set-lang">
                <Select
                  id="set-lang"
                  value={settings.default_language}
                  options={[
                    { value: "ar", label: t.language.ar },
                    { value: "en", label: t.language.en },
                    { value: "tr", label: t.language.tr },
                  ]}
                  onChange={(e) =>
                    patch(
                      "default_language",
                      e.target.value as PlatformSettings["default_language"],
                    )
                  }
                />
              </FormField>
              <FormField label={t.settings.defaultCurrency} htmlFor="set-cur">
                <Input
                  id="set-cur"
                  maxLength={3}
                  value={settings.default_currency}
                  onChange={(e) =>
                    patch("default_currency", e.target.value.toUpperCase())
                  }
                />
              </FormField>
              <FormField label={t.settings.defaultTrialDays} htmlFor="set-trial">
                <Input
                  id="set-trial"
                  type="number"
                  min="0"
                  value={settings.default_trial_days}
                  onChange={(e) =>
                    patch("default_trial_days", Number(e.target.value) || 0)
                  }
                />
              </FormField>
            </div>
          </Card>

          <Card className="settings-section">
            <SectionHeader
              title={t.settings.sectionSwitches}
              description={t.settings.descSwitches}
              icon={ToggleRight}
            />
            <div className="stack">
              <Switch
                id="set-reg"
                label={t.settings.allowPublicRegistration}
                checked={settings.allow_public_registration}
                onChange={(v) => patch("allow_public_registration", v)}
              />
              <Switch
                id="set-maint"
                label={t.settings.maintenanceMode}
                checked={settings.maintenance_mode}
                onChange={(v) => patch("maintenance_mode", v)}
              />
            </div>
          </Card>

          <div className="cluster">
            <Button type="submit" disabled={busy}>
              {busy ? t.common.saving : t.common.save}
            </Button>
          </div>
        </form>
      ) : null}

      {!loading && !error && settings ? <PlatformAuditCard /> : null}
    </PageContainer>
  );
}

function PlatformAuditCard() {
  const { t, locale } = useI18n();
  const [rows, setRows] = useState<SettingsAuditLog[] | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getPlatformSettingsAudit()
      .then((res) => alive && setRows(res.results))
      .catch((err) => alive && setAuditError(messageForError(err, t)));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Card>
      <SectionHeader
        title={t.hotel.settings.sectionAudit}
        description={t.hotel.settings.sectionAuditDesc}
        icon={History}
      />
      {auditError ? <Alert tone="error">{auditError}</Alert> : null}
      {rows === null && !auditError ? (
        <LoadingState label={t.common.loading} />
      ) : rows && rows.length === 0 ? (
        <p className="muted">{t.hotel.settings.noAuditYet}</p>
      ) : (
        <div className="stack">
          {(rows ?? []).map((r) => (
            <div key={r.id} className="detail-item" style={{ alignItems: "flex-start" }}>
              <span className="detail-item__label">
                {settingsSectionLabel(r.section, t)}
                <span className="muted"> · {formatDateTime(r.created_at, locale)}</span>
              </span>
              <span className="detail-item__value">
                {Object.keys(r.changes).length} {t.hotel.settings.auditFieldsChanged}
                {r.actor ? <span className="muted"> · {r.actor}</span> : null}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
