"use client";

import { useEffect, useState, type FormEvent } from "react";

import {
  Alert,
  Button,
  FormField,
  Input,
  LoadingState,
  Modal,
  Select,
  Switch,
} from "@/components/ui";
import { addGuestService, listCatalog } from "@/lib/api/guestServices";
import { messageForError } from "@/lib/api/errors";
import type { GuestExtraService, GuestFolioDirectoryRow } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Post ONE catalog service to a stay's folio. The price/tax PREVIEW is cosmetic —
 * the backend computes the authoritative amount. A VARIABLE service, and only for
 * a caller holding `finance.charge_create`, may override the unit price (with a
 * mandatory reason); otherwise the price is read-only (fixed, or variable without
 * the perm). Submit sends a fresh idempotency_key and the submit button is
 * disabled while pending, so a double-click never posts twice.
 */
export function AddServiceModal({
  stay,
  canCharge,
  onClose,
  onAdded,
}: {
  stay: GuestFolioDirectoryRow | null;
  /** Resolved `finance.charge_create` — enables the variable-price override. */
  canCharge: boolean;
  onClose: () => void;
  onAdded: () => void;
}) {
  const { t, locale } = useI18n();
  const g = t.guestFolio;
  const open = stay !== null;

  const [catalog, setCatalog] = useState<GuestExtraService[]>([]);
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [serviceId, setServiceId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [override, setOverride] = useState(false);
  const [overridePrice, setOverridePrice] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setServiceId("");
    setQuantity("1");
    setOverride(false);
    setOverridePrice("");
    setReason("");
    setError(null);
    setBusy(false);
    setLoadingCatalog(true);
    listCatalog({ is_active: true })
      .then((items) => setCatalog(items))
      .catch(() => setCatalog([]))
      .finally(() => setLoadingCatalog(false));
  }, [open]);

  const selected = catalog.find((item) => String(item.id) === serviceId) ?? null;
  const isVariable = selected?.pricing_mode === "variable";
  const canOverride = Boolean(isVariable && canCharge);

  // Handlers declared AFTER every useState they touch (no setter referenced
  // before its declaration), so the React Compiler's memoization holds.
  function changeService(id: string) {
    setServiceId(id);
    setOverride(false);
    setOverridePrice("");
    setReason("");
    setError(null);
  }

  function toggleOverride(next: boolean) {
    setOverride(next);
    setOverridePrice(next && selected ? selected.unit_price : "");
    if (!next) setReason("");
  }

  const qtyNum = Number(quantity);
  const unitNum = override ? Number(overridePrice) : Number(selected?.unit_price ?? NaN);
  const previewValid =
    selected !== null &&
    Number.isFinite(qtyNum) &&
    qtyNum > 0 &&
    Number.isFinite(unitNum) &&
    unitNum >= 0;
  const taxRateNum = selected ? Number(selected.tax_rate) : 0;
  const subtotal = previewValid ? unitNum * qtyNum : 0;
  const taxAmount = previewValid ? (subtotal * taxRateNum) / 100 : 0;
  const previewTotal = subtotal + taxAmount;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !stay) return;
    if (!serviceId) return setError(g.addModal.serviceRequired);
    if (!Number.isFinite(qtyNum) || qtyNum <= 0)
      return setError(g.addModal.quantityInvalid);
    const useOverride = canOverride && override;
    if (useOverride) {
      const price = Number(overridePrice);
      if (!Number.isFinite(price) || price < 0)
        return setError(g.addModal.priceInvalid);
      if (!reason.trim()) return setError(t.guestFolio.errors.reasonRequired);
    }
    setBusy(true);
    setError(null);
    try {
      await addGuestService(stay.stay_id, {
        service: Number(serviceId),
        quantity,
        ...(useOverride
          ? { unit_price_override: overridePrice, reason: reason.trim() }
          : {}),
        idempotency_key: crypto.randomUUID(),
      });
      onAdded();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const serviceOptions = catalog.map((item) => ({
    value: String(item.id),
    label: item.name,
  }));
  const priceReadOnly = !canOverride || !override;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={g.addModal.title}
      closeLabel={t.common.close}
      preventClose={busy}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button
            form="gf-add-form"
            type="submit"
            loading={busy}
            disabled={busy}
          >
            {g.addModal.submit}
          </Button>
        </>
      }
    >
      {loadingCatalog ? (
        <LoadingState label={t.common.loading} />
      ) : (
        <form id="gf-add-form" className="stack" onSubmit={submit} noValidate>
          {error ? <Alert tone="error">{error}</Alert> : null}
          {stay ? (
            <p className="muted small">
              {g.addModal.forGuest.replace("{guest}", stay.guest_name)}{" "}
              <bdi dir="ltr">{stay.room_number}</bdi>
            </p>
          ) : null}
          {catalog.length === 0 ? (
            <Alert tone="info">{g.addModal.noCatalog}</Alert>
          ) : null}
          <FormField label={g.addModal.service} htmlFor="gf-add-service">
            <Select
              id="gf-add-service"
              value={serviceId}
              placeholder={g.addModal.selectService}
              options={serviceOptions}
              onChange={(e) => changeService(e.target.value)}
            />
          </FormField>
          <div className="form-grid">
            <FormField label={g.addModal.quantity} htmlFor="gf-add-qty">
              <Input
                id="gf-add-qty"
                type="number"
                min="0.01"
                step="0.01"
                inputMode="decimal"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
            </FormField>
            <FormField label={g.addModal.unitPrice} htmlFor="gf-add-price">
              <Input
                id="gf-add-price"
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={override ? overridePrice : (selected?.unit_price ?? "")}
                readOnly={priceReadOnly}
                onChange={(e) => setOverridePrice(e.target.value)}
              />
            </FormField>
          </div>

          {canOverride ? (
            <div className="stack" style={{ gap: "0.5rem" }}>
              <Switch
                id="gf-add-override"
                checked={override}
                onChange={toggleOverride}
                label={g.addModal.overrideLabel}
              />
              {override ? (
                <FormField label={g.addModal.reason} htmlFor="gf-add-reason">
                  <Input
                    id="gf-add-reason"
                    value={reason}
                    placeholder={g.addModal.reasonPlaceholder}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </FormField>
              ) : null}
            </div>
          ) : null}

          {selected ? (
            <div className="stack" style={{ gap: "0.25rem" }} aria-live="polite">
              <span className="field__label">{g.addModal.previewTitle}</span>
              <div className="stay-card__meta">
                <span>
                  {g.addModal.previewTax}:{" "}
                  <bdi dir="ltr">{taxRateNum}%</bdi>
                </span>
                <span>
                  {g.addModal.previewTotal}:{" "}
                  {previewValid ? (
                    formatMoney(previewTotal, selected.currency, locale)
                  ) : (
                    <span className="muted">{t.common.notAvailable}</span>
                  )}
                </span>
              </div>
              <span className="muted small">{g.addModal.previewHint}</span>
            </div>
          ) : null}
        </form>
      )}
    </Modal>
  );
}
