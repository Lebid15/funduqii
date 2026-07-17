"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  BedDouble,
  Building2,
  Globe,
  History,
  Image as ImageIcon,
  Languages,
  MapPin,
  Phone,
  SlidersHorizontal,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
import { HotelMediaSection } from "@/components/hotel/HotelMediaSection";
import {
  Alert,
  Badge,
  Button,
  Card,
  ErrorState,
  FormField,
  IconButton,
  Input,
  LoadingState,
  PageHeader,
  SectionHeader,
  Select,
  Switch,
  Textarea,
  useToast,
} from "@/components/ui";
import {
  getProfile,
  getSettings,
  getSettingsAudit,
  updateSettingsSection,
} from "@/lib/api/hotel";
import { messageForError } from "@/lib/api/errors";
import type {
  HotelSettings,
  SettingsAuditLog,
  SettingsSection,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

// Section -> the exact fields it owns (mirrors the backend HOTEL_SETTINGS_GROUPS).
const SECTION_FIELDS: Record<SettingsSection, (keyof HotelSettings)[]> = {
  identity: [
    "display_name",
    "legal_name",
    "facility_type",
    "star_rating",
    "short_description",
    "description",
  ],
  localization: [
    "default_language",
    "timezone",
    "default_currency",
    "accepted_currencies",
  ],
  contact: [
    "phone",
    "whatsapp_number",
    "email",
    "website_url",
    "facebook_url",
    "instagram_url",
    "social_links",
  ],
  location: [
    "country",
    "city",
    "area",
    "address_line",
    "latitude",
    "longitude",
    "map_url",
    "google_place_id",
    "location_notes",
  ],
  policies: [
    "check_in_time",
    "check_out_time",
    "cancellation_policy",
    "child_policy",
    "pet_policy",
    "smoking_policy",
    "extra_bed_policy",
    "important_notes",
  ],
  operational: [
    "require_guest_phone",
    "require_guest_document",
    "housekeeping_inspection_required",
    "restaurant_enabled",
    "cafe_enabled",
  ],
  public: [
    "public_is_listed",
    "allow_public_booking",
    "public_booking_requires_confirmation",
    "public_featured",
    "public_slug",
    "public_min_nights",
    "public_max_nights",
    "public_terms_text",
    "public_sort_order",
  ],
};

type NavKey = SettingsSection | "media" | "audit";

function pick(obj: HotelSettings, fields: (keyof HotelSettings)[]) {
  const out: Partial<HotelSettings> = {};
  for (const f of fields) out[f] = obj[f] as never;
  return out;
}

export default function HotelSettingsPage() {
  const { t, locale } = useI18n();
  const { notify } = useToast();

  const [settings, setSettings] = useState<HotelSettings | null>(null);
  const [baseline, setBaseline] = useState<HotelSettings | null>(null);
  const [suspended, setSuspended] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savingSection, setSavingSection] = useState<SettingsSection | null>(null);
  const [active, setActive] = useState<NavKey>("identity");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    try {
      const [data, profile] = await Promise.all([getSettings(), getProfile()]);
      setSettings(data);
      setBaseline(data);
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

  const isSectionDirty = useCallback(
    (section: SettingsSection): boolean => {
      if (!settings || !baseline) return false;
      return SECTION_FIELDS[section].some(
        (f) => JSON.stringify(settings[f]) !== JSON.stringify(baseline[f]),
      );
    },
    [settings, baseline],
  );

  const anyDirty = useMemo(
    () => (Object.keys(SECTION_FIELDS) as SettingsSection[]).some(isSectionDirty),
    [isSectionDirty],
  );

  // §9.2 confirm-on-exit-unsaved (browser navigation / tab close).
  useEffect(() => {
    if (!anyDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [anyDirty]);

  function patch<K extends keyof HotelSettings>(key: K, value: HotelSettings[K]) {
    setSettings((s) => (s ? { ...s, [key]: value } : s));
  }

  async function saveSection(section: SettingsSection) {
    if (!settings || suspended) return;
    setSaveError(null);
    setSavingSection(section);
    try {
      const saved = await updateSettingsSection(
        section,
        pick(settings, SECTION_FIELDS[section]),
      );
      // Merge only THIS section's fields — never clobber unsaved edits elsewhere.
      const fields = SECTION_FIELDS[section];
      setSettings((s) => (s ? { ...s, ...pick(saved, fields) } : s));
      setBaseline((b) => (b ? { ...b, ...pick(saved, fields) } : saved));
      notify(t.hotel.settings.saved);
    } catch (err) {
      setSaveError(messageForError(err, t));
    } finally {
      setSavingSection(null);
    }
  }

  const s = settings;

  const NAV: { key: NavKey; label: string; icon: LucideIcon }[] = [
    { key: "identity", label: t.hotel.settings.sectionIdentity, icon: Building2 },
    { key: "localization", label: t.hotel.settings.sectionLocalization, icon: Languages },
    { key: "contact", label: t.hotel.settings.sectionContact, icon: Phone },
    { key: "location", label: t.hotel.settings.sectionLocation, icon: MapPin },
    { key: "policies", label: t.hotel.settings.sectionPolicies, icon: BedDouble },
    { key: "operational", label: t.hotel.settings.sectionDefaults, icon: SlidersHorizontal },
    { key: "public", label: t.hotel.settings.sectionPublic, icon: Globe },
    { key: "media", label: t.hotel.settings.sectionMedia, icon: ImageIcon },
    { key: "audit", label: t.hotel.settings.sectionAudit, icon: History },
  ];

  const term = search.trim().toLowerCase();
  const visibleNav = term
    ? NAV.filter((n) => n.label.toLowerCase().includes(term))
    : NAV;

  return (
    <PageContainer>
      <PageHeader
        title={t.hotel.settings.title}
        subtitle={t.hotel.settings.subtitle}
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
        <>
          {suspended ? (
            <Alert tone="error">{t.hotel.settings.readOnlySuspended}</Alert>
          ) : null}

          <div className="settings-shell">
            {/* §9.2 side navigation + in-settings search */}
            <nav className="settings-shell__nav" aria-label={t.hotel.settings.title}>
              <Input
                type="search"
                value={search}
                placeholder={t.hotel.settings.searchPlaceholder}
                onChange={(e) => setSearch(e.target.value)}
                aria-label={t.hotel.settings.searchPlaceholder}
              />
              <ul className="settings-nav" role="list">
                {visibleNav.map((n) => {
                  const dirty =
                    n.key !== "media" &&
                    n.key !== "audit" &&
                    isSectionDirty(n.key as SettingsSection);
                  return (
                    <li key={n.key}>
                      <button
                        type="button"
                        className="settings-nav__item"
                        aria-current={active === n.key ? "page" : undefined}
                        data-active={active === n.key}
                        onClick={() => setActive(n.key)}
                      >
                        <n.icon size={16} aria-hidden />
                        <span>{n.label}</span>
                        {dirty ? (
                          <span
                            className="settings-nav__dot"
                            title={t.hotel.settings.unsavedChanges}
                            aria-label={t.hotel.settings.unsavedChanges}
                          />
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </nav>

            <div className="settings-shell__panel">
              {saveError ? <Alert tone="error">{saveError}</Alert> : null}
              {term && visibleNav.length === 0 ? (
                <Card>
                  <p className="muted">{t.hotel.settings.noSearchResults}</p>
                </Card>
              ) : active === "media" ? (
                <HotelMediaSection disabled={suspended} />
              ) : active === "audit" ? (
                <AuditPanel />
              ) : (
                <SectionCard
                  section={active}
                  s={s}
                  patch={patch}
                  suspended={suspended}
                  dirty={isSectionDirty(active)}
                  saving={savingSection === active}
                  onSave={() => saveSection(active)}
                >
                  <SectionFields
                    section={active}
                    s={s}
                    patch={patch}
                    suspended={suspended}
                  />
                </SectionCard>
              )}
            </div>
          </div>
        </>
      ) : null}
    </PageContainer>
  );

  // --- audit panel (kept inside for i18n/locale closure) --------------------
  function AuditPanel() {
    const [rows, setRows] = useState<SettingsAuditLog[] | null>(null);
    const [auditError, setAuditError] = useState<string | null>(null);

    useEffect(() => {
      let alive = true;
      getSettingsAudit()
        .then((res) => alive && setRows(res.results))
        .catch((err) => alive && setAuditError(messageForError(err, t)));
      return () => {
        alive = false;
      };
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
                  {r.section}
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
}

// --- section wrapper card (title + per-section save) ------------------------
function SectionCard({
  section,
  s,
  patch,
  suspended,
  dirty,
  saving,
  onSave,
  children,
}: {
  section: SettingsSection;
  s: HotelSettings;
  patch: <K extends keyof HotelSettings>(k: K, v: HotelSettings[K]) => void;
  suspended: boolean;
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  children: ReactNode;
}) {
  void s;
  void patch;
  const { t } = useI18n();
  const meta: Record<SettingsSection, { title: string; desc: string }> = {
    identity: { title: t.hotel.settings.sectionIdentity, desc: t.hotel.settings.sectionIdentityDesc },
    localization: { title: t.hotel.settings.sectionLocalization, desc: t.hotel.settings.sectionLocalizationDesc },
    contact: { title: t.hotel.settings.sectionContact, desc: t.hotel.settings.sectionContactDesc },
    location: { title: t.hotel.settings.sectionLocation, desc: t.hotel.settings.sectionLocationDesc },
    policies: { title: t.hotel.settings.sectionPolicies, desc: t.hotel.settings.sectionPoliciesDesc },
    operational: { title: t.hotel.settings.sectionDefaults, desc: t.hotel.settings.sectionDefaultsDesc },
    public: { title: t.hotel.settings.sectionPublic, desc: t.hotel.settings.sectionPublicDesc },
  };
  return (
    <Card className="settings-section">
      <div className="cluster" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <SectionHeader title={meta[section].title} description={meta[section].desc} />
        {dirty ? <Badge tone="warning">{t.hotel.settings.unsavedChanges}</Badge> : null}
      </div>
      <div style={{ marginTop: "var(--space-4)" }}>{children}</div>
      {!suspended ? (
        <div className="cluster" style={{ marginTop: "var(--space-4)" }}>
          <Button onClick={onSave} loading={saving} disabled={!dirty}>
            {t.hotel.settings.saveSection}
          </Button>
        </div>
      ) : null}
    </Card>
  );
}

// --- accepted-currencies chip editor ---------------------------------------
function AcceptedCurrenciesEditor({
  value,
  disabled,
  onChange,
}: {
  value: string[];
  disabled: boolean;
  onChange: (next: string[]) => void;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState("");
  function add() {
    const code = draft.trim().toUpperCase();
    if (/^[A-Z]{3}$/.test(code) && !value.includes(code)) {
      onChange([...value, code]);
    }
    setDraft("");
  }
  return (
    <div className="stack" style={{ gap: "var(--space-2)" }}>
      <div className="cluster" style={{ flexWrap: "wrap", gap: "var(--space-2)" }}>
        {value.map((code) => (
          <Badge key={code} tone="neutral">
            {code}
            {!disabled ? (
              <button
                type="button"
                className="chip__remove"
                aria-label={`${code} ✕`}
                onClick={() => onChange(value.filter((c) => c !== code))}
                style={{ marginInlineStart: "0.25rem", cursor: "pointer" }}
              >
                ✕
              </button>
            ) : null}
          </Badge>
        ))}
      </div>
      {!disabled ? (
        <div className="cluster" style={{ gap: "var(--space-2)" }}>
          <Input
            value={draft}
            maxLength={3}
            dir="ltr"
            placeholder={t.hotel.settings.currencyPlaceholder}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
          <Button variant="secondary" onClick={add} disabled={draft.trim().length !== 3}>
            {t.hotel.settings.addCurrency}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

// --- social-links label→url editor -----------------------------------------
function SocialLinksEditor({
  value,
  disabled,
  onChange,
}: {
  value: Record<string, string>;
  disabled: boolean;
  onChange: (next: Record<string, string>) => void;
}) {
  const entries = Object.entries(value ?? {});
  function update(oldKey: string, key: string, url: string) {
    const next: Record<string, string> = {};
    for (const [k, v] of Object.entries(value ?? {})) {
      if (k === oldKey) {
        if (key.trim()) next[key.trim()] = url;
      } else {
        next[k] = v;
      }
    }
    onChange(next);
  }
  return (
    <div className="stack" style={{ gap: "var(--space-2)" }}>
      {entries.map(([k, v]) => (
        <div key={k} className="cluster" style={{ gap: "var(--space-2)" }}>
          <Input value={k} disabled={disabled} onChange={(e) => update(k, e.target.value, v)} />
          <Input
            dir="ltr"
            value={v}
            disabled={disabled}
            onChange={(e) => update(k, k, e.target.value)}
          />
          {!disabled ? (
            <IconButton
              icon={X}
              label="✕"
              onClick={() => {
                const next = { ...value };
                delete next[k];
                onChange(next);
              }}
            />
          ) : null}
        </div>
      ))}
      {!disabled ? (
        <Button
          variant="secondary"
          onClick={() => onChange({ ...(value ?? {}), "": "" })}
          disabled={Object.prototype.hasOwnProperty.call(value ?? {}, "")}
        >
          +
        </Button>
      ) : null}
    </div>
  );
}

// --- per-section field renderers -------------------------------------------
function SectionFields({
  section,
  s,
  patch,
  suspended,
}: {
  section: SettingsSection;
  s: HotelSettings;
  patch: <K extends keyof HotelSettings>(k: K, v: HotelSettings[K]) => void;
  suspended: boolean;
}) {
  const { t } = useI18n();
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
  const facilityOptions = [
    { value: "hotel", label: t.hotel.settings.facilityTypeHotel },
    { value: "apartments", label: t.hotel.settings.facilityTypeApartments },
    { value: "resort", label: t.hotel.settings.facilityTypeResort },
    { value: "motel", label: t.hotel.settings.facilityTypeMotel },
    { value: "guesthouse", label: t.hotel.settings.facilityTypeGuesthouse },
    { value: "other", label: t.hotel.settings.facilityTypeOther },
  ];

  const text = (
    key: keyof HotelSettings,
    label: string,
    opts: { full?: boolean; hint?: string; type?: string; dir?: "ltr" } = {},
  ) => (
    <FormField
      label={label}
      htmlFor={String(key)}
      hint={opts.hint}
      className={opts.full ? "form-grid__full" : undefined}
    >
      <Input
        id={String(key)}
        type={opts.type}
        dir={opts.dir}
        value={(s[key] as string | null) ?? ""}
        disabled={suspended}
        onChange={(e) => patch(key, e.target.value as never)}
      />
    </FormField>
  );

  const area = (key: keyof HotelSettings, label: string, hint?: string) => (
    <FormField label={label} htmlFor={String(key)} className="form-grid__full" hint={hint}>
      <Textarea
        id={String(key)}
        value={(s[key] as string) ?? ""}
        disabled={suspended}
        onChange={(e) => patch(key, e.target.value as never)}
      />
    </FormField>
  );

  const numberField = (key: keyof HotelSettings, label: string, min = "1") => (
    <FormField label={label} htmlFor={String(key)}>
      <Input
        id={String(key)}
        type="number"
        min={min}
        value={(s[key] as number | null) ?? ""}
        disabled={suspended}
        onChange={(e) =>
          patch(key, (e.target.value === "" ? null : Number(e.target.value)) as never)
        }
      />
    </FormField>
  );

  const toggle = (key: keyof HotelSettings, label: string, hint?: string) => (
    <div>
      <Switch
        id={String(key)}
        label={label}
        checked={Boolean(s[key])}
        disabled={suspended}
        onChange={(v) => patch(key, v as never)}
      />
      {hint ? <p className="field__hint">{hint}</p> : null}
    </div>
  );

  switch (section) {
    case "identity":
      return (
        <div className="form-grid">
          {text("display_name", t.hotel.settings.displayName)}
          {text("legal_name", t.hotel.settings.legalName)}
          <FormField label={t.hotel.settings.facilityType} htmlFor="facility_type">
            <Select
              id="facility_type"
              value={s.facility_type}
              options={facilityOptions}
              disabled={suspended}
              onChange={(e) => patch("facility_type", e.target.value as never)}
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
                patch("star_rating", e.target.value === "" ? null : Number(e.target.value))
              }
            />
          </FormField>
          {text("short_description", t.hotel.settings.shortDescription, { full: true })}
          {area("description", t.hotel.settings.description)}
        </div>
      );
    case "localization":
      return (
        <div className="form-grid">
          <FormField label={t.hotel.settings.defaultLanguage} htmlFor="default_language">
            <Select
              id="default_language"
              value={s.default_language}
              options={langOptions}
              disabled={suspended}
              onChange={(e) =>
                patch("default_language", e.target.value as HotelSettings["default_language"])
              }
            />
          </FormField>
          {text("timezone", t.hotel.settings.timezone)}
          <FormField label={t.hotel.settings.defaultCurrency} htmlFor="default_currency">
            <Input
              id="default_currency"
              maxLength={3}
              dir="ltr"
              value={s.default_currency}
              disabled={suspended}
              onChange={(e) => patch("default_currency", e.target.value.toUpperCase())}
            />
          </FormField>
          <FormField
            label={t.hotel.settings.acceptedCurrencies}
            htmlFor="accepted_currencies"
            className="form-grid__full"
            hint={t.hotel.settings.acceptedCurrenciesHint}
          >
            <AcceptedCurrenciesEditor
              value={s.accepted_currencies}
              disabled={suspended}
              onChange={(next) => patch("accepted_currencies", next)}
            />
          </FormField>
        </div>
      );
    case "contact":
      return (
        <div className="form-grid">
          {text("phone", t.hotel.settings.phone)}
          {text("whatsapp_number", t.hotel.settings.whatsapp)}
          {text("email", t.hotel.settings.email, { type: "email" })}
          {text("website_url", t.hotel.settings.website, { type: "url", dir: "ltr" })}
          {text("facebook_url", t.hotel.settings.facebook, { type: "url", dir: "ltr" })}
          {text("instagram_url", t.hotel.settings.instagram, { type: "url", dir: "ltr" })}
          <FormField
            label={t.hotel.settings.socialLinks}
            htmlFor="social_links"
            className="form-grid__full"
            hint={t.hotel.settings.socialLinksHint}
          >
            <SocialLinksEditor
              value={s.social_links}
              disabled={suspended}
              onChange={(next) => patch("social_links", next)}
            />
          </FormField>
        </div>
      );
    case "location":
      return (
        <div className="form-grid">
          {text("country", t.hotel.settings.country)}
          {text("city", t.hotel.settings.city)}
          {text("area", t.hotel.settings.area)}
          {text("address_line", t.hotel.settings.addressLine)}
          <FormField label={t.hotel.settings.latitude} htmlFor="latitude" hint={t.hotel.settings.mapsFieldsHint}>
            <Input
              id="latitude"
              inputMode="decimal"
              value={s.latitude ?? ""}
              disabled={suspended}
              onChange={(e) => patch("latitude", e.target.value === "" ? null : e.target.value)}
            />
          </FormField>
          <FormField label={t.hotel.settings.longitude} htmlFor="longitude">
            <Input
              id="longitude"
              inputMode="decimal"
              value={s.longitude ?? ""}
              disabled={suspended}
              onChange={(e) => patch("longitude", e.target.value === "" ? null : e.target.value)}
            />
          </FormField>
          {text("map_url", t.hotel.settings.mapUrl, { type: "url", dir: "ltr" })}
          {text("google_place_id", t.hotel.settings.placeId)}
          {text("location_notes", t.hotel.settings.locationNotes, { full: true })}
        </div>
      );
    case "policies":
      return (
        <div className="form-grid">
          <FormField label={t.hotel.settings.checkInTime} htmlFor="check_in_time">
            <Input
              id="check_in_time"
              type="time"
              value={(s.check_in_time ?? "").slice(0, 5)}
              disabled={suspended}
              onChange={(e) => patch("check_in_time", e.target.value || null)}
            />
          </FormField>
          <FormField label={t.hotel.settings.checkOutTime} htmlFor="check_out_time">
            <Input
              id="check_out_time"
              type="time"
              value={(s.check_out_time ?? "").slice(0, 5)}
              disabled={suspended}
              onChange={(e) => patch("check_out_time", e.target.value || null)}
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
          <FormField label={t.hotel.settings.smokingPolicy} htmlFor="smoking_policy">
            <Select
              id="smoking_policy"
              value={s.smoking_policy}
              options={smokingOptions}
              disabled={suspended}
              onChange={(e) => patch("smoking_policy", e.target.value)}
            />
          </FormField>
          {area("cancellation_policy", t.hotel.settings.cancellationPolicy)}
          {area("child_policy", t.hotel.settings.childPolicy)}
          {area("extra_bed_policy", t.hotel.settings.extraBedPolicy)}
          {area("important_notes", t.hotel.settings.importantNotes)}
        </div>
      );
    case "operational":
      return (
        <div className="stack">
          {toggle("require_guest_phone", t.hotel.settings.requireGuestPhone)}
          {toggle("require_guest_document", t.hotel.settings.requireGuestDocument)}
          {toggle(
            "housekeeping_inspection_required",
            t.hotel.settings.hkInspectionRequired,
            t.hotel.settings.hkInspectionRequiredHint,
          )}
          {toggle("restaurant_enabled", t.hotel.settings.restaurantEnabled, t.hotel.settings.restaurantEnabledHint)}
          {toggle("cafe_enabled", t.hotel.settings.cafeEnabled, t.hotel.settings.cafeEnabledHint)}
        </div>
      );
    case "public":
      return (
        <>
          <div className="stack">
            {toggle("public_is_listed", t.hotel.settings.publicListed)}
            {toggle("allow_public_booking", t.hotel.settings.allowPublicBooking)}
            {toggle("public_booking_requires_confirmation", t.hotel.settings.publicRequiresConfirmation)}
            {toggle("public_featured", t.hotel.settings.publicFeatured)}
          </div>
          <div className="form-grid" style={{ marginTop: "var(--space-4)" }}>
            <FormField label={t.hotel.settings.publicSlug} htmlFor="public_slug" hint={t.hotel.settings.publicSlugHint}>
              <Input
                id="public_slug"
                dir="ltr"
                value={s.public_slug ?? ""}
                disabled={suspended}
                onChange={(e) => patch("public_slug", e.target.value === "" ? null : e.target.value)}
              />
            </FormField>
            {numberField("public_min_nights", t.hotel.settings.publicMinNights)}
            {numberField("public_max_nights", t.hotel.settings.publicMaxNights)}
            {area("public_terms_text", t.hotel.settings.publicTerms, t.hotel.settings.publicTermsHint)}
          </div>
        </>
      );
    default:
      return null;
  }
}
