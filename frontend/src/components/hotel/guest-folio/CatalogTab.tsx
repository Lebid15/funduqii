"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Check, Pencil, Plus, Power, PowerOff, XCircle } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  Modal,
  SectionHeader,
  Select,
  Textarea,
  useToast,
  type Column,
} from "@/components/ui";
import {
  activateCatalogItem,
  createCatalogItem,
  deactivateCatalogItem,
  listCatalog,
  updateCatalogItem,
  type CatalogBody,
} from "@/lib/api/guestServices";
import { isApiError, messageForError } from "@/lib/api/errors";
import type { GuestExtraService } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

import {
  GUEST_SERVICE_CATEGORIES,
  GUEST_SERVICE_PRICING_MODES,
  useCan,
} from "./shared";

const CURRENCY_RE = /^[A-Za-z]{3}$/;

export function CatalogTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();
  const g = t.guestFolio;
  const c = g.catalog;
  const can = useCan();

  const canCreate = can("services.create");
  const canUpdate = can("services.update");
  const canToggle = can("services.delete");
  const canManage = canUpdate || canToggle;

  const [items, setItems] = useState<GuestExtraService[]>([]);
  const [activeFilter, setActiveFilter] = useState<"" | "active" | "inactive">(
    "",
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  // null = closed; { item: null } = create; { item } = edit.
  const [form, setForm] = useState<{ item: GuestExtraService | null } | null>(
    null,
  );

  const loadedOnceRef = useRef(false);
  const seqRef = useRef(0);

  const load = useCallback(async () => {
    const seq = (seqRef.current += 1);
    setLoading(true);
    setError(null);
    try {
      const params =
        activeFilter === "active"
          ? { is_active: true }
          : activeFilter === "inactive"
            ? { is_active: false }
            : undefined;
      const rows = await listCatalog(params);
      if (seqRef.current !== seq) return;
      setItems(rows);
      loadedOnceRef.current = true;
      setHasLoadedOnce(true);
    } catch (err) {
      if (seqRef.current !== seq) return;
      const message = messageForError(err, t);
      if (loadedOnceRef.current) notify(message, "error");
      else setError(message);
    } finally {
      if (seqRef.current === seq) setLoading(false);
    }
  }, [activeFilter, t, notify]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(
    id: number,
    action: () => Promise<unknown>,
    msg: string,
  ) {
    setBusyId(id);
    try {
      await action();
      notify(msg);
      await load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    } finally {
      setBusyId(null);
    }
  }

  const columns: Column<GuestExtraService>[] = [
    { key: "name", header: c.fields.name, render: (item) => <bdi>{item.name}</bdi> },
    {
      key: "category",
      header: c.fields.category,
      render: (item) => c.categories[item.category],
    },
    {
      key: "unit_price",
      header: c.fields.unitPrice,
      align: "end",
      render: (item) => (
        <bdi dir="ltr">{formatMoney(item.unit_price, item.currency, locale)}</bdi>
      ),
    },
    {
      key: "tax_rate",
      header: c.fields.taxRate,
      align: "end",
      render: (item) => <bdi dir="ltr">{Number(item.tax_rate)}%</bdi>,
    },
    {
      key: "pricing_mode",
      header: c.fields.pricingMode,
      render: (item) => c.pricingModes[item.pricing_mode],
    },
    {
      key: "display_order",
      header: c.fields.displayOrder,
      align: "end",
      render: (item) => <bdi dir="ltr">{item.display_order}</bdi>,
    },
    {
      key: "is_active",
      header: c.fields.status,
      render: (item) => (
        <Badge
          tone={item.is_active ? "success" : "neutral"}
          icon={item.is_active ? Check : XCircle}
        >
          {item.is_active ? c.statusActive : c.statusInactive}
        </Badge>
      ),
    },
  ];

  // A mutation reloads the WHOLE list, so letting a sibling row stay clickable
  // mid-flight invites a second write against data that is about to be replaced.
  // `busyId` marks WHICH row is spinning; `mutating` locks every row.
  const mutating = busyId !== null;

  if (canManage) {
    columns.push({
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (item) => (
        <div className="cluster" style={{ gap: "0.35rem", justifyContent: "flex-end" }}>
          {canUpdate ? (
            <Button
              size="sm"
              variant="secondary"
              icon={Pencil}
              disabled={mutating}
              onClick={() => setForm({ item })}
            >
              {t.common.edit}
            </Button>
          ) : null}
          {canToggle && item.is_active ? (
            <Button
              size="sm"
              variant="dangerSoft"
              icon={PowerOff}
              loading={busyId === item.id}
              disabled={mutating}
              onClick={() =>
                run(item.id, () => deactivateCatalogItem(item.id), c.deactivated)
              }
            >
              {c.deactivate}
            </Button>
          ) : null}
          {canToggle && !item.is_active ? (
            <Button
              size="sm"
              variant="secondary"
              icon={Power}
              loading={busyId === item.id}
              disabled={mutating}
              onClick={() =>
                run(item.id, () => activateCatalogItem(item.id), c.activated)
              }
            >
              {c.activate}
            </Button>
          ) : null}
        </div>
      ),
    });
  }

  const filterOptions = [
    { value: "active", label: c.filterActive },
    { value: "inactive", label: c.filterInactive },
  ];
  const backgroundRefreshing = loading && hasLoadedOnce;

  return (
    <>
      <Card>
        <SectionHeader
          title={c.title}
          description={c.subtitle}
          actions={
            canCreate ? (
              <Button
                icon={Plus}
                disabled={mutating}
                onClick={() => setForm({ item: null })}
              >
                {c.create}
              </Button>
            ) : null
          }
        />
        <FilterBar>
          <FormField label={t.common.status} htmlFor="gf-cat-filter">
            <Select
              id="gf-cat-filter"
              value={activeFilter}
              placeholder={t.common.all}
              options={filterOptions}
              onChange={(e) =>
                setActiveFilter(e.target.value as "" | "active" | "inactive")
              }
            />
          </FormField>
        </FilterBar>

        {/* Changing the status filter refetches; without this the table simply
            froze with stale rows and no signal (FolioDirectoryTab already had
            it). Keeps the rows MOUNTED — a11y-safe background refresh. */}
        <div className="op-results__status" role="status" aria-live="polite">
          {backgroundRefreshing ? (
            <span className="op-results__searching">
              <span className="spinner" aria-hidden="true" />
              <span>{t.operations.updating}</span>
            </span>
          ) : null}
        </div>

        {loading && !hasLoadedOnce ? (
          <LoadingState label={t.common.loading} />
        ) : null}
        {!loading && !hasLoadedOnce && error !== null ? (
          <ErrorState
            title={t.states.errorTitle}
            message={error}
            retryLabel={t.common.retry}
            onRetry={load}
          />
        ) : null}
        {hasLoadedOnce ? (
          items.length === 0 ? (
            <EmptyState title={c.empty} hint={c.emptyHint} />
          ) : (
            <div aria-busy={backgroundRefreshing}>
              <DataTable
                columns={columns}
                rows={items}
                rowKey={(item) => item.id}
                caption={c.title}
              />
            </div>
          )
        ) : null}
      </Card>

      <CatalogFormModal
        state={form}
        onClose={() => setForm(null)}
        onSaved={(created) => {
          setForm(null);
          notify(created ? c.created : c.updated);
          load();
        }}
      />
    </>
  );
}

/** Create / edit a catalog entry. Enforces the SAME client validations the
 * backend does (non-empty name, 3-letter currency, unit_price>=0, tax 0..100,
 * display_order>=0, a pricing mode) with friendly messages; the backend stays
 * authoritative. `is_active` is intentionally NOT here (its own route). */
function CatalogFormModal({
  state,
  onClose,
  onSaved,
}: {
  state: { item: GuestExtraService | null } | null;
  onClose: () => void;
  onSaved: (created: boolean) => void;
}) {
  const { t } = useI18n();
  const g = t.guestFolio;
  const c = g.catalog;
  const open = state !== null;
  const editing = state?.item ?? null;

  const [name, setName] = useState("");
  const [category, setCategory] = useState("other");
  const [description, setDescription] = useState("");
  const [unitPrice, setUnitPrice] = useState("0");
  const [currency, setCurrency] = useState("");
  const [taxRate, setTaxRate] = useState("0");
  const [pricingMode, setPricingMode] = useState("fixed");
  const [displayOrder, setDisplayOrder] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setBusy(false);
    if (editing) {
      setName(editing.name);
      setCategory(editing.category);
      setDescription(editing.description);
      setUnitPrice(editing.unit_price);
      setCurrency(editing.currency);
      setTaxRate(editing.tax_rate);
      setPricingMode(editing.pricing_mode);
      setDisplayOrder(String(editing.display_order));
    } else {
      setName("");
      setCategory("other");
      setDescription("");
      setUnitPrice("0");
      setCurrency("");
      setTaxRate("0");
      setPricingMode("fixed");
      setDisplayOrder("0");
    }
  }, [open, editing]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const trimmedName = name.trim();
    if (!trimmedName) return setError(c.errors.nameRequired);
    const code = currency.trim().toUpperCase();
    if (!CURRENCY_RE.test(code)) return setError(c.errors.currencyInvalid);
    const price = Number(unitPrice);
    if (!Number.isFinite(price) || price < 0)
      return setError(c.errors.priceInvalid);
    const tax = Number(taxRate);
    if (!Number.isFinite(tax) || tax < 0 || tax > 100)
      return setError(c.errors.taxInvalid);
    const order = Number(displayOrder);
    if (!Number.isInteger(order) || order < 0)
      return setError(c.errors.orderInvalid);

    const body: CatalogBody = {
      name: trimmedName,
      category,
      description: description.trim(),
      unit_price: String(price),
      currency: code,
      tax_rate: String(tax),
      pricing_mode: pricingMode,
      display_order: order,
    };
    setBusy(true);
    setError(null);
    try {
      if (editing) await updateCatalogItem(editing.id, body);
      else await createCatalogItem(body);
      onSaved(!editing);
    } catch (err) {
      // The only server-only failure my client validation can't pre-empt is the
      // per-hotel duplicate NAME (a field error under details.name).
      const duplicate =
        isApiError(err) &&
        err.details !== null &&
        typeof err.details === "object" &&
        "name" in (err.details as Record<string, unknown>);
      setError(duplicate ? c.errors.duplicateName : messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const categoryOptions = GUEST_SERVICE_CATEGORIES.map((value) => ({
    value,
    label: c.categories[value],
  }));
  const pricingOptions = GUEST_SERVICE_PRICING_MODES.map((value) => ({
    value,
    label: c.pricingModes[value],
  }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? c.editTitle : c.createTitle}
      closeLabel={t.common.close}
      preventClose={busy}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="gf-catalog-form" type="submit" loading={busy} disabled={busy}>
            {t.common.save}
          </Button>
        </>
      }
    >
      <form id="gf-catalog-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={c.fields.name} htmlFor="gf-cat-name">
          <Input id="gf-cat-name" value={name} onChange={(e) => setName(e.target.value)} />
        </FormField>
        <div className="form-grid">
          <FormField label={c.fields.category} htmlFor="gf-cat-category">
            <Select
              id="gf-cat-category"
              value={category}
              options={categoryOptions}
              onChange={(e) => setCategory(e.target.value)}
            />
          </FormField>
          <FormField label={c.fields.pricingMode} htmlFor="gf-cat-pricing">
            <Select
              id="gf-cat-pricing"
              value={pricingMode}
              options={pricingOptions}
              onChange={(e) => setPricingMode(e.target.value)}
            />
          </FormField>
        </div>
        <FormField label={c.fields.description} htmlFor="gf-cat-desc">
          <Textarea
            id="gf-cat-desc"
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </FormField>
        <div className="form-grid">
          <FormField label={c.fields.unitPrice} htmlFor="gf-cat-price">
            <Input
              id="gf-cat-price"
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={unitPrice}
              onChange={(e) => setUnitPrice(e.target.value)}
            />
          </FormField>
          <FormField label={c.fields.currency} htmlFor="gf-cat-currency">
            <Input
              id="gf-cat-currency"
              value={currency}
              maxLength={3}
              placeholder={c.currencyPlaceholder}
              onChange={(e) => setCurrency(e.target.value)}
            />
          </FormField>
          <FormField label={c.fields.taxRate} htmlFor="gf-cat-tax">
            <Input
              id="gf-cat-tax"
              type="number"
              min="0"
              max="100"
              step="0.01"
              inputMode="decimal"
              value={taxRate}
              onChange={(e) => setTaxRate(e.target.value)}
            />
          </FormField>
          <FormField label={c.fields.displayOrder} htmlFor="gf-cat-order">
            <Input
              id="gf-cat-order"
              type="number"
              min="0"
              step="1"
              inputMode="numeric"
              value={displayOrder}
              onChange={(e) => setDisplayOrder(e.target.value)}
            />
          </FormField>
        </div>
      </form>
    </Modal>
  );
}
