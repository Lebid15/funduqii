"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { FolderOpen, Pencil, Plus, Trash2, UtensilsCrossed } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  FormField,
  Input,
  LoadingState,
  Modal,
  Pagination,
  SectionHeader,
  Select,
  Switch,
  useToast,
  type Column,
} from "@/components/ui";
import {
  createServiceCategory,
  createServiceItem,
  deleteServiceCategory,
  deleteServiceItem,
  listServiceCategories,
  listServiceItems,
  updateServiceCategory,
  updateServiceItem,
  type ServiceCategoryBody,
  type ServiceItemBody,
} from "@/lib/api/services";
import { messageForError } from "@/lib/api/errors";
import type { ServiceCategory, ServiceItem } from "@/lib/api/types";
import { formatMoney } from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

const PAGE_SIZE = 25;
const ITEM_TYPES = ["restaurant", "cafe", "room_service", "other"] as const;

export function CatalogTab() {
  const { t, locale } = useI18n();
  const { notify } = useToast();

  const [categories, setCategories] = useState<ServiceCategory[]>([]);
  const [items, setItems] = useState<ServiceItem[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState("");
  const [itemType, setItemType] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [categoryModal, setCategoryModal] = useState<{ open: boolean; edit: ServiceCategory | null }>({ open: false, edit: null });
  const [itemModal, setItemModal] = useState<{ open: boolean; edit: ServiceItem | null }>({ open: false, edit: null });
  const [deleteCat, setDeleteCat] = useState<ServiceCategory | null>(null);
  const [deleteItem, setDeleteItem] = useState<ServiceItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cats, its] = await Promise.all([
        listServiceCategories(),
        listServiceItems({
          page,
          search: query || undefined,
          category: category ? Number(category) : undefined,
          item_type: itemType || undefined,
        }),
      ]);
      setCategories(cats.results);
      setItems(its.results);
      setCount(its.count);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, query, category, itemType, t]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const categoryOptions = categories.map((c) => ({ value: String(c.id), label: c.name }));
  const typeOptions = ITEM_TYPES.map((v) => ({ value: v, label: t.services.itemTypes[v] }));

  const catColumns: Column<ServiceCategory>[] = [
    { key: "name", header: t.services.catalog.categoryName },
    { key: "code", header: t.services.catalog.categoryCode, render: (r) => r.code || "—" },
    { key: "item_count", header: t.services.catalog.itemCount },
    {
      key: "is_active",
      header: t.common.status,
      render: (r) => (
        <Badge tone={r.is_active ? "success" : "neutral"}>
          {r.is_active ? t.services.catalog.active : t.services.catalog.inactive}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => (
        <div className="table__actions">
          <Button size="sm" variant="secondary" icon={Pencil} onClick={() => setCategoryModal({ open: true, edit: r })}>
            {t.common.edit}
          </Button>
          <Button size="sm" variant="danger" icon={Trash2} onClick={() => setDeleteCat(r)}>
            {t.common.delete}
          </Button>
        </div>
      ),
    },
  ];

  const itemColumns: Column<ServiceItem>[] = [
    { key: "name", header: t.services.catalog.itemName },
    { key: "category_name", header: t.services.catalog.itemCategory },
    { key: "item_type", header: t.services.catalog.itemTypeLabel, render: (r) => t.services.itemTypes[r.item_type] },
    { key: "unit_price", header: t.services.catalog.price, render: (r) => formatMoney(r.unit_price, r.currency, locale) },
    { key: "tax_rate", header: t.services.catalog.taxRate, render: (r) => `${r.tax_rate}%` },
    {
      key: "is_available",
      header: t.services.catalog.available,
      render: (r) => (
        <Badge tone={r.is_available && r.is_active ? "success" : "neutral"}>
          {r.is_available && r.is_active ? t.services.catalog.available : t.services.catalog.unavailable}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (r) => (
        <div className="table__actions">
          <Button size="sm" variant="secondary" icon={Pencil} onClick={() => setItemModal({ open: true, edit: r })}>
            {t.common.edit}
          </Button>
          <Button size="sm" variant="danger" icon={Trash2} onClick={() => setDeleteItem(r)}>
            {t.common.delete}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <Card>
        <SectionHeader
          title={t.services.catalog.categories}
          actions={
            <Button icon={Plus} onClick={() => setCategoryModal({ open: true, edit: null })}>
              {t.services.catalog.addCategory}
            </Button>
          }
        />
        {loading ? <LoadingState label={t.common.loading} /> : null}
        {!loading && !error ? (
          categories.length === 0 ? (
            <EmptyState
              title={t.services.catalog.emptyCategories}
              hint={t.services.catalog.emptyCategoriesHint}
              icon={FolderOpen}
            />
          ) : (
            <DataTable caption={t.services.catalog.categories} columns={catColumns} rows={categories} rowKey={(r) => r.id} />
          )
        ) : null}
      </Card>

      <Card>
        <SectionHeader
          title={t.services.catalog.items}
          actions={
            <Button icon={Plus} onClick={() => setItemModal({ open: true, edit: null })}>
              {t.services.catalog.addItem}
            </Button>
          }
        />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            setQuery(search);
          }}
        >
          <FilterBar>
            <FormField label={t.common.search} htmlFor="svc-search">
              <Input id="svc-search" value={search} placeholder={t.services.catalog.searchPlaceholder} onChange={(e) => setSearch(e.target.value)} />
            </FormField>
            <FormField label={t.services.catalog.itemCategory} htmlFor="svc-cat">
              <Select id="svc-cat" value={category} placeholder={t.common.all} options={categoryOptions} onChange={(e) => { setPage(1); setCategory(e.target.value); }} />
            </FormField>
            <FormField label={t.services.catalog.itemTypeLabel} htmlFor="svc-type">
              <Select id="svc-type" value={itemType} placeholder={t.common.all} options={typeOptions} onChange={(e) => { setPage(1); setItemType(e.target.value); }} />
            </FormField>
          </FilterBar>
        </form>
        {loading ? <LoadingState label={t.common.loading} /> : null}
        {!loading && error ? (
          <ErrorState title={t.states.errorTitle} message={error} retryLabel={t.common.retry} onRetry={load} />
        ) : null}
        {!loading && !error ? (
          items.length === 0 ? (
            <EmptyState
              title={t.services.catalog.emptyItems}
              hint={t.services.catalog.emptyItemsHint}
              icon={UtensilsCrossed}
              action={
                <Button icon={Plus} onClick={() => setItemModal({ open: true, edit: null })}>
                  {t.services.catalog.addItem}
                </Button>
              }
            />
          ) : (
            <>
              <DataTable caption={t.services.catalog.items} columns={itemColumns} rows={items} rowKey={(r) => r.id} />
              <Pagination
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                labels={{
                  previous: t.pagination.previous,
                  next: t.pagination.next,
                  status: t.pagination.page.replace("{page}", String(page)).replace("{total}", String(totalPages)),
                }}
              />
            </>
          )
        ) : null}
      </Card>

      <CategoryModal
        open={categoryModal.open}
        edit={categoryModal.edit}
        onClose={() => setCategoryModal({ open: false, edit: null })}
        onSaved={() => {
          setCategoryModal({ open: false, edit: null });
          notify(t.services.saved);
          load();
        }}
      />
      <ItemModal
        open={itemModal.open}
        edit={itemModal.edit}
        categories={categories}
        onClose={() => setItemModal({ open: false, edit: null })}
        onSaved={() => {
          setItemModal({ open: false, edit: null });
          notify(t.services.saved);
          load();
        }}
      />
      <ConfirmDialog
        open={deleteCat !== null}
        title={t.services.catalog.deleteCategory}
        body={t.services.catalog.deleteConfirmCategory}
        confirmLabel={t.common.delete}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        onClose={() => setDeleteCat(null)}
        onConfirm={async () => {
          if (!deleteCat) return;
          try {
            await deleteServiceCategory(deleteCat.id);
            notify(t.services.saved);
            load();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setDeleteCat(null);
          }
        }}
      />
      <ConfirmDialog
        open={deleteItem !== null}
        title={t.services.catalog.deleteItem}
        body={t.services.catalog.deleteConfirmItem}
        confirmLabel={t.common.delete}
        cancelLabel={t.common.cancel}
        closeLabel={t.common.close}
        tone="danger"
        onClose={() => setDeleteItem(null)}
        onConfirm={async () => {
          if (!deleteItem) return;
          try {
            await deleteServiceItem(deleteItem.id);
            notify(t.services.saved);
            load();
          } catch (err) {
            notify(messageForError(err, t), "error");
          } finally {
            setDeleteItem(null);
          }
        }}
      />
    </>
  );
}

function CategoryModal({
  open,
  edit,
  onClose,
  onSaved,
}: {
  open: boolean;
  edit: ServiceCategory | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState<ServiceCategoryBody>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(
        edit
          ? { name: edit.name, code: edit.code, description: edit.description, is_active: edit.is_active }
          : { name: "", code: "", description: "", is_active: true },
      );
      setError(null);
    }
  }, [open, edit]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.name?.trim()) return setError(t.errors.validation);
    setBusy(true);
    setError(null);
    try {
      if (edit) await updateServiceCategory(edit.id, form);
      else await createServiceCategory(form);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={edit ? t.services.catalog.editCategory : t.services.catalog.addCategory}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="svc-cat-form" type="submit" loading={busy}>{t.common.save}</Button>
        </>
      }
    >
      <form id="svc-cat-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.services.catalog.categoryName} htmlFor="c-name">
            <Input id="c-name" value={form.name ?? ""} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
          </FormField>
          <FormField label={t.services.catalog.categoryCode} htmlFor="c-code">
            <Input id="c-code" value={form.code ?? ""} onChange={(e) => setForm((p) => ({ ...p, code: e.target.value }))} />
          </FormField>
        </div>
        <FormField label={t.services.catalog.categoryDescription} htmlFor="c-desc">
          <Input id="c-desc" value={form.description ?? ""} onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))} />
        </FormField>
        <Switch
          id="c-active"
          checked={form.is_active ?? true}
          onChange={(checked) => setForm((p) => ({ ...p, is_active: checked }))}
          label={t.services.catalog.active}
        />
      </form>
    </Modal>
  );
}

