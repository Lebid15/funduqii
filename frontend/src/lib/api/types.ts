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
  created_at: string;
  updated_at: string;
}

/* ==========================================================================
 * Phase 6 — Reservations & availability DTOs (mirror /api/v1/hotel/).
 * ======================================================================== */

export type ReservationStatus = "held" | "confirmed" | "cancelled" | "expired";
export type ReservationSource = "direct" | "phone" | "walk_in" | "other";

export interface ReservationLine {
  id: number;
  room_type: number;
  room_type_name: string;
  room_type_code: string;
  max_capacity: number;
  room: number | null;
  room_number: string | null;
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
  primary_guest_name: string;
  primary_guest_phone: string;
  primary_guest_email: string;
  primary_guest_nationality: string;
  primary_guest_document_type: string;
  primary_guest_document_number: string;
  adults: number;
  children: number;
  total_guests: number;
  notes: string;
  special_requests: string;
  booking_channel_name: string;
  expected_payment_method: ExpectedPaymentMethod;
  no_show_reason: string;
  cancellation_reason: string;
  cancelled_at: string | null;
  hold_expires_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  lines: ReservationLine[];
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
  phone: string;
  email: string;
  nationality: string;
  document_type: DocumentType;
  document_number: string;
  date_of_birth: string | null;
  gender: Gender;
  address: string;
  notes: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
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
  created_at: string;
  updated_at: string;
}

export interface StayStatusLogEntry {
  previous_status: string;
  new_status: string;
  note: string;
  changed_by: string | null;
  created_at: string;
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
  paid_at: string;
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

/* ==========================================================================
 * Phase 9 — Service catalog & orders DTOs (mirror /api/v1/hotel/services/).
 * ======================================================================== */

export type ServiceItemType = "restaurant" | "cafe" | "room_service" | "other";
export type ServiceOrderSource =
  | "room_service"
  | "restaurant"
  | "cafe"
  | "other";
export type ServiceOrderStatus =
  | "draft"
  | "submitted"
  | "preparing"
  | "ready"
  | "delivered"
  | "cancelled";

export interface ServiceCategory {
  id: number;
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
  name: string;
  code: string;
  description: string;
  item_type: ServiceItemType;
  unit_price: string;
  currency: string;
  tax_rate: string;
  is_available: boolean;
  is_active: boolean;
  sort_order: number;
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
  source: ServiceOrderSource;
  status: ServiceOrderStatus;
  stay: number | null;
  room: number | null;
  room_number: string;
  ordered_at: string;
  requested_delivery_time: string | null;
  delivered_at: string | null;
  is_posted: boolean;
  posted_at: string | null;
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
  source: ServiceOrderSource;
  status: ServiceOrderStatus;
  stay: number | null;
  room: number | null;
  room_number: string;
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
  posted_today_total: string;
  active_items: number;
}

export interface ServiceTicket {
  document: "service_ticket";
  hotel: HotelHeader;
  order: {
    order_number: string;
    source: ServiceOrderSource;
    status: ServiceOrderStatus;
    room_number: string;
    guest_name: string;
    ordered_at: string;
    requested_delivery_time: string | null;
    notes: string;
  };
  items: Array<{
    item_name: string;
    quantity: string;
    unit_price: string;
    total_amount: string;
    notes: string;
  }>;
  totals: ServiceOrderTotals;
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
  job_title: string;
  staff_code: string;
  permission_count: number;
  created_at: string;
}

export interface StaffMember extends Omit<StaffMemberListItem, "permission_count"> {
  is_primary_manager: boolean;
  notes: string;
  deactivated_at: string | null;
  deactivation_reason: string;
  permissions: string[];
  created_by_name: string;
  updated_by_name: string;
  updated_at: string;
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
