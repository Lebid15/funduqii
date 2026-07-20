"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import {
  Alert,
  Button,
  ErrorState,
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
 * the perm).
 *
 * IDEMPOTENCY (financial safety): the key is minted ONCE per add-attempt session
 * (when the modal opens) and REUSED across every retry, then regenerated after a
 * success. It is deliberately NOT regenerated when the user edits the form,
 * because a stable key is what makes a NETWORK-FAILURE RETRY safe: if the lost
 * request actually committed server-side, replaying the same key either returns
 * the existing posting (identical payload) or fails closed with a 409
 * `idempotency_key_conflict` (edited payload) — never a duplicate charge on a
 * guest's folio. A per-attempt key would defeat the backend protection entirely.
 * The `busy` guard only covers double-clicks, which is the easy half of the
 * problem.
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
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [serviceId, setServiceId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [override, setOverride] = useState(false);
  const [overridePrice, setOverridePrice] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** The add-attempt idempotency key — see the component docstring. */
  const idempotencyKeyRef = useRef("");
  const catalogSeqRef = useRef(0);

  const loadCatalog = useCallback(() => {
    const seq = (catalogSeqRef.current += 1);
    setLoadingCatalog(true);
    setCatalogError(null);
    // Only ACTIVE catalogue entries may be posted to a folio, so the picker asks
    // the server for exactly that set (a deactivated service would be refused
    // server-side anyway — never offer it).
    listCatalog({ is_active: true })
      .then((items) => {
        if (catalogSeqRef.current !== seq) return;
        setCatalog(items);
        setCatalogError(null);
      })
      .catch((err) => {
        if (catalogSeqRef.current !== seq) return;
        // A FAILED fetch must NOT masquerade as "the catalogue is empty" — that
        // is indistinguishable from a genuinely empty catalogue and offers no
        // way back. Surface the real error with a Retry instead.
        setCatalog([]);
        setCatalogError(messageForError(err, t));
      })
      .finally(() => {
        if (catalogSeqRef.current === seq) setLoadingCatalog(false);
      });
  }, [t]);

  useEffect(() => {
    if (!open) return;
    setServiceId("");
    setQuantity("1");
    setOverride(false);
    setOverridePrice("");
    setReason("");
    setError(null);
    setBusy(false);
    // ONE key per add-attempt session; reused by every retry below.
    idempotencyKeyRef.current = crypto.randomUUID();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    loadCatalog();
  }, [open, loadCatalog]);

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
    // Defensive: the open-effect always mints one first, but never post without.
    if (!idempotencyKeyRef.current) idempotencyKeyRef.current = crypto.randomUUID();
    try {
      await addGuestService(stay.stay_id, {
        service: Number(serviceId),
        quantity,
        ...(useOverride
          ? { unit_price_override: overridePrice, reason: reason.trim() }
          : {}),
        // REUSED across retries — a lost response must never become a second
        // charge. Regenerated only on success, just below.
        idempotency_key: idempotencyKeyRef.current,
      });
      // The attempt is settled; the next add starts a genuinely new request.
      idempotencyKeyRef.current = crypto.randomUUID();
      onAdded();
    } catch (err) {
      // NOTE: the key is intentionally left untouched here so the next click is
      // a REPLAY of the same request, not a new one.
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
  // Nothing can be posted while the catalogue is loading, failed, or empty.
  const catalogUnusable =
    loadingCatalog || catalogError !== null || catalog.length === 0;

  // Explain WHY the price cannot be edited, instead of a silently inert field.
  let priceHint: string | undefined;
  if (selected && priceReadOnly) {
    if (!isVariable) priceHint = g.addModal.priceFixedHint;
    else if (!canCharge) priceHint = g.addModal.priceNoPermissionHint;
    else priceHint = g.addModal.priceOverrideOffHint;
  }

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
            disabled={busy || catalogUnusable}
          >
            {g.addModal.submit}
          </Button>
        </>
      }
    >
      {loadingCatalog ? (
        <LoadingState label={t.common.loading} />
      ) : catalogError !== null ? (
        <ErrorState
          title={g.addModal.catalogFailed}
          message={catalogError}
          retryLabel={t.common.retry}
          onRetry={loadCatalog}
        />
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
            <FormField
              label={g.addModal.unitPrice}
              htmlFor="gf-add-price"
              hint={priceHint}
            >
              <Input
                id="gf-add-price"
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={override ? overridePrice : (selected?.unit_price ?? "")}
                readOnly={priceReadOnly}
                // A read-only price reads as a quiet, sunken, non-editable value
                // (the established `.input[readonly]` treatment) rather than an
                // ordinary field that silently swallows typing. Tokens only.
                style={
                  priceReadOnly
                    ? {
                        background: "var(--color-surface-sunken)",
                        cursor: "default",
                      }
                    : undefined
                }
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
