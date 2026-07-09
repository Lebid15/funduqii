"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Building2, Plus, Search } from "lucide-react";

import { PageContainer } from "@/components/layout/PageContainer";
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
  PageHeader,
  Pagination,
  PasswordInput,
  Select,
  useToast,
  type Column,
} from "@/components/ui";
import {
  activateHotel,
  createHotel,
  listHotels,
  suspendHotel,
  unsuspendHotel,
  type HotelCreateBody,
} from "@/lib/api/platform";
import { messageForError } from "@/lib/api/errors";
import type { Hotel } from "@/lib/api/types";
import {
  hotelStatusLabel,
  hotelStatusTone,
  subscriptionStatusLabel,
  subscriptionStatusTone,
} from "@/lib/format";
import { useI18n } from "@/lib/i18n/I18nProvider";

const PAGE_SIZE = 25;

export default function HotelsPage() {
  const { t } = useI18n();
  const { notify } = useToast();

  const [rows, setRows] = useState<Hotel[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [subscription, setSubscription] = useState("");
  const [publicListed, setPublicListed] = useState("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [suspendTarget, setSuspendTarget] = useState<Hotel | null>(null);

  // Await-first so the mount effect performs no synchronous setState; the
  // spinner for user-initiated refetches is set by the handlers below.
  const load = useCallback(async () => {
    try {
      const data = await listHotels({
        page,
        status: status || undefined,
        subscription: subscription || undefined,
        public: publicListed || undefined,
        search: query || undefined,
      });
      setRows(data.results);
      setCount(data.count);
      setError(null);
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setLoading(false);
    }
  }, [page, status, subscription, publicListed, query, t]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  const statusOptions = useMemo(
    () => [
      { value: "setup", label: t.hotels.statusSetup },
      { value: "active", label: t.hotels.statusActive },
      { value: "suspended", label: t.hotels.statusSuspended },
    ],
    [t],
  );

  async function runAction(action: () => Promise<Hotel>) {
    try {
      await action();
      notify(t.settings.saved);
      load();
    } catch (err) {
      notify(messageForError(err, t), "error");
    }
  }

  const columns: Column<Hotel>[] = [
    {
      key: "name",
      header: t.hotels.name,
      render: (row) => (
        <Link className="table__link" href={`/platform/hotels/${row.id}`}>
          {row.name}
        </Link>
      ),
    },
    {
      key: "city",
      header: t.hotels.city,
      render: (row) => row.city || <span className="muted">—</span>,
    },
    {
      key: "status",
      header: t.common.status,
      render: (row) => (
        <Badge tone={hotelStatusTone(row.status)}>
          {hotelStatusLabel(row.status, t)}
        </Badge>
      ),
    },
    {
      key: "subscription",
      header: t.hotels.subscription,
      render: (row) =>
        row.current_subscription ? (
          <Badge tone={subscriptionStatusTone(row.current_subscription.status)}>
            {subscriptionStatusLabel(row.current_subscription.status, t)}
          </Badge>
        ) : (
          <span className="muted">{t.hotels.noSubscription}</span>
        ),
    },
    {
      key: "public",
      header: t.hotels.publicListed,
      render: (row) => (
        <Badge tone={row.public_is_listed ? "success" : "neutral"}>
          {row.public_is_listed ? t.common.yes : t.common.no}
        </Badge>
      ),
    },
    {
      key: "primary_manager",
      header: t.hotels.primaryManager,
      render: (row) =>
        row.primary_manager ? (
          row.primary_manager.email
        ) : (
          <span className="muted">{t.hotels.noManager}</span>
        ),
    },
    {
      key: "actions",
      header: t.common.actions,
      align: "end",
      render: (row) => (
        <div className="table__actions">
          {row.status === "setup" ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => runAction(() => activateHotel(row.id))}
            >
              {t.hotels.activate}
            </Button>
          ) : null}
          {row.status === "active" ? (
            <Button variant="danger" size="sm" onClick={() => setSuspendTarget(row)}>
              {t.hotels.suspend}
            </Button>
          ) : null}
          {row.status === "suspended" ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => runAction(() => unsuspendHotel(row.id))}
            >
              {t.hotels.unsuspend}
            </Button>
          ) : null}
        </div>
      ),
    },
  ];

  function applySearch(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setPage(1);
    setQuery(search);
  }

  return (
    <PageContainer>
      <PageHeader
        title={t.hotels.title}
        subtitle={t.hotels.subtitle}
        actions={
          <Button icon={Plus} onClick={() => setModalOpen(true)}>
            {t.hotels.create}
          </Button>
        }
      />

      <Card>
        <form onSubmit={applySearch}>
          <FilterBar>
            <FormField label={t.common.search} htmlFor="hotel-search">
              <Input
                id="hotel-search"
                value={search}
                placeholder={t.hotels.searchPlaceholder}
                onChange={(event) => setSearch(event.target.value)}
              />
            </FormField>
            <FormField label={t.hotels.filterStatus} htmlFor="hotel-status">
              <Select
                id="hotel-status"
                value={status}
                placeholder={t.common.all}
                options={statusOptions}
                onChange={(event) => {
                  setLoading(true);
                  setPage(1);
                  setStatus(event.target.value);
                }}
              />
            </FormField>
            <FormField label={t.hotels.filterSubscription} htmlFor="hotel-sub">
              <Select
                id="hotel-sub"
                value={subscription}
                placeholder={t.common.all}
                options={[
                  { value: "trial", label: t.subscriptions.statusTrial },
                  { value: "active", label: t.subscriptions.statusActive },
                  { value: "expired", label: t.subscriptions.statusExpired },
                  { value: "cancelled", label: t.subscriptions.statusCancelled },
                ]}
                onChange={(event) => {
                  setLoading(true);
                  setPage(1);
                  setSubscription(event.target.value);
                }}
              />
            </FormField>
            <FormField label={t.hotels.publicListed} htmlFor="hotel-public">
              <Select
                id="hotel-public"
                value={publicListed}
                placeholder={t.common.all}
                options={[
                  { value: "true", label: t.common.yes },
                  { value: "false", label: t.common.no },
                ]}
                onChange={(event) => {
                  setLoading(true);
                  setPage(1);
                  setPublicListed(event.target.value);
                }}
              />
            </FormField>
            <div className="filter-bar__actions">
              <Button type="submit" variant="secondary" icon={Search}>
                {t.common.search}
              </Button>
            </div>
          </FilterBar>
        </form>
      </Card>

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

      {!loading && !error ? (
        rows.length === 0 ? (
          <EmptyState
            title={t.hotels.empty}
            hint={t.hotels.emptyHint}
            icon={Building2}
            action={
              <Button icon={Plus} onClick={() => setModalOpen(true)}>
                {t.hotels.create}
              </Button>
            }
          />
        ) : (
          <>
            <DataTable
              caption={t.hotels.title}
              columns={columns}
              rows={rows}
              rowKey={(row) => row.id}
            />
            <Pagination
              page={page}
              totalPages={totalPages}
              onPageChange={(next) => {
                setLoading(true);
                setPage(next);
              }}
              labels={{
                previous: t.pagination.previous,
                next: t.pagination.next,
                status: t.pagination.page
                  .replace("{page}", String(page))
                  .replace("{total}", String(totalPages)),
              }}
            />
          </>
        )
      ) : null}

      <CreateHotelModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={() => {
          setModalOpen(false);
          notify(t.settings.saved);
          setPage(1);
          load();
        }}
      />
      <SuspendHotelModal
        hotel={suspendTarget}
        onClose={() => setSuspendTarget(null)}
        onDone={() => {
          setSuspendTarget(null);
          notify(t.settings.saved);
          load();
        }}
      />
    </PageContainer>
  );
}

