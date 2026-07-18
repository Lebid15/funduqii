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
  Guest,
  GuestChangeLogRow,
  GuestDirectoryRow,
  GuestDocumentRow,
  GuestProfile,
  GuestReservationRow,
  GuestStayRow,
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
    has_upcoming: false,
    needs_review: false,
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
