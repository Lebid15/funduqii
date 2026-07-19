import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/rooms", () => ({
  listRoomOptions: vi.fn(),
}));

import { listRoomOptions } from "@/lib/api/rooms";
import type { PaginatedResponse, RoomOption } from "@/lib/api/types";
import { RoomOptionSelect } from "../RoomOptionSelect";
import { makeRoomOption, renderWithProviders } from "@/test-utils";

/**
 * RoomOptionSelect (WP12 / owner §17 "SEARCH/FILTERS/PAGINATION"). The async,
 * server-searchable room picker that REPLACED the old `listRooms({ page_size:
 * 100 })` feed (which silently dropped every room past 100). It must page the
 * compact `GET /rooms/options/?search=&page=` endpoint — never request a fixed
 * 100-row page — so no room is unreachable in a large hotel.
 */

function page(results: RoomOption[], next: string | null = null): PaginatedResponse<RoomOption> {
  return { count: results.length, next, previous: null, results };
}

function renderSelect(props: Partial<React.ComponentProps<typeof RoomOptionSelect>> = {}) {
  return renderWithProviders(
    <RoomOptionSelect
      id="op-room"
      label="Room"
      value={props.value ?? null}
      onChange={props.onChange ?? vi.fn()}
      placeholder="Any room"
      searchPlaceholder="Search rooms…"
      loadMoreLabel="Load more"
      loadingLabel="Loading…"
      emptyLabel="No rooms found."
      selectedLabel={props.selectedLabel}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listRoomOptions).mockResolvedValue(page([makeRoomOption()]));
});

describe("RoomOptionSelect — uses the paginated options endpoint", () => {
  it("fetches page 1 of listRoomOptions on mount and NEVER passes page_size", async () => {
    renderSelect();
    await waitFor(() => expect(listRoomOptions).toHaveBeenCalled());
    // The first fetch is the compact options feed, page 1, no search.
    expect(listRoomOptions).toHaveBeenCalledWith({ search: undefined, page: 1 });
    // Not a single call carries a `page_size` (the dropped-rows bug it replaced).
    for (const [params] of vi.mocked(listRoomOptions).mock.calls) {
      expect(params).not.toHaveProperty("page_size");
    }
  });

  it("renders the returned rooms as options (number · floor)", async () => {
    vi.mocked(listRoomOptions).mockResolvedValue(
      page([makeRoomOption({ id: 11, number: "101", floor_name: "Ground" })]),
    );
    renderSelect();
    const select = screen.getByLabelText("Room") as HTMLSelectElement;
    await waitFor(() =>
      expect(within(select).getByRole("option", { name: "101 · Ground" })).toBeInTheDocument(),
    );
  });
});

describe("RoomOptionSelect — server-side debounced search", () => {
  it("forwards the typed term to listRoomOptions (debounced, page 1)", async () => {
    renderSelect();
    await waitFor(() => expect(listRoomOptions).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("Search rooms…"), {
      target: { value: "204" },
    });
    await waitFor(() =>
      expect(listRoomOptions).toHaveBeenCalledWith({ search: "204", page: 1 }),
    );
  });
});

describe("RoomOptionSelect — load more (server pagination)", () => {
  it("shows Load more when there is a next page and appends page 2", async () => {
    vi.mocked(listRoomOptions)
      .mockResolvedValueOnce(page([makeRoomOption({ id: 11, number: "101" })], "/rooms/options?page=2"))
      .mockResolvedValueOnce(page([makeRoomOption({ id: 12, number: "102" })], null));

    renderSelect();
    const loadMore = await screen.findByRole("button", { name: "Load more" });
    fireEvent.click(loadMore);

    await waitFor(() =>
      expect(vi.mocked(listRoomOptions)).toHaveBeenCalledWith({ search: undefined, page: 2 }),
    );
    const select = screen.getByLabelText("Room") as HTMLSelectElement;
    // Both pages are now selectable — page 1 rows are NOT discarded.
    await waitFor(() =>
      expect(within(select).getByRole("option", { name: /102/ })).toBeInTheDocument(),
    );
    expect(within(select).getByRole("option", { name: /101/ })).toBeInTheDocument();
  });

  it("hides Load more when the endpoint reports no next page", async () => {
    vi.mocked(listRoomOptions).mockResolvedValue(page([makeRoomOption()], null));
    renderSelect();
    await screen.findByLabelText("Room");
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });
});

describe("RoomOptionSelect — selection", () => {
  it("emits the chosen room id through onChange", async () => {
    const onChange = vi.fn();
    vi.mocked(listRoomOptions).mockResolvedValue(
      page([makeRoomOption({ id: 11, number: "101" })]),
    );
    renderSelect({ onChange });
    const select = (await screen.findByLabelText("Room")) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "11" } });
    expect(onChange).toHaveBeenCalledWith(11);
  });

  it("keeps a preselected room reachable via selectedLabel even when off-page", async () => {
    vi.mocked(listRoomOptions).mockResolvedValue(
      page([makeRoomOption({ id: 11, number: "101" })]),
    );
    renderSelect({ value: 999, selectedLabel: "Room 900" });
    const select = (await screen.findByLabelText("Room")) as HTMLSelectElement;
    // The current selection stays present even though the fetch never returned it.
    expect(within(select).getByRole("option", { name: "Room 900" })).toBeInTheDocument();
    expect(select.value).toBe("999");
  });
});
