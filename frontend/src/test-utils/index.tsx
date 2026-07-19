/**
 * Shared, deterministic test helpers for the guest-UI Vitest suites
 * (MANDATE W7). NOT a test file itself (no `.test`/`.spec`), so the runner never
 * collects it — it only provides render wrappers and typed data factories so the
 * component tests render against the REAL i18n dictionary + UI primitives.
 *
 * Everything here is pure/deterministic: no timers, no network, no randomness.
 * The API layer is mocked per-test-file (`vi.mock`), never by this module.
 */
import type { ReactElement, ReactNode } from "react";
import { render } from "@testing-library/react";

import { ToastProvider } from "@/components/ui";
import type { ApiError } from "@/lib/api/client";
import type {
  ArrivalNotReadyRow,
  Guest,
  GuestChangeLogRow,
  GuestCurrentUnit,
  GuestDirectoryRow,
  GuestDocumentRow,
  GuestProfile,
  GuestReservationRow,
  GuestStayRow,
  HousekeepingTaskListItem,
  LostFoundItemListItem,
  MaintenanceRequestListItem,
  OperationsOverview,
  RoomOption,
  StaffMemberListItem,
} from "@/lib/api/types";
import type { Locale } from "@/lib/i18n/config";
import { I18nProvider } from "@/lib/i18n/I18nProvider";

/** Wrap a subtree in the real i18n + toast providers (the minimum the guest UI
 * needs). The hotel-access context is mocked per test file, never here. */
export function Providers({
  locale = "en",
  children,
}: {
  locale?: Locale;
  children: ReactNode;
}) {
  return (
    <I18nProvider initialLocale={locale}>
      <ToastProvider>{children}</ToastProvider>
    </I18nProvider>
  );
}

/** Render a component inside {@link Providers}. */
export function renderWithProviders(
  ui: ReactElement,
  options?: { locale?: Locale },
) {
  const locale = options?.locale;
  return render(ui, {
    wrapper: ({ children }) => <Providers locale={locale}>{children}</Providers>,
  });
}

/** A minimal but structurally-valid backend error envelope. */
export function apiError(
  code: string,
  status = 400,
  details?: unknown,
): ApiError {
  return { status, code, message: code, details };
}

/** GET /guests/directory row (defaults: a returning, non-resident, masked guest). */
export function makeDirectoryRow(
  overrides: Partial<GuestDirectoryRow> = {},
): GuestDirectoryRow {
  return {
    id: 7,
    full_name: "Ali Hassan",
    phone: "0555••••56",
    nationality: "Saudi",
    document_type: "national_id",
    document_number: "••••1234",
    is_active: true,
    is_vip: false,
    is_blocked: false,
    stays_count: 3,
    nights_total: 12,
    first_stay_date: "2026-01-05",
    last_stay_date: "2026-07-10",
    is_repeat: true,
    is_resident: false,
    current_room_number: null,
    current_units_count: 0,
    current_unit: null,
    has_upcoming: false,
    needs_review: false,
    ...overrides,
  };
}

/** R4a/R4c current-unit summary (defaults: one Standard unit "101" on floor "G").
 * Trimmed R4c to the exact four keys the card consumes. */
export function makeCurrentUnit(
  overrides: Partial<GuestCurrentUnit> = {},
): GuestCurrentUnit {
  return {
    room_number: "101",
    room_type_name: "Standard",
    floor_name: "G",
    floor_number: "0",
    ...overrides,
  };
}

