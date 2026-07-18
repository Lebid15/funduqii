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
  suspension_reason: string;
  status_changed_at: string | null;
  status_changed_by: string | null;
  primary_manager: PrimaryManagerSummary | null;
  current_subscription: HotelSubscriptionSummary | null;
  trial_used: boolean;
  city: string;
  country: string;
  contact_phone: string;
  contact_email: string;
  public_is_listed: boolean;
  public_booking_enabled: boolean;
  rooms_count: number;
  staff_count: number;
  reservations_count: number;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionPlan {
  id: number;
  name: string;
  slug: string;
  description: string;
  price: string;
  price_yearly: string | null;
  currency: string;
  billing_cycle: BillingCycle;
  trial_days: number;
  room_limit: number | null;
  user_limit: number | null;
  max_public_bookings_per_month: number | null;
  feature_codes: string[];
  is_active: boolean;
  is_public: boolean;
  sort_order: number;
  notes: string;
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
  /** Date-derived status — PREFER this over `status` for display. */
  effective_status: SubscriptionStatus;
  /** Frozen copy of the plan's terms at activation time (null on legacy rows). */
  plan_snapshot: Record<string, unknown> | null;
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

/* Phase 16 — platform owner panel completion. */

export interface PlatformDashboard {
  total_hotels: number;
  active_hotels: number;
  setup_hotels: number;
  suspended_hotels: number;
  trial_hotels: number;
  paid_hotels: number;
  expired_subscriptions: number;
  expiring_soon_subscriptions: number;
  total_plans: number;
  public_listed_hotels: number;
  public_booking_enabled_hotels: number;
  /** Estimated recurring revenue per currency — an administrative figure,
   * never "profit" and never a legal financial report. */
  estimated_monthly_recurring_revenue: Record<string, string>;
  revenue_excluded_custom_cycles: number;
  recent_hotels: Hotel[];
  recent_subscription_events: HotelSubscription[];
}

export type PlatformPaymentMethod = "cash" | "bank_transfer" | "manual" | "other";

export interface PlatformPayment {
  id: number;
  hotel: number;
  hotel_name: string;
  subscription: number | null;
  amount: string;
  currency: string;
  method: PlatformPaymentMethod;
  reference: string;
  note: string;
  received_at: string;
  recorded_by: string | null;
  is_voided: boolean;
  voided_at: string | null;
  void_reason: string;
  created_at: string;
}

/** A translatable admin text override — empty strings fall back to the
 * built-in dictionary translation. */
export type I18nText = { ar: string; en: string; tr: string };

export interface PlatformPublicSettings {
  show_home_link: boolean;
  show_hotels_link: boolean;
  show_contact_link: boolean;
  show_book_now_button: boolean;
  show_trial_button: boolean;
  header_home_label: I18nText;
  header_hotels_label: I18nText;
  header_contact_label: I18nText;
  header_book_now_label: I18nText;
  header_trial_label: I18nText;
  hero_title: I18nText;
  hero_subtitle: I18nText;
  hero_primary_button_label: I18nText;
  hero_primary_button_url: string;
  hero_secondary_button_label: I18nText;
  hero_secondary_button_url: string;
  public_phone: string;
  public_whatsapp_display: string;
  public_email: string;
  public_address: string;
  facebook_url: string;
  instagram_url: string;
  website_url: string;
  footer_text: I18nText;
  updated_at: string;
}

/** Snapshot terms carried by a subscription (all values frozen at activation);
 * `price`/`price_yearly` are decimal strings — render as-is, never parseFloat. */
export interface SubscriptionTerms {
  plan_name: string;
  billing_cycle: BillingCycle;
  price: string;
  price_yearly: string | null;
  currency: string;
  room_limit: number | null;
  user_limit: number | null;
  feature_codes: string[];
  max_public_bookings_per_month: number | null;
  trial_days: number;
}

export type EntitlementState =
  | "normal"
  | "nearing_limit"
  | "limit_reached"
  | "over_limit";

/** One measured dimension (rooms/staff/public bookings): current usage against
 * the plan limit. `limit`/`remaining` are null when the dimension is unlimited. */
export interface EntitlementDimension {
  usage: number;
  limit: number | null;
  remaining: number | null;
  state: EntitlementState;
}

export interface EntitlementSummary {
  rooms: EntitlementDimension;
  staff: EntitlementDimension;
  public_bookings: EntitlementDimension;
  features: string[];
}

/** One row of the hotel's own billing history — safe fields only (no ids). */
export interface SubscriptionStatePayment {
  amount: string;
  currency: string;
  method: PlatformPaymentMethod;
  received_at: string;
  is_voided: boolean;
}

export interface HotelSubscriptionState {
  has_subscription: boolean;
  status: SubscriptionStatus | null;
  /** Date-derived status — PREFER this over `status` for display. */
  effective_status: SubscriptionStatus | null;
  plan_name: string | null;
  /** The live subscription's start date (§8.3). Null when there is no live sub. */
  starts_at: string | null;
  /** Trial end date — only set for a trial subscription, else null. */
  trial_ends_at: string | null;
  ends_at: string | null;
  days_left: number | null;
  expiring_soon: boolean;
  expired: boolean;
  suspended: boolean;
  write_blocked: boolean;
  blocked_reason: "hotel_suspended" | "subscription_inactive" | null;
  terms: SubscriptionTerms | null;
  entitlements: EntitlementSummary;
  payments: SubscriptionStatePayment[];
}

// --- Subscription change requests (§8.4/§8.5) --------------------------------

export type ChangeRequestKind = "new_subscription" | "renewal" | "plan_change";

export type ChangeRequestStatus =
  | "under_review"
  | "accepted"
  | "rejected"
  | "cancelled"
  | "executed";

/** Per-hotel state of a plan in the hotel's available-plans grid. */
export type AvailablePlanState =
  | "current"
  | "upgradeable"
  | "available"
  | "unavailable";

/** One plan row for the hotel plan grid: flat plan fields + per-hotel state.
 * `price`/`price_yearly` are decimal strings — render as-is, never parseFloat. */
export interface AvailablePlan {
  id: number;
  name: string;
  slug: string;
  description: string;
  price: string;
  price_yearly: string | null;
  currency: string;
  billing_cycle: BillingCycle;
  trial_days: number;
  room_limit: number | null;
  user_limit: number | null;
  max_public_bookings_per_month: number | null;
  feature_codes: string[];
  sort_order: number;
  state: AvailablePlanState;
  requestable: boolean;
  request_kind: ChangeRequestKind | null;
}

export interface AvailablePlansResponse {
  plans: AvailablePlan[];
  can_request_renewal: boolean;
  current_plan_id: number | null;
}

/** A hotel-initiated subscription change request (hotel-safe view). */
export interface SubscriptionChangeRequest {
  id: number;
  kind: ChangeRequestKind;
  kind_display: string;
  status: ChangeRequestStatus;
  status_display: string;
  requested_plan: number | null;
  requested_plan_name: string | null;
  current_plan_name: string | null;
  hotel_note: string;
  admin_note: string;
  decided_at: string | null;
  executed_at: string | null;
  resulting_subscription: number | null;
  created_at: string;
  updated_at: string;
}

/** Owner review view — adds hotel + actor context. */
export interface PlatformChangeRequest extends SubscriptionChangeRequest {
  hotel: number;
  hotel_name: string;
  requested_by: string | null;
  decided_by: string | null;
}

/** GET /api/v1/public/plans/ → one public (active + public) plan card. */
export interface PublicPlan {
  id: number;
  name: string;
  slug: string;
  description: string;
  price: string;
  price_yearly: string | null;
  currency: string;
  billing_cycle: BillingCycle;
  trial_days: number;
  room_limit: number | null;
  user_limit: number | null;
  feature_codes: string[];
}

/* ==========================================================================
 * Phase 4 — Hotel settings & media DTOs (mirror /api/v1/hotel/ responses).
 * ======================================================================== */

export type MediaKind = "logo" | "cover" | "gallery";

export type FacilityType =
  | "hotel"
  | "apartments"
  | "resort"
  | "motel"
  | "guesthouse"
  | "other";

/** A settings section key (§9.1 typed groups) — matches the backend registry. */
export type SettingsSection =
  | "identity"
  | "localization"
  | "contact"
  | "location"
  | "policies"
  | "operational"
  | "public";

/** One append-only settings audit row (§9.17). */
export interface SettingsAuditLog {
  id: number;
  scope: "hotel" | "platform";
  section: string;
  actor: string | null;
  changes: Record<string, { old: unknown; new: unknown }>;
  reason: string;
  created_at: string;
}

export interface HotelSettings {
  display_name: string;
  legal_name: string;
  facility_type: FacilityType;
  short_description: string;
  description: string;
  star_rating: number | null;
  default_language: "ar" | "en" | "tr";
  default_currency: string;
  /** Accepted PAYMENT currencies (RESERVATIONS-FORM-REWORK). Multi-currency
   * lives at the payment layer only; the reservation/folio currency stays
   * `default_currency`. An EMPTY list means only `default_currency` is accepted
   * (which is always implicitly accepted). Each entry is a 3-letter ISO code. */
  accepted_currencies: string[];
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
  housekeeping_inspection_required: boolean;
  restaurant_enabled: boolean;
  cafe_enabled: boolean;
  public_is_listed: boolean;
  public_slug: string | null;
  public_booking_requires_confirmation: boolean;
  public_min_nights: number | null;
  public_max_nights: number | null;
  public_terms_text: string;
  public_sort_order: number;
  public_featured: boolean;
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
  subscription_state: HotelSubscriptionState;
}

/* ==========================================================================
 * Phase 5 — Floors / room types / rooms DTOs (mirror /api/v1/hotel/).
 * ======================================================================== */

export type RoomStatus =
  | "available"
  | "dirty"
  | "cleaning"
  | "maintenance"
  | "out_of_service"
  | "archived";

export interface Floor {
  id: number;
  name: string;
  number: string;
  description: string;
  sort_order: number;
  is_active: boolean;
  room_count: number;
  created_at: string;
  updated_at: string;
}

export interface RoomType {
  id: number;
  name: string;
  code: string;
  description: string;
  base_capacity: number;
  max_capacity: number;
  bed_type: string;
  amenities: string[];
  base_rate: string | null;
  is_active: boolean;
  sort_order: number;
  public_is_visible: boolean;
  public_name: string;
  public_description: string;
  public_base_price: string | null;
  public_sort_order: number;
  room_count: number;
  created_at: string;
  updated_at: string;
}

export interface Room {
  id: number;
  number: string;
  display_name: string;
  floor: number;
  floor_name: string;
  room_type: number;
  room_type_name: string;
  room_type_code: string;
  base_capacity: number;
  max_capacity: number;
  status: RoomStatus;
  status_note: string;
  status_changed_at: string | null;
  status_changed_by: string | null;
  is_active: boolean;
  /* ROOMS §6.1 per-room feature overrides. Returned by RoomSerializer on BOTH
   * the list and single-room DETAIL responses (`/rooms/` and GET/PATCH/PUT
   * `/rooms/<id>/`). `feature_additions` / `feature_exclusions` are writable;
   * `effective_features` (type defaults − exclusions + additions) and
   * `inherited_features` (the room type's own amenities) are read-only. They are
   * optional here only because the board-derived Room objects (built from
   * RoomBoardRoom) do not carry them. */
  feature_additions?: string[];
  feature_exclusions?: string[];
  effective_features?: string[];
  inherited_features?: string[];
  created_at: string;
  updated_at: string;
}

/* --- Rooms operational board (owner task) — READ-ONLY aggregation ---------- */

/** Computed for DISPLAY only — `occupied`/`reserved` are derived from stays
 * and blocking reservations, never stored on the room. */
export type RoomDisplayStatus = RoomStatus | "occupied" | "reserved";

/** Occupancy axis (independent from the operational status): derived purely
 * from real in-house stays / covering reservations. */
export type RoomOccupancyStatus = "free" | "occupied" | "reserved";

export interface RoomBoardStay {
  id: number;
  guest_name: string;
  planned_check_out_date: string;
  reservation_id: number | null;
  reservation_number: string | null;
}

export interface RoomBoardReservation {
  id: number;
  reservation_number: string;
  guest_name: string;
  status: string;
  check_in_date: string;
  check_out_date: string;
}

export interface RoomBoardRoom {
  id: number;
  number: string;
  display_name: string;
  floor: number;
  floor_name: string;
  room_type: number;
  room_type_name: string;
  room_type_code: string;
  base_capacity: number;
  max_capacity: number;
  base_rate: string | null;
  /** ROOMS §6.1: the room's EFFECTIVE feature keys — the room type's amenities
   * with this room's `feature_exclusions` removed and `feature_additions` added
   * (deduped, ordered). The field NAME is unchanged for compatibility, but the
   * VALUE is now per-room effective (not the raw room-type list). Empty when the
   * room has no effective features. */
  amenities: string[];
  is_active: boolean;
  operational_status: RoomStatus;
  /** Independent occupancy axis (free / occupied / reserved). */
  occupancy_status: RoomOccupancyStatus;
  /** True only when the room is bookable right now (every gate open on both
   * axes). Drives the "Available now" card + filter. */
  available_now: boolean;
  floor_is_active: boolean;
  room_type_is_active: boolean;
  /** Kept only for buildRoomLinks + the calm card-accent tone (compat). */
  display_status: RoomDisplayStatus;
  status_note: string;
  status_changed_at: string | null;
  current_stay: RoomBoardStay | null;
  next_reservation: RoomBoardReservation | null;
}

export interface RoomBoardCounts {
  total: number;
  available: number;
  /** Explicit alias of `available` on the bookable-now axis. */
  available_now: number;
  occupied: number;
  reserved: number;
  dirty: number;
  cleaning: number;
  maintenance: number;
  out_of_service: number;
  /** dirty + cleaning + maintenance + out_of_service ("Needs action"). */
  attention: number;
}

export interface RoomBoardFloor extends RoomBoardCounts {
  id: number;
  name: string;
  number: string;
  is_active: boolean;
  availability_rate: number;
}

export interface RoomOperationalBoard {
  /** The hotel's currency (e.g. "USD"/"SAR"/"TRY") — the single source for
   * every price rendered across the rooms section and the room-type form. */
  currency: string;
  summary: RoomBoardCounts;
  floors: RoomBoardFloor[];
  rooms: RoomBoardRoom[];
}

/** One room in a bulk-create request (POST /rooms/bulk/). */
export interface RoomBulkRow {
  number: string;
  display_name?: string;
  floor: number;
  room_type: number;
  is_active?: boolean;
  initial_status?: RoomStatus;
  status_note?: string;
}

export interface RoomBulkCreateBody {
  rooms: RoomBulkRow[];
}

export interface RoomBulkCreateResponse {
  created_count: number;
  rooms: Room[];
}

/* ==========================================================================
 * Phase 6 — Reservations & availability DTOs (mirror /api/v1/hotel/).
 * ======================================================================== */

export type ReservationStatus = "held" | "confirmed" | "cancelled" | "expired";
/** Derived reservation payment state (§31/§35): unpaid / partial / paid. Null
 * when the caller may not see money (masked server-side by finance.view). */
export type ReservationPaymentStatus = "unpaid" | "partial" | "paid";
export type ReservationSource =
  | "direct"
  | "phone"
  | "walk_in"
  | "public_website"
  | "other";

export interface ReservationLine {
  id: number;
  room_type: number;
  room_type_name: string;
  room_type_code: string;
  max_capacity: number;
  room: number | null;
  room_number: string | null;
  /** Floor of the SPECIFIC assigned room (null when the line has no room).
   * `floor_number` mirrors Floor.number (a CharField), so it is a string. */
  floor_name: string | null;
  floor_number: string | null;
  quantity: number;
  adults: number | null;
  children: number | null;
  notes: string;
}

export type BookingKind = "instant" | "future";

export type ExpectedPaymentMethod = "" | "cash" | "card" | "bank_transfer" | "other";

export interface Reservation {
  id: number;
  reservation_number: string;
  status: ReservationStatus;
  source: ReservationSource;
  booking_kind: BookingKind;
  check_in_date: string;
  check_out_date: string;
  expected_arrival_time: string | null;
  nights: number;
  /** Optional link to the central guest directory (id only). */
  primary_guest: number | null;
  primary_guest_name: string;
  primary_guest_phone: string;
  primary_guest_email: string;
  primary_guest_nationality: string;
  primary_guest_document_type: string;
  primary_guest_document_number: string;
  /** RESERVATIONS-FORM-REWORK — the frozen, structured identity snapshot the
   * read serializer returns alongside the legacy fields. `primary_guest_national_id`
   * is masked server-side for callers without `guests.view_sensitive_data`
   * (bullet characters), exactly like `primary_guest_document_number`. */
  primary_guest_first_name: string;
  primary_guest_last_name: string;
  primary_guest_father_name: string;
  primary_guest_mother_name: string;
  primary_guest_national_id: string;
  primary_guest_date_of_birth: string | null;
  adults: number;
  children: number;
  total_guests: number;
  notes: string;
  special_requests: string;
  booking_channel_name: string;
  expected_payment_method: ExpectedPaymentMethod;
  cancellation_reason: string;
  cancelled_at: string | null;
  hold_expires_at: string | null;
  public_cancel_requested_at: string | null;
  public_cancel_reason: string;
  /** Post-check-in guard: the guest is in-house — dates/rooms frozen and
   * cancel refused (the stay is the source of truth). */
  has_in_house_stay: boolean;
  /** §25 — the LATEST related stay's status (in_house / checked_out /
   * cancelled) or null when the booking never checked in. Distinguishes a
   * departed guest from one who never arrived; complements `has_in_house_stay`. */
  stay_status: StayStatus | null;
  stay_id: number | null;
  /** §37 — DERIVED count of the reservation's uploaded documents (never stored;
   * `len` of the prefetched relation). Drives the card's "View documents" button:
   * it only appears when this is > 0, with the count on a badge. */
  document_count: number;
  /** §26/§31/§35 — DERIVED financial read (never stored). The money fields are
   * gated by `finance.view` and come back null when the caller may not see
   * money; `currency`/`nights` are always present. Money values are decimal
   * strings — render as-is, never parseFloat. */
  nightly_rate: string | null;
  reservation_total: string | null;
  currency: string;
  paid: string | null;
  remaining: string | null;
  payment_status: ReservationPaymentStatus | null;
  /** False when a selected room type has no `base_rate` (unpriced); null when
   * money is hidden. */
  is_priced: boolean | null;
  created_by: string | null;
  /** Creator display name (full_name, else email, else null). */
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
  lines: ReservationLine[];
  /** Named adult companions (RESERVATIONS-FORM-REWORK). Optional so existing
   * callers never break; the reservation serializer returns them in creation
   * order, which the wizard uses to attach staged documents to the right
   * occupant after create. */
  occupants?: ReservationOccupant[];
}

export interface TypeAvailability {
  room_type: number;
  room_type_name: string;
  room_type_code: string;
  base_capacity: number;
  max_capacity: number;
  total_rooms: number;
  blocked_rooms: number;
  reserved_quantity: number;
  available_quantity: number;
  can_book: boolean;
  reason: string | null;
}

export interface ReservationOverview {
  total: number;
  held: number;
  confirmed: number;
  cancelled: number;
  expired: number;
  /** Count of reservations whose `source` is `public_website` (hotel-scoped).
   * A SOURCE subset — already distributed across the status counts above, not a
   * status of its own; never summed into the status math. */
  website: number;
  /** The hotel's operational "today" — the create wizard defaults the arrival
   * date to this, and it derives instant-vs-future (client clocks can differ). */
  business_date: string;
  arrivals: Reservation[];
  departures: Reservation[];
}

export interface ReservationStatusLogEntry {
  previous_status: string;
  new_status: string;
  note: string;
  changed_by: string | null;
  created_at: string;
}

/* ==========================================================================
 * Phase 7 — Guests, check-in & check-out DTOs (mirror /api/v1/hotel/).
 * ======================================================================== */

export type DocumentType =
  | ""
  | "national_id"
  | "passport"
  | "driving_license"
  | "other";
export type Gender = "" | "male" | "female" | "other" | "unspecified";

export interface Guest {
  id: number;
  full_name: string;
  /** Structured identity (RESERVATIONS-FORM-REWORK). Optional here so existing
   * callers never break; the backend GuestSerializer always returns them. */
  first_name?: string;
  last_name?: string;
  father_name?: string;
  mother_name?: string;
  phone: string;
  email: string;
  /** True when the guest explicitly has no email (skips the email requirement). */
  no_email?: boolean;
  nationality: string;
  /** Structured national ID — masked for callers without
   * `guests.view_sensitive_data` (like `document_number`). */
  national_id?: string;
  document_type: DocumentType;
  document_number: string;
  date_of_birth: string | null;
  gender: Gender;
  address: string;
  notes: string;
  is_active: boolean;
  is_vip: boolean;
  is_blocked: boolean;
  created_at: string;
  updated_at: string;
}

/** DELETE /guests/<id> — delete hardening distinguishes the outcomes. */
export interface GuestDeleteResult {
  result: "deleted" | "deactivated";
  guest?: Guest;
}

/** GET /guests/directory — a directory row with derived stats. */
export interface GuestDirectoryRow {
  id: number;
  full_name: string;
  phone: string;
  nationality: string;
  document_type: DocumentType;
  document_number: string;
  is_active: boolean;
  is_vip: boolean;
  is_blocked: boolean;
  stays_count: number;
  nights_total: number;
  first_stay_date: string | null;
  last_stay_date: string | null;
  is_repeat: boolean;
  is_resident: boolean;
  current_room_number: string | null;
}

/** GET /guests/<id>/profile — one stay-history row (read-only). */
export interface GuestProfileStay {
  stay_id: number;
  status: StayStatus;
  is_current: boolean;
  reservation_id: number | null;
  reservation_number: string | null;
  room_number: string;
  room_type_name: string;
  check_in_date: string;
  check_out_date: string;
  actual_check_out_at: string | null;
  nights: number;
  folio_id: number | null;
  folio_number: string | null;
  folio_status: string | null;
}

/** GET /guests/<id>/profile — the central read-only profile. */
export interface GuestProfile extends GuestDirectoryRow {
  email: string;
  gender: Gender;
  date_of_birth: string | null;
  address: string;
  notes: string;
  vip_marked_at: string | null;
  vip_marked_by: string | null;
  blocked_at: string | null;
  blocked_by: string | null;
  /** Only present for holders of guests.block. */
  block_reason: string | null;
  current: {
    stay_id: number;
    room_number: string;
    reservation_id: number | null;
    reservation_number: string | null;
    folio_id: number | null;
    folio_number: string | null;
    folio_status: string | null;
  } | null;
  stays: GuestProfileStay[];
  /** GUESTS-CLOSURE central identity — true when this profile still needs staff
   * review (e.g. an unresolved identity signal). Backend-derived. */
  needs_review: boolean;
  /** GUESTS-CLOSURE — the guest's forthcoming reservations (summary rows). Shape
   * mirrors GuestReservationRow. */
  upcoming_reservations: GuestReservationRow[];
  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
}

/* --- GUESTS-CLOSURE central-identity paginated sub-resources ---------------- *
 * Additive rows for the four paginated guest sub-lists the UI wave (W6) renders.
 * All four are DRF PageNumberPagination envelopes (`PaginatedResponse<Row>`). */

/** GET guests/<pk>/stays/ — one paginated stay row (central identity view). */
export interface GuestStayRow {
  stay_id: number;
  status: StayStatus;
  is_checked_out: boolean;
  check_in_date: string;
  check_out_date: string;
  actual_check_out_at: string | null;
  nights: number;
  room_number: string;
  room_type_name: string;
  reservation_id: number | null;
  reservation_number: string | null;
  /** The stay's folio subset, or null when no folio exists. */
  folio: {
    id: number;
    folio_number: string;
    status: FolioStatus;
  } | null;
}

/** GET guests/<pk>/reservations/ — one paginated reservation summary row. */
export interface GuestReservationRow {
  id: number;
  reservation_number: string;
  status: ReservationStatus;
  source: ReservationSource;
  booking_kind: BookingKind;
  check_in_date: string;
  check_out_date: string;
}

/** GET guests/<pk>/documents/ — one paginated document row. Behind BOTH
 * guests.view AND reservation_documents.view. `number` is masked (bullet
 * characters) unless the viewer holds guests.view_sensitive_data — treat it as
 * display-only (see `isMaskedValue`). `front_url`/`back_url` point at the
 * existing reservation signed-url mint and are null when no file is stored. */
export interface GuestDocumentRow {
  id: number;
  reservation: number;
  occupant: number | null;
  doc_type: ReservationDocumentType;
  number: string;
  has_front: boolean;
  has_back: boolean;
  front_url: string | null;
  back_url: string | null;
  expiry_date: string | null;
  created_at: string;
  updated_at: string;
}

/** GET guests/<pk>/change-log/ — one paginated change-event row. `message` is
 * null unless the viewer holds guests.block (block-event detail is gated).
 * `event_type` / `category` / `severity` are stable backend strings. */
export interface GuestChangeLogRow {
  id: number;
  event_number: string;
  event_type: string;
  category: string;
  severity: string;
  title: string;
  message: string | null;
  actor: string | null;
  occurred_at: string;
  created_at: string;
}

export type StayStatus = "in_house" | "checked_out" | "cancelled";
export type StayGuestRole = "primary" | "companion";

export interface StayGuestLink {
  id: number;
  guest: number;
  guest_name: string;
  role: StayGuestRole;
}

export interface Stay {
  id: number;
  reservation: number | null;
  reservation_number: string | null;
  reservation_line: number | null;
  room: number;
  room_number: string;
  room_type_name: string;
  primary_guest: number;
  primary_guest_name: string;
  primary_guest_is_vip: boolean;
  status: StayStatus;
  planned_check_in_date: string;
  planned_check_out_date: string;
  actual_check_in_at: string;
  actual_check_out_at: string | null;
  nights: number;
  check_in_notes: string;
  check_out_notes: string;
  checkout_reason: string;
  checked_in_by: string | null;
  checked_out_by: string | null;
  guests: StayGuestLink[];
  /** Count of the linked reservation's documents (§13) — 0 for a walk-in. */
  document_count: number;
  /**
   * Operational-card finance block (§12) — present only on the front-desk
   * resident/departure lists. A DISCRIMINATED UNION on `financial_details_visible`:
   * a finance viewer (`finance.view`) gets the full monetary block; every other
   * viewer gets only abstract operational clearance states (no amounts, currency,
   * folio number or payment status). Null when the stay has no open folio.
   * Derived from the folio ledger; the client never recomputes it.
   */
  folio_summary?: StayFolioCardSummary | null;
  /**
   * STAYS rate-integrity remediation — an OPERATIONAL flag (NOT finance-gated):
   * true when an in-house stay has a DUE/consumed billable night with no
   * positive-rate coverage (a "stuck" stay). Such a stay blocks check-out and its
   * folio must never be shown as settled/zero; a `stays.rate_override` holder can
   * remediate it via POST /stays/<id>/remediate-rate/. Backend-derived — never
   * recomputed on the client.
   */
  requires_rate_remediation: boolean;
  created_at: string;
  updated_at: string;
}

/** One CONTIGUOUS gap of consumed nights lacking a positive rate — half-open
 * `[start_date, end_date)` (end EXCLUSIVE), split at the planned-check-out
 * boundary so each range is entirely within-plan or entirely overstay. This is
 * NEVER the whole stay: it is the exact window the remediation form defaults to. */
export interface MissingRateRange {
  start_date: string;
  end_date: string;
}

/**
 * STAYS rate-integrity — the OPERATIONAL rate-coverage block (dates + flags, NOT
 * money) merged into EVERY stay folio summary (card + checkout) for EVERY viewer,
 * never gated behind `finance.view`. Backend-derived — never recomputed here.
 */
export interface RateCoverageFields {
  /** True when any consumed billable night lacks positive-rate coverage. */
  requires_rate_remediation: boolean;
  /** The specific contiguous uncovered windows (end exclusive); empty when covered. */
  missing_rate_ranges: MissingRateRange[];
  /** True when a within-plan gap exists (directly remediable). */
  remediation_allowed: boolean;
  /** True when an overstay gap (at/after planned check-out) exists — the stay must
   * be EXTENDED first before those nights can be priced. */
  requires_extension_first: boolean;
}

/**
 * Operational-card finance block (§12) — a DISCRIMINATED UNION on
 * `financial_details_visible`. A finance viewer receives the full monetary
 * block; every other viewer receives ONLY abstract operational clearance states.
 * The monetary fields are OMITTED for a non-finance viewer (never zeroed), so
 * the UI can never print `0` for a hidden value. Both variants also carry the
 * OPERATIONAL `RateCoverageFields` (dates/flags, not money).
 */
export type StayFolioCardSummary =
  | StayFolioCardSummaryVisible
  | StayFolioCardSummaryHidden;

/** Finance viewer — full monetary detail (backend derives it from the ledger). */
export interface StayFolioCardSummaryVisible extends RateCoverageFields {
  financial_details_visible: true;
  folio_number: string;
  currency: string;
  total_charges: string;
  total_payments: string;
  balance: string;
  /** Derived from the folio's own totals (§12). `overpaid` = credit/refund-due. */
  payment_status: "paid" | "partial" | "unpaid" | "overpaid";
  awaiting_final_charges: boolean;
  /** The stay's CURRENT nightly rate (the latest rate period's rate/currency —
   * the value an extension defaults from) so the extend dialog can SHOW it.
   * finance.view ONLY; NULL when the stay has no rate period. Backend-derived —
   * NEVER recomputed on the client. */
  current_nightly_rate: string | null;
  current_rate_currency: string | null;
}

/** Non-finance viewer — abstract operational states only (no money at all). */
export interface StayFolioCardSummaryHidden extends RateCoverageFields {
  financial_details_visible: false;
  /** True when balance is zero, no folio awaits final charges, no insurance held. */
  financial_clearance_complete: boolean;
  /** True when the account still needs a finance action before departure. */
  requires_financial_action: boolean;
}

/**
 * GET /stays/<id>/folio-summary and POST /stays/<id>/ensure-room-charges — the
 * check-out dialog context. A DISCRIMINATED UNION on `financial_details_visible`.
 * The base fields (including the backend-authoritative `can_check_out`) are
 * always present; a finance viewer additionally receives the monetary block
 * (balances, insurances). A non-finance viewer receives a money-free
 * `open_folios` skeleton and no balance/insurance fields — they are OMITTED,
 * never zeroed.
 */
export type StayFolioSummary = StayFolioSummaryVisible | StayFolioSummaryHidden;

interface StayFolioSummaryBase extends RateCoverageFields {
  business_date: string;
  is_early_departure: boolean;
  has_folio: boolean;
  /** True when balance is zero, nothing awaits final charges, no insurance held. */
  financial_clearance_complete: boolean;
  /** True when a finance action is still required before departure. */
  requires_financial_action: boolean;
  /** Backend-authoritative checkout readiness — the UI gates the confirm button
   * on this (NOT a money-derived flag), so a non-finance actor can still depart a
   * financially-cleared stay. */
  can_check_out: boolean;
  /** True when any open folio is still flagged awaiting final charges (§32). */
  awaiting_final_charges: boolean;
}

/** Finance viewer — full monetary detail. */
export interface StayFolioSummaryVisible extends StayFolioSummaryBase {
  financial_details_visible: true;
  open_folios: {
    id: number;
    folio_number: string;
    status: string;
    currency: string;
    balance: string;
    awaiting_final_charges: boolean;
    awaiting_final_charges_note: string;
  }[];
  /** Total balance across the stay's OPEN folios ("0" when settled/none). */
  balance: string;
  /** Refundable insurance held against the stay (§35). */
  insurances: {
    id: number;
    currency: string;
    amount: string;
    deducted_amount: string;
    refunded_amount: string;
    held_amount: string;
    status: "held" | "refunded" | "partially_deducted" | "consumed";
  }[];
  /** True when any insurance still has a held amount awaiting settlement. */
  insurance_pending: boolean;
  /** The stay's CURRENT nightly rate (latest rate period rate/currency — the
   * value an extension defaults from) so the extend dialog can SHOW it.
   * finance.view ONLY; NULL when the stay has no rate period. Backend-derived —
   * NEVER recomputed on the client. */
  current_nightly_rate: string | null;
  current_rate_currency: string | null;
}

/** Non-finance viewer — money-free operational skeleton. Item 10: NO folio list
 * (`open_folios`) at all — it leaked internal financial identifiers (folio id +
 * folio_number). Only the abstract operational states on the base survive; no
 * amount, currency, folio number, or nightly rate is ever sent. */
export interface StayFolioSummaryHidden extends StayFolioSummaryBase {
  financial_details_visible: false;
}

/** GET /stays/check-in-rooms and /stays/<id>/move-candidates. */
export interface AdmissibleRoom {
  id: number;
  number: string;
  room_type_name?: string;
  max_capacity?: number;
}

export interface StayStatusLogEntry {
  previous_status: string;
  new_status: string;
  note: string;
  changed_by: string | null;
  created_at: string;
}

/* ==========================================================================
 * RESERVATIONS-FORM-REWORK — occupants, guest documents, per-room availability,
 * guest lookup, and the immediate atomic check-in (deposit/FX). These mirror the
 * additive backend endpoints under /api/v1/hotel/. Money values are decimal
 * STRINGS — render as-is, never parseFloat.
 * ======================================================================== */

/** How an ADULT companion relates to the primary guest (write set). The read
 * DTO widens this with "" because a stored occupant may have no relationship. */
export type OccupantRelationship =
  | "spouse"
  | "child_adult"
  | "parent"
  | "sibling"
  | "relative"
  | "other";

/** GET reservation → `occupants[]`. One adult companion (structured snapshot,
 * optionally linked to a central Guest). `national_id` is masked for callers
 * without `guests.view_sensitive_data`. Children stay a count on the reservation. */
export interface ReservationOccupant {
  id: number;
  guest: number | null;
  first_name: string;
  last_name: string;
  father_name: string;
  mother_name: string;
  national_id: string;
  nationality: string;
  date_of_birth: string | null;
  relationship: OccupantRelationship | "";
  created_at: string;
}

export type ReservationDocumentType =
  | ""
  | "national_id"
  | "passport"
  | "residence"
  | "visa"
  | "marriage_contract"
  | "family_book"
  | "family_statement"
  | "other";

/** GET reservations/<id>/documents/ → metadata ONLY (the raw files are never
 * exposed here — only `has_front`/`has_back`). `number` is masked for callers
 * without `guests.view_sensitive_data`. Behind `reservation_documents.view`. */
export interface ReservationDocument {
  id: number;
  reservation: number;
  occupant: number | null;
  doc_type: ReservationDocumentType;
  number: string;
  has_front: boolean;
  has_back: boolean;
  created_at: string;
  updated_at: string;
}

/** GET reservations/room-availability/ → one candidate room for the period.
 * `available` is backend-authoritative (the UI never decides bookability
 * itself); `base_rate` is a decimal string (or null) — render as-is. */
export interface RoomAvailabilityRow {
  id: number;
  number: string;
  floor_name: string | null;
  floor_number: string | null;
  room_type_id: number;
  room_type_name: string;
  base_capacity: number;
  max_capacity: number;
  amenities: string[];
  base_rate: string | null;
  currency: string;
  available: boolean;
}

/** GET guests/lookup/ → exact-match candidates for the reservation form. Each
 * `Guest` may be blocked/VIP and has its `national_id` masked per permission. */
export interface GuestLookupResult {
  results: Guest[];
}

/** Deposit payment method for an immediate check-in — validated against the
 * finance payment methods server-side (a separate union from the folio
 * `PaymentMethod` so adding it here never widens existing finance switches). */
export type ReservationDepositMethod =
  | "cash"
  | "card"
  | "bank_transfer"
  | "electronic"
  | "internal_electronic"
  | "other";

/** Optional pre-arrival deposit on an immediate check-in. A base-currency
 * deposit sends `amount`; a foreign-currency deposit instead sends
 * `original_amount` + `exchange_rate` (+ optional `rate_basis`) and the backend
 * DERIVES the base amount (single ledger — nothing stored twice). Money fields
 * are decimal strings. A manual FX rate requires `exchange_rate.override`. */
export interface ReservationDepositBody {
  amount?: string | null;
  method: ReservationDepositMethod;
  currency?: string;
  original_amount?: string | null;
  exchange_rate?: string | null;
  rate_basis?: string;
  payer_name?: string;
  reference?: string;
  notes?: string;
}

/** GET reservations/<id>/financial-summary/ (§26/§31/§35/§39). A DERIVED read,
 * never stored. The money block is gated by `finance.view`: when
 * `can_view_money` is false every money field is null and `payments` is empty
 * (masked server-side). All money values are decimal strings — render as-is. */
export interface ReservationFinancialSummary {
  reservation: number;
  reservation_number: string;
  currency: string;
  nights: number;
  is_priced: boolean | null;
  can_view_money: boolean;
  nightly_rate: string | null;
  reservation_total: string | null;
  paid: string | null;
  remaining: string | null;
  payment_status: ReservationPaymentStatus | null;
  /** RESERVATIONS-FINAL-CLOSURE §1 — true once a stay exists; the account has
   * moved to the folio. When true, paid/remaining/payment_status are null and
   * `folio_balance` carries the real current balance from the central folio. */
  has_stay: boolean;
  folio_balance: string | null;
  payments: Payment[];
}

/** POST reservations/<id>/payments/ (§27) → the recorded pre-arrival deposit
 * plus the refreshed derived financial summary. */
export interface ReservationDepositResult {
  payment: Payment;
  financial_summary: ReservationFinancialSummary;
}

/** The folio subset returned by an immediate check-in (null when no folio was
 * opened, e.g. no deposit). `balance` is a DERIVED decimal string. */
export interface ImmediateCheckInFolio {
  id: number;
  folio_number: string;
  status: FolioStatus;
  currency: string;
  balance: string;
}

/** POST stays/immediate-check-in/ → the composed atomic result (reservation +
 * stay + optional folio). */
export interface ImmediateCheckInResult {
  reservation: Reservation;
  stay: Stay;
  folio: ImmediateCheckInFolio | null;
}

/* ==========================================================================
 * Phase 8 — Internal finance DTOs (mirror /api/v1/hotel/finance/).
 * ======================================================================== */

export type FolioStatus = "open" | "closed" | "voided";
export type PostingStatus = "posted" | "voided";
export type InvoiceStatus = "draft" | "issued" | "voided";
export type ChargeType =
  | "room"
  | "service"
  | "tax"
  | "adjustment"
  | "discount"
  | "other";
export type PaymentMethod =
  | "cash"
  | "card"
  | "bank_transfer"
  | "electronic"
  | "other";
export type ExpenseCategory =
  | "operations"
  | "maintenance"
  | "supplies"
  | "marketing"
  | "salary"
  | "utilities"
  | "other";

export interface FolioBalance {
  total_charges: string;
  total_payments: string;
  balance: string;
}

export interface FolioCharge {
  id: number;
  charge_number: string;
  type: ChargeType;
  description: string;
  quantity: string;
  unit_amount: string;
  amount: string;
  tax_rate: string;
  tax_amount: string;
  total_amount: string;
  charge_date: string;
  source: string;
  status: PostingStatus;
  adjusts: number | null;
  adjusts_number: string | null;
  void_reason: string;
  voided_at: string | null;
  voided_by: string | null;
  created_at: string;
}

export interface Payment {
  id: number;
  folio: number;
  folio_number: string;
  reservation_number: string | null;
  receipt_number: string;
  amount: string;
  currency: string;
  method: PaymentMethod;
  status: PostingStatus;
  paid_at: string;
  business_date: string | null;
  /** Multi-currency FX snapshot (§29), surfaced read-only. An empty
   * `payment_currency` means the tender was in the folio/base currency (legacy).
   * `amount`/`currency` above stay the base equivalent. `exchange_rate` is a
   * high-precision decimal string; all money values render as-is. */
  payment_currency: string;
  original_amount: string | null;
  exchange_rate: string | null;
  rate_basis: string;
  rate_captured_at: string | null;
  reverses: number | null;
  reverses_receipt: string | null;
  payer_name: string;
  reference: string;
  notes: string;
  void_reason: string;
  voided_at: string | null;
  voided_by: string | null;
  created_by: string | null;
  created_at: string;
}

export interface Folio {
  id: number;
  folio_number: string;
  status: FolioStatus;
  currency: string;
  reservation: number | null;
  reservation_number: string | null;
  stay: number | null;
  guest: number | null;
  guest_name: string | null;
  customer_name: string;
  notes: string;
  opened_at: string;
  closed_at: string | null;
  void_reason: string;
  voided_at: string | null;
  balance: FolioBalance;
  charges: FolioCharge[];
  payments: Payment[];
  created_at: string;
  updated_at: string;
}

export interface FolioListItem {
  id: number;
  folio_number: string;
  status: FolioStatus;
  currency: string;
  reservation: number | null;
  reservation_number: string | null;
  stay: number | null;
  guest: number | null;
  guest_name: string | null;
  customer_name: string;
  balance: FolioBalance;
  opened_at: string;
  created_at: string;
}

export interface InvoiceLine {
  id: number;
  description: string;
  quantity: string;
  unit_amount: string;
  tax_rate: string;
  tax_amount: string;
  total_amount: string;
  source_charge: number | null;
}

export interface Invoice {
  id: number;
  folio: number;
  folio_number: string;
  reservation_number: string | null;
  invoice_number: string;
  status: InvoiceStatus;
  currency: string;
  issued_at: string | null;
  due_date: string | null;
  subtotal: string;
  tax_total: string;
  total: string;
  balance_at_issue: string;
  customer_name: string;
  customer_phone: string;
  customer_email: string;
  customer_document_number: string;
  notes: string;
  void_reason: string;
  voided_at: string | null;
  lines: InvoiceLine[];
  created_at: string;
}

export interface Expense {
  id: number;
  expense_number: string;
  category: ExpenseCategory;
  description: string;
  amount: string;
  currency: string;
  method: PaymentMethod;
  /** Execution timestamp — the financial date is `business_date`. */
  paid_at: string;
  /** THE financial date of the voucher (null on legacy rows). */
  business_date: string | null;
  shift: number | null;
  shift_number: string | null;
  /** Set when this row is a reversal of another voucher. */
  reverses: number | null;
  reverses_number: string | null;
  /** Set when this voucher has been reversed by a later voucher. */
  reversed_by_number: string | null;
  vendor_name: string;
  reference: string;
  notes: string;
  status: PostingStatus;
  void_reason: string;
  voided_at: string | null;
  voided_by: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface FinanceOverview {
  open_folios: number;
  outstanding_balance: string;
  unpaid_folios: number;
  payments_today: string;
  expenses_today: string;
  net_today: string;
  issued_invoices: number;
  currency: string;
  foreign_currency_folios: {
    count: number;
    currencies: string[];
  };
}

export interface HotelHeader {
  hotel_name: string;
  currency: string;
  phone: string;
  address: string;
}

export interface PrintDocument {
  document: string;
  hotel: HotelHeader;
  payment?: Payment;
  invoice?: Invoice;
  expense?: Expense;
}

export interface FolioStatementStay {
  id: number;
  room_number: string;
  planned_check_in_date: string;
  planned_check_out_date: string;
}

export interface FolioStatement {
  document: string;
  hotel: HotelHeader;
  folio: Folio;
  stay: FolioStatementStay | null;
}

/* ==========================================================================
 * Phase 9 — Service catalog & orders DTOs (mirror /api/v1/hotel/services/).
 * ======================================================================== */

export type ServiceOutlet = "restaurant" | "cafe";
export type ServiceOrderType = "room" | "table";
export type ServiceOrderSettlement = "unsettled" | "direct" | "folio";
export type RestaurantTableStatus = "available" | "out_of_service";
export type ServiceOrderStatus =
  | "draft"
  | "submitted"
  | "preparing"
  | "ready"
  | "delivered"
  | "cancelled";

export interface ServiceCategory {
  id: number;
  outlet: ServiceOutlet;
  name: string;
  code: string;
  description: string;
  sort_order: number;
  is_active: boolean;
  item_count: number;
  created_at: string;
  updated_at: string;
}

export interface ServiceItem {
  id: number;
  category: number;
  category_name: string;
  /** Read-only, derived from the item's category. */
  outlet: ServiceOutlet;
  name: string;
  code: string;
  description: string;
  unit_price: string;
  currency: string;
  tax_rate: string;
  is_available: boolean;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface RestaurantTableOpenOrder {
  id: number;
  order_number: string;
  status: ServiceOrderStatus;
  customer_name: string;
  guest_name: string;
}

export interface RestaurantTable {
  id: number;
  outlet: ServiceOutlet;
  number: string;
  name: string;
  capacity: number;
  status: RestaurantTableStatus;
  status_note: string;
  /** Derived: the table has one open (unsettled, not cancelled) order. */
  is_occupied: boolean;
  open_order: RestaurantTableOpenOrder | null;
  created_at: string;
  updated_at: string;
}

export interface ServiceOrderItem {
  id: number;
  service_item: number | null;
  item_name: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
  amount: string;
  tax_amount: string;
  total_amount: string;
  notes: string;
  is_cancelled: boolean;
  cancelled_at: string | null;
  cancelled_by_name: string;
  cancel_reason: string;
}

export interface ServiceOrderStatusLogEntry {
  id: number;
  previous_status: string;
  new_status: string;
  note: string;
  changed_by_name: string;
  created_at: string;
}

export interface ServiceOrderListItem {
  id: number;
  order_number: string;
  order_type: ServiceOrderType;
  outlet: ServiceOutlet;
  status: ServiceOrderStatus;
  settlement: ServiceOrderSettlement;
  stay: number | null;
  room: number | null;
  room_number: string;
  table: number | null;
  table_number: string;
  customer_name: string;
  business_date: string | null;
  ordered_at: string;
  requested_delivery_time: string | null;
  delivered_at: string | null;
  is_posted: boolean;
  posted_at: string | null;
  settled_at: string | null;
  total: string | null;
}

export interface ServiceOrderTotals {
  subtotal: string;
  tax_total: string;
  total: string;
}

export interface ServiceOrder {
  id: number;
  order_number: string;
  order_type: ServiceOrderType;
  outlet: ServiceOutlet;
  status: ServiceOrderStatus;
  settlement: ServiceOrderSettlement;
  stay: number | null;
  room: number | null;
  room_number: string;
  table: number | null;
  table_number: string;
  customer_name: string;
  business_date: string | null;
  guest_name: string;
  folio: number | null;
  folio_number: string;
  ordered_at: string;
  requested_delivery_time: string | null;
  delivered_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string;
  notes: string;
  internal_notes: string;
  is_posted: boolean;
  posted_at: string | null;
  posted_charge: number | null;
  posted_charge_number: string;
  settled_at: string | null;
  settlement_payment: number | null;
  settlement_receipt: string;
  items: ServiceOrderItem[];
  totals: ServiceOrderTotals;
  status_logs: ServiceOrderStatusLogEntry[];
  created_at: string;
  updated_at: string;
}

export interface ServicesOverview {
  orders_today: number;
  submitted: number;
  preparing: number;
  ready: number;
  delivered: number;
  delivered_not_posted: number;
  delivered_not_settled: number;
  posted_today_total: string;
  paid_direct_today_total: string;
  active_items: number;
}

/** KOT (`variant=kot`, default — no prices) or guest check
 * (`variant=guest_check` — prices + totals). Cancelled lines never appear. */
export interface ServiceTicket {
  document: "service_ticket" | "guest_check";
  hotel: HotelHeader;
  order: {
    order_number: string;
    order_type: ServiceOrderType;
    outlet: ServiceOutlet;
    status: ServiceOrderStatus;
    settlement: ServiceOrderSettlement;
    room_number: string;
    table_number: string;
    customer_name: string;
    guest_name: string;
    ordered_at: string;
    requested_delivery_time: string | null;
    notes: string;
  };
  items: Array<{
    item_name: string;
    quantity: string;
    notes: string;
    /** Present only on the guest check variant. */
    unit_price?: string;
    tax_amount?: string;
    total_amount?: string;
  }>;
  /** Present only on the guest check variant. */
  totals?: ServiceOrderTotals;
}

/* ==========================================================================
 * Phase 10 — Operations DTOs (mirror /api/v1/hotel/operations/).
 * ======================================================================== */

export type OperationPriority = "low" | "normal" | "high" | "urgent";

export type HousekeepingTaskType =
  | "checkout_cleaning"
  | "daily_cleaning"
  | "deep_cleaning"
  | "inspection"
  | "other";

export type HousekeepingStatus =
  | "pending"
  | "assigned"
  | "in_progress"
  | "awaiting_inspection"
  | "completed"
  | "cancelled";

export interface OperationStatusLogEntry {
  id: number;
  previous_status: string;
  new_status: string;
  note: string;
  changed_by_name: string;
  created_at: string;
}

export interface HousekeepingTaskListItem {
  id: number;
  task_number: string;
  room: number | null;
  room_number: string;
  stay: number | null;
  task_type: HousekeepingTaskType;
  status: HousekeepingStatus;
  priority: OperationPriority;
  assigned_to: number | null;
  assigned_to_name: string;
  requested_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface HousekeepingTask extends HousekeepingTaskListItem {
  room_status: string;
  cancelled_at: string | null;
  cancellation_reason: string;
  notes: string;
  internal_notes: string;
  status_logs: OperationStatusLogEntry[];
  created_at: string;
  updated_at: string;
}

/** Room expecting a confirmed arrival on the hotel business date but not yet
 * ready (not `available` or still occupied). */
export interface ArrivalNotReadyRow {
  room: number;
  room_number: string;
  room_status: string;
  occupied: boolean;
  reservation_number: string;
}

export type MaintenanceCategory =
  | "electrical"
  | "plumbing"
  | "hvac"
  | "furniture"
  | "cleaning_issue"
  | "safety"
  | "other";

export type MaintenanceStatus =
  | "open"
  | "assigned"
  | "in_progress"
  | "resolved"
  | "closed"
  | "cancelled";

export type RoomBlockStatus = "none" | "maintenance" | "out_of_service";

export interface MaintenanceRequestListItem {
  id: number;
  request_number: string;
  room: number | null;
  room_number: string;
  stay: number | null;
  title: string;
  category: MaintenanceCategory;
  priority: OperationPriority;
  status: MaintenanceStatus;
  affects_room_availability: boolean;
  room_block_status: RoomBlockStatus;
  assigned_to: number | null;
  assigned_to_name: string;
  reported_at: string;
  resolved_at: string | null;
  closed_at: string | null;
}

export interface MaintenanceRequest extends MaintenanceRequestListItem {
  room_status: string;
  description: string;
  started_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string;
  resolution_notes: string;
  internal_notes: string;
  status_logs: OperationStatusLogEntry[];
  created_at: string;
  updated_at: string;
}

export type LostFoundCategory =
  | "electronics"
  | "documents"
  | "clothing"
  | "jewelry"
  | "money"
  | "luggage"
  | "other";

export type LostFoundStatus =
  | "found"
  | "stored"
  | "claimed"
  | "returned"
  | "disposed"
  | "closed";

export interface LostFoundItemListItem {
  id: number;
  item_number: string;
  title: string;
  category: LostFoundCategory;
  status: LostFoundStatus;
  found_at: string;
  found_location: string;
  room: number | null;
  room_number: string;
  stay: number | null;
  guest: number | null;
  guest_name: string;
  stored_location: string;
  returned_at: string | null;
}

export interface LostFoundItem extends LostFoundItemListItem {
  description: string;
  found_by_name: string;
  claimed_by_name: string;
  claimed_by_phone: string;
  claimed_at: string | null;
  disposed_at: string | null;
  closed_at: string | null;
  notes: string;
  internal_notes: string;
  status_logs: OperationStatusLogEntry[];
  created_at: string;
  updated_at: string;
}

export interface OperationsOverview {
  dirty_rooms: number;
  hk_pending: number;
  hk_in_progress: number;
  open_maintenance: number;
  rooms_under_maintenance: number;
  lost_found_open: number;
  urgent_tasks: number;
}

/* ==========================================================================
 * Phase 11 — Staff & permissions DTOs (mirror /api/v1/hotel/staff/).
 * ======================================================================== */

export type HotelMembershipType = "manager" | "staff";

export interface StaffMemberListItem {
  id: number;
  user_id: number;
  full_name: string;
  email: string;
  phone: string;
  membership_type: HotelMembershipType;
  is_manager: boolean;
  is_active: boolean;
  is_primary_manager: boolean;
  job_title: string;
  staff_code: string;
  permission_count: number;
  created_at: string;
}

export interface StaffMember extends Omit<StaffMemberListItem, "permission_count"> {
  notes: string;
  deactivated_at: string | null;
  deactivation_reason: string;
  permissions: string[];
  created_by_name: string;
  updated_by_name: string;
  updated_at: string;
}

/** POST /staff/<id>/delete — the hardened delete reports what it removed.
 * `user_deleted` is null when the shared user account was kept. */
export interface StaffDeleteResult {
  membership_deleted: number;
  user_deleted: number | null;
}

export interface PermissionRegistrySection {
  section: string;
  operations: string[];
  codes: string[];
}

export interface StaffPermissionsPayload {
  membership: number;
  full_name: string;
  is_manager: boolean;
  is_active: boolean;
  editable: boolean;
  is_self: boolean;
  granted: string[];
  effective: string[];
  registry: PermissionRegistrySection[];
}

export interface MyHotelPermissions {
  is_manager: boolean;
  permissions: string[];
}

export interface StaffOverview {
  total_staff: number;
  active_staff: number;
  inactive_staff: number;
  managers: number;
  staff_with_permissions: number;
  staff_without_permissions: number;
}

/* ==========================================================================
 * Phase 12 — Shifts / handover / daily close DTOs (mirror /api/v1/hotel/shifts/).
 * ======================================================================== */

export type ShiftStatus = "open" | "closing" | "closed" | "cancelled";
export type HandoverStatus =
  | "draft"
  | "submitted"
  | "accepted"
  | "rejected"
  | "cancelled";
export type DailyCloseStatus = "draft" | "closed" | "reopened";

export interface ShiftListItem {
  id: number;
  shift_number: string;
  business_date: string;
  status: ShiftStatus;
  responsible_user: number;
  responsible_name: string;
  opened_at: string;
  closed_at: string | null;
  opening_cash_amount: string;
  expected_cash_amount: string;
  actual_cash_amount: string | null;
  cash_difference: string;
}

export interface Shift extends ShiftListItem {
  opened_by: number | null;
  opened_by_name: string;
  cancelled_at: string | null;
  cancellation_reason: string;
  difference_reason: string;
  opening_notes: string;
  closing_notes: string;
  internal_notes: string;
  status_logs: OperationStatusLogEntry[];
  created_at: string;
  updated_at: string;
}

export interface ShiftCashSummary {
  opening_cash: string;
  cash_payments_total: string;
  cash_expenses_total: string;
  expected_cash: string;
  payments_count: number;
  expenses_count: number;
  payments_by_method: Record<string, { count: number; total: string }>;
  expenses_by_method: Record<string, { count: number; total: string }>;
}

export interface UnassignedMovements {
  payments_count: number;
  payments_total: string;
  expenses_count: number;
  expenses_total: string;
}

export interface ShiftsOverview {
  business_date: string;
  open_shifts: number;
  today_shifts: number;
  pending_handovers: number;
  last_daily_close_date: string | null;
  today_cash_expected: string;
  today_cash_actual: string;
  unassigned_movements: UnassignedMovements;
  today_close_status: DailyCloseStatus | null;
}

export interface ShiftHandoverListItem {
  id: number;
  handover_number: string;
  from_shift: number;
  from_shift_number: string;
  to_user: number;
  to_user_name: string;
  status: HandoverStatus;
  created_by_name: string;
  submitted_at: string | null;
  accepted_at: string | null;
  created_at: string;
}

export interface ShiftHandover extends ShiftHandoverListItem {
  rejected_at: string | null;
  cancelled_at: string | null;
  rejection_reason: string;
  cancellation_reason: string;
  summary_notes: string;
  pending_tasks_notes: string;
  cash_notes: string;
  guest_notes: string;
  maintenance_notes: string;
  lost_found_notes: string;
  status_logs: OperationStatusLogEntry[];
  updated_at: string;
}

/** GET /shifts/<id>/statement — print-friendly operational shift statement. */
export interface ShiftStatement {
  document: string;
  hotel: HotelHeader;
  shift: Shift;
  cash_summary: ShiftCashSummary;
  unassigned_movements: UnassignedMovements;
}

/** GET /shifts/handovers/<id>/voucher — print-friendly handover voucher. */
export interface HandoverVoucher {
  document: string;
  hotel: HotelHeader;
  handover: ShiftHandover;
}

/** One issue surfaced by the daily-close checks. `code` is stable; the extra
 *  fields only appear on the codes that carry them. */
export interface DailyCloseException {
  code: string;
  count?: number;
  shifts?: string[];
  total_balance?: string;
  net_cash?: string;
}

/** Money totals for a close. Identical keys appear in the list `totals_json`
 *  and in the prepare `preview_totals`. */
export interface DailyCloseTotals {
  payments_cash_total: string;
  payments_non_cash_total: string;
  expenses_cash_total: string;
  expenses_non_cash_total: string;
  restaurant_sales: string;
  cafe_sales: string;
  shifts_count: number;
  expected_cash_total: string;
  actual_cash_total: string;
  difference_total: string;
}

export interface DailyCloseMethodTotals {
  count: number;
  total: string;
}

export interface DailyCloseUnassignedMovements {
  cash_payments: DailyCloseMethodTotals;
  cash_expenses: DailyCloseMethodTotals;
  cash_payment_reversals: DailyCloseMethodTotals;
  cash_expense_reversals: DailyCloseMethodTotals;
  net_cash: string;
}

/** Stored snapshot on a closed DailyClose row (read-only, sectioned). */
export interface DailyCloseSnapshot {
  identity: {
    hotel_id: number;
    business_date: string;
    previous_business_date: string;
    next_business_date: string;
    timezone: string;
    currency: string;
  };
  shifts: {
    closed_shifts_count: number;
    cancelled_shifts_count: number;
    opening_balances_total: string;
    expected_cash_total: string;
    actual_cash_total: string;
    difference_total: string;
    shifts_with_difference_count: number;
    difference_reasons_summary: unknown[];
    items: Array<{
      shift_number: string;
      status: string;
      responsible: string;
      opening_cash: string;
      expected_cash: string;
      actual_cash: string;
      cash_difference: string;
    }>;
  };
  payments: {
    posted_by_method: Record<string, DailyCloseMethodTotals>;
    cash_total: string;
    non_cash_total: string;
    voided_count: number;
    voided_total: string;
    reversals_count: number;
    reversals_total: string;
    cash_reversals_total: string;
    non_cash_reversals_total: string;
  };
  expenses: {
    posted_by_method: Record<string, DailyCloseMethodTotals>;
    posted_by_category: Record<string, DailyCloseMethodTotals>;
    cash_total: string;
    non_cash_total: string;
    voided_count: number;
    voided_total: string;
    reversals_count: number;
    reversals_total: string;
    cash_reversals_total: string;
    non_cash_reversals_total: string;
  };
  restaurant: {
    restaurant_sales: string;
    cafe_sales: string;
    direct_settlements: DailyCloseMethodTotals;
    folio_postings: DailyCloseMethodTotals;
    open_orders_count: number;
    cancelled_orders_count: number;
  };
  folios: {
    open_folios_count: number;
    total_balance: string;
    positive_balance_count: number;
    positive_balance_amount: string;
    negative_balance_count: number;
    negative_balance_amount: string;
    zero_balance_count: number;
    folios_closed_during_day: number;
    foreign_currency_folios: unknown[];
  };
  operations: {
    in_house_stays: number;
    arrivals_not_checked_in: number;
    overdue_departures: number;
    open_housekeeping_tasks: number;
    open_maintenance_requests: number;
    not_ready_rooms: number;
    open_lost_found_records: number;
  };
  exceptions: {
    blocking_errors: DailyCloseException[];
    warnings: DailyCloseException[];
    informational_alerts: DailyCloseException[];
    unassigned_movements: DailyCloseUnassignedMovements;
  };
  business_date: string;
}

export interface DailyClose {
  id: number;
  close_number: string;
  business_date: string;
  status: DailyCloseStatus;
  closed_by: number | null;
  closed_by_name: string;
  closed_at: string | null;
  notes: string;
  snapshot_json: DailyCloseSnapshot;
  totals_json: DailyCloseTotals;
  created_at: string;
  updated_at: string;
}

/** POST /shifts/daily-close/prepare — read-only pre-close check. Writes nothing. */
export interface DailyClosePreview {
  business_date: string;
  can_close: boolean;
  blocking_errors: DailyCloseException[];
  warnings: DailyCloseException[];
  informational_alerts: DailyCloseException[];
  preview_totals: DailyCloseTotals;
}

/** GET /shifts/daily-close/<pk>/statement — print-friendly stored statement. */
export interface DailyCloseStatement {
  document: string;
  hotel: HotelHeader;
  close: DailyClose;
}

export interface DailyCloseListItem {
  id: number;
  close_number: string;
  business_date: string;
  status: DailyCloseStatus;
  closed_by_name: string;
  closed_at: string | null;
  totals_json: DailyCloseTotals;
}

/* ==========================================================================
 * Phase 13 — Reports DTOs (mirror /api/v1/hotel/reports/). Read-only.
 * ======================================================================== */

export interface ReportBucket {
  key: string;
  count: number;
  total?: string;
}

export interface ReportDayRow {
  date: string;
  count: number;
  total: string;
}

export interface ReportPage<T> {
  count: number;
  page: number;
  page_size: number;
  results: T[];
}

export interface OverviewReport {
  date_from: string;
  date_to: string;
  reservations_count: number;
  confirmed_reservations_count: number;
  cancelled_reservations_count: number;
  expired_reservations_count: number;
  arrivals_count: number;
  departures_count: number;
  in_house_count: number;
  occupancy_rate: string;
  rooms_total: number;
  rooms_available: number;
  rooms_dirty: number;
  rooms_maintenance: number;
  // Financial totals were REMOVED from the operational overview (final
  // closure): money now lives behind `reports.finance` in the finance
  // reports below. Do not re-add money fields to this operational shape.
  service_orders_total: number;
  open_housekeeping_tasks: number;
  open_maintenance_requests: number;
  open_lost_found_items: number;
  open_shifts_count: number;
  closed_days_count: number;
}

export interface ReservationsReport {
  by_status: ReportBucket[];
  by_source: ReportBucket[];
  by_booking_kind: ReportBucket[];
  average_nights: string;
  by_room_type: ReportBucket[];
  arrivals_by_day: Record<string, number>;
  departures_by_day: Record<string, number>;
  list: ReportPage<{
    id: number;
    reservation_number: string;
    guest_name: string;
    status: ReservationStatus;
    source: string;
    booking_kind: string;
    check_in_date: string;
    check_out_date: string;
    nights: number;
  }>;
}

export interface OccupancyReport {
  date_from: string;
  date_to: string;
  occupancy_rate: string;
  rooms_capacity: number;
  occupied_by_day: Record<string, number>;
  in_house_now: number;
  room_status_now: Record<string, number>;
  stays_by_room_type: ReportBucket[];
}

export interface GuestsReport {
  new_guests_count: number;
  by_nationality: ReportBucket[];
  repeat_guests_count: number;
  current_residents_count: number;
  checked_out_count: number;
  list: ReportPage<{
    id: number;
    full_name: string;
    nationality: string;
    phone: string;
    created_at: string;
  }>;
}

export interface FinanceReport {
  date_from: string;
  date_to: string;
  payments_by_method: ReportBucket[];
  payments_by_day: ReportDayRow[];
  expenses_by_category: ReportBucket[];
  expenses_by_day: ReportDayRow[];
  total_payments: string;
  total_expenses: string;
  net_cashflow_simple: string;
  invoices_issued_count: number;
  invoices_issued_total: string;
  open_folios_count: number;
  folios_closed_in_range: number;
  voided: { payments: number; expenses: number; charges: number };
}

export interface ServicesReport {
  orders_count: number;
  by_status: ReportBucket[];
  by_source: ReportBucket[];
  delivered_posted: number;
  delivered_unposted: number;
  posted_to_folio_total: string;
  top_items: Array<ReportBucket & { quantity: string }>;
  cancelled_count: number;
}

export interface OperationsReport {
  housekeeping_by_status: ReportBucket[];
  cleaning_completed_count: number;
  maintenance_by_status: ReportBucket[];
  maintenance_by_category: ReportBucket[];
  maintenance_by_priority: ReportBucket[];
  rooms_under_maintenance_now: number;
  lost_found_by_status: ReportBucket[];
  lost_found_by_category: ReportBucket[];
  urgent_open_count: number;
}

export interface ShiftsReport {
  shifts_by_status: ReportBucket[];
  closed_shifts_count: number;
  shifts_with_difference: number;
  total_expected_cash: string;
  total_actual_cash: string;
  total_cash_difference: string;
  handovers_by_status: ReportBucket[];
  unassigned_movements: UnassignedMovements;
  closed_days_count: number;
  shifts: Array<{
    shift_number: string;
    business_date: string;
    status: ShiftStatus;
    responsible: string;
    opening_cash: string;
    expected_cash: string;
    actual_cash: string | null;
    cash_difference: string;
    difference_reason: string;
  }>;
  today_unassigned: UnassignedMovements;
}

export interface DailyCloseReportRow {
  id: number;
  close_number: string;
  business_date: string;
  status: DailyCloseStatus;
  closed_by: string;
  closed_at: string | null;
  totals: DailyCloseTotals;
}

/* ==========================================================================
 * Finance & Reports final closure — business-date-keyed finance reports
 * (mirror /api/v1/hotel/reports/finance/*). Gated by `reports.finance`.
 * EVERY money value is a decimal STRING: render as-is, never parseFloat.
 * ======================================================================== */

export type FinanceSourceStatus = "live" | "snapshot" | "mixed" | "none";

/** Revenue split by category — net of tax; `taxes` is the stored tax amount.
 * A `type` (not `interface`) so it stays assignable to `Record<string, string>`
 * for the shared amount tables. */
export type FinanceRevenueByCategory = {
  room: string;
  restaurant: string;
  cafe: string;
  services: string;
  other: string;
  adjustments: string;
  discounts: string;
  taxes: string;
  total: string;
};

export interface FinanceDataQuality {
  has_room_charges: boolean;
  room_revenue_source: string;
}

export interface FinanceKpis {
  occupancy_rate: string;
  adr: string;
  revpar: string;
  total_revenue: string;
  room_revenue: string;
  restaurant_revenue: string;
  cafe_revenue: string;
  expenses: string;
  net_cashflow: string;
  open_folio_balance: string | null;
}

export interface FinanceOverviewReport {
  current_business_date: string;
  date_from: string;
  date_to: string;
  source_status: FinanceSourceStatus;
  days_missing_close: string[];
  reporting_missing_days: string[];
  revenue: FinanceRevenueByCategory;
  taxes: string;
  gross_payments: string;
  payment_reversals: string;
  net_payments: string;
  gross_expenses: string;
  expense_reversals: string;
  net_expenses: string;
  net_cashflow: string;
  open_folio_balance: string;
  occupancy: string;
  adr: string;
  revpar: string;
  kpis: FinanceKpis;
  data_quality: FinanceDataQuality;
}

export interface RevenueReport {
  date_from: string;
  date_to: string;
  source_status: FinanceSourceStatus;
  days_missing_close: string[];
  reporting_missing_days: string[];
  by_category: FinanceRevenueByCategory;
  gross_revenue: string;
  adjustments: string;
  discounts: string;
  taxes: string;
  net_revenue: string;
  data_quality: FinanceDataQuality;
}

/** A posted movement block (payments OR expenses): gross, reversals and
 * voided are reported SEPARATELY, never pre-netted into one figure. */
export interface FinanceMovement {
  gross: string;
  cash: string;
  non_cash: string;
  by_method: Record<string, string>;
  reversals: { count: number; amount: string; cash: string; non_cash: string };
  voided: { count: number; amount: string };
  net: string;
  /** Populated for expenses; null for payments. */
  by_category: Record<string, string> | null;
}

export interface PaymentsReport {
  date_from: string;
  date_to: string;
  source_status: FinanceSourceStatus;
  payments: FinanceMovement;
  unassigned_movements: UnassignedMovements;
}

export interface ExpensesReport {
  date_from: string;
  date_to: string;
  source_status: FinanceSourceStatus;
  expenses: FinanceMovement;
}

export interface TaxReport {
  date_from: string;
  date_to: string;
  source_status: FinanceSourceStatus;
  reporting_missing_days: string[];
  total_tax: string;
  net_revenue_ex_tax: string;
  by_category_revenue: FinanceRevenueByCategory;
}

export interface ForeignCurrencyFolio {
  currency: string;
  count: number;
  balance: string;
}

/** Point-in-time open-folio balances; foreign-currency folios are reported
 * separately and NEVER mixed into the hotel-currency totals. */
export interface FolioBalancesReport {
  currency: string;
  open_folios_count: number;
  total_balance: string;
  positive_balance_count: number;
  positive_balance_amount: string;
  negative_balance_count: number;
  negative_balance_amount: string;
  zero_balance_count: number;
  closed_in_range: number;
  foreign_currency_folios: ForeignCurrencyFolio[];
}

export interface RestaurantCafeReport {
  date_from: string;
  date_to: string;
  source_status: FinanceSourceStatus;
  restaurant_sales: string;
  cafe_sales: string;
  direct_settlements: { count: number; total: string };
  folio_postings: { count: number; total: string };
  open_orders_count: number;
  cancelled_orders_count: number;
}

/** `delta_pct` is null when the previous value is 0 (zero-guard) → render "—". */
export interface ComparisonMetric {
  current: string;
  previous: string;
  delta: string;
  delta_pct: string | null;
}

export interface ComparisonMetrics {
  revenue_total: ComparisonMetric;
  net_payments: ComparisonMetric;
  net_expenses: ComparisonMetric;
  taxes: ComparisonMetric;
}

export interface ComparisonsReport {
  current_business_date: string;
  day_vs_previous: ComparisonMetrics & {
    current_date: string;
    previous_date: string;
  };
  mtd_vs_previous_month: ComparisonMetrics & {
    current_range: [string, string];
    previous_range: [string, string];
  };
}

/* ==========================================================================
 * Phase 14 — Notifications + activity DTOs (mirror /api/v1/hotel/notifications/).
 * ======================================================================== */

export type ActivityCategory =
  | "reservation"
  | "stay"
  | "guest"
  | "room"
  | "finance"
  | "service"
  | "operation"
  | "shift"
  | "staff"
  | "report"
  | "system";

export type ActivitySeverity = "info" | "success" | "warning" | "danger";

export type NotificationScope = "hotel" | "platform";

export interface HotelNotification {
  id: number;
  notification_number: string;
  scope: NotificationScope;
  hotel: number;
  category: ActivityCategory;
  severity: ActivitySeverity;
  title: string;
  message: string;
  related_url: string;
  activity: number | null;
  is_read: boolean;
  read_at: string | null;
  is_archived: boolean;
  archived_at: string | null;
  created_at: string;
}

export interface ActivityEventRow {
  id: number;
  event_number: string;
  event_type: string;
  category: ActivityCategory;
  severity: ActivitySeverity;
  title: string;
  message: string;
  actor: number | null;
  actor_name: string;
  target_user: number | null;
  target_user_name: string;
  related_object_type: string;
  related_object_id: number | null;
  related_url: string;
  metadata_json: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
}

export interface NotificationsOverview {
  unread_count: number;
  today_notifications_count: number;
  warning_count: number;
  danger_count: number;
  archived_count: number;
  recent_activity_count: number;
}
