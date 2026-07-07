/**
 * API DTO types for Phase 2 auth/identity endpoints.
 *
 * These mirror the backend's snake_case JSON responses exactly (no transform
 * layer is built yet). They document the shapes the API returns; UI is added
 * in later phases.
 */

export type AccountType = "platform_owner" | "hotel_user";
export type MembershipType = "manager" | "staff";

/** A `section.operation` permission code (e.g. "reservations.view"). */
export type PermissionCode = string;

/** GET /api/auth/me/ → `user` */
export interface CurrentUser {
  id: number;
  email: string;
  full_name: string;
  phone: string;
  avatar_url: string;
  account_type: AccountType;
  is_platform_owner: boolean;
  is_active: boolean;
  date_joined: string;
  last_login: string | null;
}

/** GET /api/auth/me/ → `memberships[]` */
export interface HotelMembershipSummary {
  hotel_id: number;
  hotel_name: string;
  hotel_slug: string;
  membership_type: MembershipType;
  is_primary_manager: boolean;
  is_active: boolean;
}

/** GET /api/auth/context/ and /api/auth/me/ → `current_hotel` */
export interface HotelContext {
  hotel_id: number;
  hotel_name: string;
  hotel_slug: string;
  membership_type: MembershipType;
  is_primary_manager: boolean;
  permissions: PermissionCode[];
}

/** GET /api/auth/me/ */
export interface MeResponse {
  user: CurrentUser;
  memberships: HotelMembershipSummary[];
  current_hotel: HotelContext | null;
}

/** POST /api/auth/token/ */
export interface TokenPair {
  access: string;
  refresh: string;
}

/**
 * Standard DRF PageNumberPagination envelope. Every large list endpoint in
 * later phases returns this shape; the UI paginates via server state (never by
 * loading whole tables, never via localStorage as a source of truth).
 */
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/* ==========================================================================
 * Phase 3 — Platform owner DTOs (mirror /api/v1/platform/ responses).
 * ======================================================================== */

export type HotelStatus = "setup" | "active" | "suspended";
export type BillingCycle = "monthly" | "yearly" | "custom";
export type SubscriptionStatus =
  | "trial"
  | "active"
  | "past_due"
  | "expired"
  | "cancelled";

export interface PrimaryManagerSummary {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
}

export interface HotelSubscriptionSummary {
  id: number;
  plan_id: number;
  plan_name: string;
  status: SubscriptionStatus;
  starts_at: string | null;
  ends_at: string | null;
  trial_ends_at: string | null;
}

export interface Hotel {
  id: number;
  name: string;
  slug: string;
  status: HotelStatus;
  primary_manager: PrimaryManagerSummary | null;
  current_subscription: HotelSubscriptionSummary | null;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionPlan {
  id: number;
  name: string;
  slug: string;
  description: string;
  price: string;
  currency: string;
  billing_cycle: BillingCycle;
  trial_days: number;
  room_limit: number | null;
  user_limit: number | null;
  feature_codes: string[];
  is_active: boolean;
  sort_order: number;
  is_in_use: boolean;
  created_at: string;
  updated_at: string;
}

export interface HotelSubscription {
  id: number;
  hotel: number;
  hotel_name: string;
  plan: number;
  plan_name: string;
  status: SubscriptionStatus;
  starts_at: string | null;
  ends_at: string | null;
  trial_ends_at: string | null;
  cancelled_at: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface PlatformSettings {
  platform_name: string;
  support_email: string;
  support_phone: string;
  support_whatsapp: string;
  website_url: string;
  default_language: "ar" | "en" | "tr";
  default_currency: string;
  default_trial_days: number;
  allow_public_registration: boolean;
  maintenance_mode: boolean;
  updated_at: string;
}

export interface PlatformOverview {
  hotels: {
    total: number;
    active: number;
    setup: number;
    suspended: number;
  };
  subscriptions: {
    active_trials: number;
    active: number;
    expiring_soon: number;
    expired: number;
  };
  recent_hotels: Hotel[];
  recent_subscriptions: HotelSubscription[];
}

/* ==========================================================================
 * Phase 4 — Hotel settings & media DTOs (mirror /api/v1/hotel/ responses).
 * ======================================================================== */

export type MediaKind = "logo" | "cover" | "gallery";

export interface HotelSettings {
  display_name: string;
  legal_name: string;
  short_description: string;
  description: string;
  star_rating: number | null;
  default_language: "ar" | "en" | "tr";
  default_currency: string;
  timezone: string;
  phone: string;
  whatsapp_number: string;
  email: string;
  website_url: string;
  facebook_url: string;
  instagram_url: string;
  social_links: Record<string, string>;
  country: string;
  city: string;
  area: string;
  address_line: string;
  latitude: string | null;
  longitude: string | null;
  map_url: string;
  google_place_id: string;
  location_notes: string;
  check_in_time: string | null;
  check_out_time: string | null;
  cancellation_policy: string;
  child_policy: string;
  pet_policy: string;
  smoking_policy: string;
  extra_bed_policy: string;
  important_notes: string;
  default_booking_status: string;
  allow_public_booking: boolean;
  require_guest_phone: boolean;
  require_guest_document: boolean;
  created_at: string;
  updated_at: string;
}

export interface HotelMedia {
  id: number;
  kind: MediaKind;
  url: string | null;
  alt_text: string;
  sort_order: number;
  is_active: boolean;
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface HotelProfile {
  hotel: { id: number; name: string; slug: string; status: HotelStatus };
  display_name: string;
  city: string;
  country: string;
  logo: HotelMedia | null;
  cover: HotelMedia | null;
  gallery_count: number;
}