/** A central Guest (used by lookup + the edit form). */
export function makeGuest(overrides: Partial<Guest> = {}): Guest {
  return {
    id: 7,
    full_name: "Ali Hassan",
    first_name: "Ali",
    last_name: "Hassan",
    father_name: "",
    mother_name: "",
    phone: "0555000056",
    email: "ali@example.com",
    no_email: false,
    nationality: "Saudi",
    national_id: "1234567890",
    document_type: "national_id",
    document_number: "1234567890",
    date_of_birth: "1990-01-01",
    gender: "male",
    address: "",
    notes: "",
    is_active: true,
    is_vip: false,
    is_blocked: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** GET /guests/<id>/profile (masked document by default). */
export function makeProfile(overrides: Partial<GuestProfile> = {}): GuestProfile {
  return {
    ...makeDirectoryRow(),
    email: "ali@example.com",
    gender: "male",
    date_of_birth: "1990-01-01",
    address: "",
    notes: "",
    vip_marked_at: null,
    vip_marked_by: null,
    blocked_at: null,
    blocked_by: null,
    block_reason: null,
    current: null,
    stays: [],
    needs_review: false,
    upcoming_reservations: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    created_by: null,
    updated_by: null,
    ...overrides,
  };
}

/** GET /guests/<id>/stays row. */
export function makeStayRow(overrides: Partial<GuestStayRow> = {}): GuestStayRow {
  return {
    stay_id: 1,
    status: "checked_out",
    is_checked_out: true,
    check_in_date: "2026-07-01",
    check_out_date: "2026-07-05",
    actual_check_out_at: "2026-07-05T10:00:00Z",
    nights: 4,
    room_number: "R201",
    room_type_name: "Deluxe",
    reservation_id: 10,
    reservation_number: "R00010",
    folio: null,
    ...overrides,
  };
}

/** GET /guests/<id>/reservations row. */
export function makeReservationRow(
  overrides: Partial<GuestReservationRow> = {},
): GuestReservationRow {
  return {
    id: 1,
    reservation_number: "R00001",
    status: "confirmed",
    source: "direct",
    booking_kind: "future",
    check_in_date: "2026-08-01",
    check_out_date: "2026-08-03",
    ...overrides,
  };
}

/** GET /guests/<id>/documents row (masked number by default). */
export function makeDocumentRow(
  overrides: Partial<GuestDocumentRow> = {},
): GuestDocumentRow {
  return {
    id: 1,
    reservation: 10,
    occupant: null,
    doc_type: "national_id",
    number: "••••5678",
    has_front: true,
    has_back: false,
    front_url: null,
    back_url: null,
    expiry_date: "2030-01-01",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

/** GET /guests/<id>/change-log row. */
export function makeChangeLogRow(
  overrides: Partial<GuestChangeLogRow> = {},
): GuestChangeLogRow {
  return {
    id: 1,
    event_number: "E0001",
    event_type: "profile_update",
    category: "profile",
    severity: "info",
    title: "Profile updated",
    message: null,
    actor: "Front Desk",
    occurred_at: "2026-07-01T09:00:00Z",
    created_at: "2026-07-01T09:00:00Z",
    ...overrides,
  };
}

/* ==========================================================================
 * Operations factories (MANDATE WP12 / owner §17). Deterministic fixtures for
 * the three-tab operations UI: housekeeping tasks, maintenance requests, lost &
 * found items, plus the arrival hint, overview counters and room-option feed.
 * ======================================================================== */

/** GET /operations/housekeeping row (defaults: a vacant, unassigned, pending
 * check-out cleaning task with NO upcoming arrival — override per test). */
export function makeHkTask(
  overrides: Partial<HousekeepingTaskListItem> = {},
): HousekeepingTaskListItem {
  return {
    id: 1,
    task_number: "HK00001",
    room: 11,
    room_number: "101",
    stay: null,
    task_type: "checkout_cleaning",
    status: "pending",
    priority: "normal",
    assigned_to: null,
    assigned_to_name: "",
    requested_at: "2026-07-19T08:00:00Z",
    started_at: null,
    completed_at: null,
    service_outcome: "",
    room_type_name: "Standard",
    floor_name: "Ground",
    floor_number: "0",
    is_occupied: false,
    // Housekeeping-only arrival hint — carries a date, NEVER a reservation no.
    upcoming_arrival: { has_upcoming: false, arrival_date: null, arrival_time: null },
    ...overrides,
  };
}

/** GET /operations/maintenance row (defaults: an open, non-blocking, high-priority
 * HVAC request in room 101). */
export function makeMtRequest(
  overrides: Partial<MaintenanceRequestListItem> = {},
): MaintenanceRequestListItem {
  return {
    id: 1,
    request_number: "MT00001",
    room: 11,
    room_number: "101",
    stay: null,
    title: "Broken air conditioner",
    description: "",
    category: "hvac",
    priority: "high",
    status: "open",
    affects_room_availability: false,
    room_block_status: "none",
    assigned_to: null,
    assigned_to_name: "",
    reported_at: "2026-07-19T08:00:00Z",
    started_at: null,
    resolved_at: null,
    closed_at: null,
    ...overrides,
  };
}

/** GET /operations/lost-found row (defaults: a found, non-sensitive item stored
 * in "Safe box A" with no linked guest). */
export function makeLfItem(
  overrides: Partial<LostFoundItemListItem> = {},
): LostFoundItemListItem {
  return {
    id: 1,
    item_number: "LF00001",
    title: "Black leather wallet",
    description: "",
    category: "other",
    status: "found",
    found_at: "2026-07-19T08:00:00Z",
    found_location: "Lobby",
    room: null,
    room_number: "",
    stay: null,
    guest: null,
    guest_name: "",
    found_by_name: "",
    stored_location: "Safe box A",
    claimed_by_name: "",
    returned_at: null,
    ...overrides,
  };
}

/** GET /operations/housekeeping/arrivals-not-ready row. Reservation number is
 * ABSENT by default (housekeeping-only disclosure). */
export function makeArrivalRow(
  overrides: Partial<ArrivalNotReadyRow> = {},
): ArrivalNotReadyRow {
  return {
    room: 11,
    room_number: "101",
    room_status: "dirty",
    occupied: false,
    arrival_date: "2026-07-20",
    ...overrides,
  };
}

/** GET /operations/overview counters (defaults: all zero). */
export function makeOverview(
  overrides: Partial<OperationsOverview> = {},
): OperationsOverview {
  return {
    dirty_rooms: 0,
    hk_pending: 0,
    hk_in_progress: 0,
    open_maintenance: 0,
    rooms_under_maintenance: 0,
    lost_found_open: 0,
    urgent_tasks: 0,
    ...overrides,
  };
}

/** GET /rooms/options row for the async room picker. */
export function makeRoomOption(overrides: Partial<RoomOption> = {}): RoomOption {
  return {
    id: 11,
    number: "101",
    floor_name: "Ground",
    room_type_name: "Standard",
    ...overrides,
  };
}

/** GET /staff row (defaults: an active member) — feeds the assignee pickers. */
export function makeStaffRow(
  overrides: Partial<StaffMemberListItem> = {},
): StaffMemberListItem {
  return {
    id: 1,
    user_id: 501,
    full_name: "Sara Cleaner",
    email: "sara@example.com",
    phone: "",
    membership_type: "staff",
    is_manager: false,
    is_active: true,
    is_primary_manager: false,
    job_title: "Housekeeper",
    staff_code: "HK1",
    permission_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}