/** Suspension always records a REASON (and who did it, on the backend). */
function SuspendHotelModal({
  hotel,
  onClose,
  onDone,
}: {
  hotel: Hotel | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (hotel) {
      setReason("");
      setError(null);
    }
  }, [hotel]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!hotel || !reason.trim()) {
      setError(t.hotels.suspendReasonRequired);
      return;
    }
    setBusy(true);
    try {
      await suspendHotel(hotel.id, reason.trim());
      onDone();
    } catch (err) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={hotel !== null}
      onClose={onClose}
      title={t.hotels.suspendTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="suspend-hotel-form" type="submit" variant="danger" loading={busy}>
            {t.hotels.suspend}
          </Button>
        </>
      }
    >
      <form id="suspend-hotel-form" className="stack" onSubmit={submit} noValidate>
        <p className="muted">{t.hotels.suspendBody}</p>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={t.hotels.suspendReason} htmlFor="suspend-reason">
          <Input
            id="suspend-reason"
            value={reason}
            required
            onChange={(event) => setReason(event.target.value)}
          />
        </FormField>
      </form>
    </Modal>
  );
}

function CreateHotelModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [withManager, setWithManager] = useState(false);
  const [managerEmail, setManagerEmail] = useState("");
  const [managerName, setManagerName] = useState("");
  const [managerPassword, setManagerPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function reset() {
    setName("");
    setSlug("");
    setWithManager(false);
    setManagerEmail("");
    setManagerName("");
    setManagerPassword("");
    setError(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!name.trim()) return setError(t.hotels.nameRequired);
    if (!slug.trim()) return setError(t.hotels.slugRequired);

    const body: HotelCreateBody = { name: name.trim(), slug: slug.trim() };
    if (withManager) {
      body.manager = {
        email: managerEmail.trim(),
        full_name: managerName.trim(),
        password: managerPassword,
      };
    }
    setBusy(true);
    try {
      await createHotel(body);
      reset();
      onCreated();
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
      title={t.hotels.createTitle}
      closeLabel={t.common.close}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button form="create-hotel-form" type="submit" disabled={busy}>
            {busy ? t.common.creating : t.common.create}
          </Button>
        </>
      }
    >
      <form id="create-hotel-form" className="stack" onSubmit={submit} noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <FormField label={t.hotels.name} htmlFor="new-hotel-name">
          <Input
            id="new-hotel-name"
            value={name}
            required
            onChange={(event) => setName(event.target.value)}
          />
        </FormField>
        <FormField label={t.hotels.slug} htmlFor="new-hotel-slug">
          <Input
            id="new-hotel-slug"
            value={slug}
            required
            onChange={(event) => setSlug(event.target.value)}
          />
        </FormField>

        <label className="cluster">
          <input
            type="checkbox"
            checked={withManager}
            onChange={(event) => setWithManager(event.target.checked)}
          />
          <span>{t.hotels.addManagerOptional}</span>
        </label>

        {withManager ? (
          <>
            <FormField label={t.hotels.managerFullName} htmlFor="new-mgr-name">
              <Input
                id="new-mgr-name"
                value={managerName}
                onChange={(event) => setManagerName(event.target.value)}
              />
            </FormField>
            <FormField label={t.hotels.managerEmail} htmlFor="new-mgr-email">
              <Input
                id="new-mgr-email"
                type="email"
                value={managerEmail}
                onChange={(event) => setManagerEmail(event.target.value)}
              />
            </FormField>
            <FormField label={t.hotels.managerPassword} htmlFor="new-mgr-pass">
              <PasswordInput
                id="new-mgr-pass"
                value={managerPassword}
                showLabel={t.auth.showPassword}
                hideLabel={t.auth.hidePassword}
                onChange={(event) => setManagerPassword(event.target.value)}
              />
            </FormField>
          </>
        ) : null}
      </form>
    </Modal>
  );
}