function ItemModal({
  open,
  edit,
  categories,
  onClose,
  onSaved,
}: {
  open: boolean;
  edit: ServiceItem | null;
  categories: ServiceCategory[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState<ServiceItemBody>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(
        edit
          ? {
              category: edit.category,
              name: edit.name,
              code: edit.code,
              description: edit.description,
              item_type: edit.item_type,
              unit_price: edit.unit_price,
              tax_rate: edit.tax_rate,
              is_available: edit.is_available,
              is_active: edit.is_active,
            }
          : {
              category: categories[0]?.id,
              name: "",
              code: "",
              description: "",
              item_type: "restaurant",
              unit_price: "",
              tax_rate: "0",
              is_available: true,
              is_active: true,
            },
      );
      setError(null);
    }
  }, [open, edit, categories]);

  function set<K extends keyof ServiceItemBody>(k: K, v: ServiceItemBody[K]) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.name?.trim() || !form.category || form.unit_price === "") {
      return setError(t.errors.validation);
    }
    setBusy(true);
    setError(null);
    try {
      if (edit) await updateServiceItem(edit.id, form);
      else await createServiceItem(form);
      onSaved();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  const categoryOptions = categories.map((c) => ({ value: String(c.id), label: c.name }));
  const typeOptions = ITEM_TYPES.map((v) => ({ value: v, label: t.services.itemTypes[v] }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={edit ? t.services.catalog.editItem : t.services.catalog.addItem}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>{t.common.cancel}</Button>
          <Button form="svc-item-form" type="submit" loading={busy}>{t.common.save}</Button>
        </>
      }
    >
      <form id="svc-item-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="form-grid">
          <FormField label={t.services.catalog.itemName} htmlFor="i-name">
            <Input id="i-name" value={form.name ?? ""} onChange={(e) => set("name", e.target.value)} />
          </FormField>
          <FormField label={t.services.catalog.itemCategory} htmlFor="i-cat">
            <Select
              id="i-cat"
              value={form.category ? String(form.category) : ""}
              options={categoryOptions}
              onChange={(e) => set("category", Number(e.target.value))}
            />
          </FormField>
          <FormField label={t.services.catalog.itemTypeLabel} htmlFor="i-type">
            <Select id="i-type" value={form.item_type ?? "restaurant"} options={typeOptions} onChange={(e) => set("item_type", e.target.value as ServiceItem["item_type"])} />
          </FormField>
          <FormField label={t.services.catalog.price} htmlFor="i-price">
            <Input id="i-price" type="number" step="0.01" min="0" value={form.unit_price ?? ""} onChange={(e) => set("unit_price", e.target.value)} />
          </FormField>
          <FormField label={t.services.catalog.taxRate} htmlFor="i-tax">
            <Input id="i-tax" type="number" step="0.01" min="0" value={form.tax_rate ?? ""} onChange={(e) => set("tax_rate", e.target.value)} />
          </FormField>
          <FormField label={t.services.catalog.itemCode} htmlFor="i-code">
            <Input id="i-code" value={form.code ?? ""} onChange={(e) => set("code", e.target.value)} />
          </FormField>
        </div>
        <FormField label={t.services.catalog.itemDescription} htmlFor="i-desc">
          <Input id="i-desc" value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} />
        </FormField>
        <div className="cluster">
          <Switch id="i-avail" checked={form.is_available ?? true} onChange={(checked) => set("is_available", checked)} label={t.services.catalog.available} />
          <Switch id="i-active" checked={form.is_active ?? true} onChange={(checked) => set("is_active", checked)} label={t.services.catalog.active} />
        </div>
      </form>
    </Modal>
  );
}
