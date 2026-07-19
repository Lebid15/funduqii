"use client";

import { useEffect, useRef, useState } from "react";

import { Button, FormField, Input, Select } from "@/components/ui";
import { listRoomOptions } from "@/lib/api/rooms";
import type { RoomOption } from "@/lib/api/types";

/**
 * Async, server-side-searchable room picker for the operations dropdowns
 * (WP10 §7). Replaces the old `listRooms({ page_size: 100 })` feed — which
 * silently dropped every room past the first 100 — with the compact,
 * paginated `GET /rooms/options/?search=&page=` endpoint, so no room is ever
 * unreachable in a large hotel.
 *
 * A debounced search input narrows the results server-side; "load more" pages
 * through the rest. The currently-selected room is always kept selectable even
 * when it falls outside the active search/page (via `selectedLabel`), so a
 * preselected room (e.g. reported from a cleaning card) never disappears.
 *
 * Presentational only — the backend owns tenancy + archived filtering.
 */
export function RoomOptionSelect({
  id,
  label,
  value,
  onChange,
  placeholder,
  searchPlaceholder,
  loadMoreLabel,
  loadingLabel,
  emptyLabel,
  disabled = false,
  invalid = false,
  selectedLabel,
}: {
  id: string;
  label: string;
  value: number | null;
  onChange: (roomId: number | null) => void;
  /** Empty-option label (also the "any room" choice for filters). */
  placeholder: string;
  searchPlaceholder: string;
  loadMoreLabel: string;
  loadingLabel: string;
  emptyLabel: string;
  disabled?: boolean;
  invalid?: boolean;
  /** Known label for `value` so a preselected room shows before the fetch. */
  selectedLabel?: string;
}) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [options, setOptions] = useState<RoomOption[]>([]);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(false);
  // Guards against a slow earlier request overwriting a newer one.
  const requestSeq = useRef(0);

  // Debounce the free-text search (server-side match).
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(handle);
  }, [search]);

  // Fetch page 1 whenever the (debounced) search changes.
  useEffect(() => {
    const seq = (requestSeq.current += 1);
    setLoading(true);
    listRoomOptions({ search: debounced || undefined, page: 1 })
      .then((res) => {
        if (seq !== requestSeq.current) return;
        setOptions(res.results);
        setHasNext(res.next !== null);
        setPage(1);
      })
      .catch(() => {
        if (seq !== requestSeq.current) return;
        setOptions([]);
        setHasNext(false);
      })
      .finally(() => {
        if (seq === requestSeq.current) setLoading(false);
      });
  }, [debounced]);

  async function loadMore() {
    const seq = (requestSeq.current += 1);
    setLoading(true);
    try {
      const next = page + 1;
      const res = await listRoomOptions({ search: debounced || undefined, page: next });
      if (seq !== requestSeq.current) return;
      setOptions((prev) => [...prev, ...res.results]);
      setHasNext(res.next !== null);
      setPage(next);
    } catch {
      if (seq === requestSeq.current) setHasNext(false);
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }

  const selectOptions = options.map((room) => ({
    value: String(room.id),
    label: room.floor_name ? `${room.number} · ${room.floor_name}` : room.number,
  }));
  // Keep the current selection reachable even when it is not in the active page.
  if (value !== null && !options.some((room) => room.id === value)) {
    selectOptions.unshift({
      value: String(value),
      label: selectedLabel || `#${value}`,
    });
  }

  return (
    <FormField label={label} htmlFor={id}>
      <div className="stack" style={{ gap: "var(--space-2)" }}>
        <Input
          id={`${id}-search`}
          value={search}
          placeholder={searchPlaceholder}
          disabled={disabled}
          aria-label={searchPlaceholder}
          onChange={(event) => setSearch(event.target.value)}
        />
        <Select
          id={id}
          value={value !== null ? String(value) : ""}
          placeholder={placeholder}
          options={selectOptions}
          invalid={invalid}
          disabled={disabled}
          onChange={(event) =>
            onChange(event.target.value ? Number(event.target.value) : null)
          }
        />
        <div className="cluster" style={{ justifyContent: "space-between" }}>
          <span className="muted small">
            {loading
              ? loadingLabel
              : selectOptions.length === 0
                ? emptyLabel
                : null}
          </span>
          {hasNext ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={loading || disabled}
              onClick={loadMore}
            >
              {loadMoreLabel}
            </Button>
          ) : null}
        </div>
      </div>
    </FormField>
  );
}
