"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Hotel, Search } from "lucide-react";

import { PublicHotelCard } from "@/components/public/PublicHotelCard";
import { PublicShell } from "@/components/public/PublicShell";
import { Button, EmptyState, ErrorState, Input, LoadingState } from "@/components/ui";
import { listPublicHotels, type PublicHotelCard as HotelCardDto } from "@/lib/api/public";
import { messageForError } from "@/lib/api/errors";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** Public directory of published hotels (Phase 15) with a simple search. */
export default function PublicHotelsPage() {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [hotels, setHotels] = useState<HotelCardDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (q?: string) => {
      setLoading(true);
      setError(null);
      try {
        setHotels((await listPublicHotels(q ? { q } : undefined)).results);
      } catch (err) {
        setError(messageForError(err, t));
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    load();
  }, [load]);

  function submit(event: FormEvent) {
    event.preventDefault();
    load(query.trim() || undefined);
  }

  return (
    <PublicShell>
      <section className="public-section">
        <div className="public-section__head">
          <div>
            <h1>{t.public.hotels.title}</h1>
            <p className="muted">{t.public.hotels.subtitle}</p>
          </div>
        </div>

        <form className="public-search" onSubmit={submit} noValidate>
          <Input
            value={query}
            placeholder={t.public.hotels.searchPlaceholder}
            aria-label={t.public.hotels.searchPlaceholder}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Button type="submit" icon={Search}>
            {t.public.hotels.search}
          </Button>
        </form>

        {loading ? <LoadingState label={t.common.loading} /> : null}
        {!loading && error ? (
          <ErrorState
            title={t.states.errorTitle}
            message={error}
            retryLabel={t.common.retry}
            onRetry={() => load(query.trim() || undefined)}
          />
        ) : null}
        {!loading && !error ? (
          hotels.length === 0 ? (
            <EmptyState
              title={t.public.hotels.empty}
              hint={t.public.hotels.emptyHint}
              icon={Hotel}
            />
          ) : (
            <div className="public-hotel-grid">
              {hotels.map((h) => (
                <PublicHotelCard key={h.slug} hotel={h} />
              ))}
            </div>
          )
        ) : null}
      </section>
    </PublicShell>
  );
}
