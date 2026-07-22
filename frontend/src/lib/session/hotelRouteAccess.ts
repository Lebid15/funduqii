/**
 * Central route → required-permissions map for the hotel console (Phase 11).
 *
 * One source of truth shared by the sidebar (link visibility) and the route
 * guard (manual URL entry). A route is visible/enterable when the user holds
 * ANY of its codes; a manager always passes. The backend enforces the same
 * permissions on every API call — this map is cosmetic defense in depth.
 */
export const HOTEL_ROUTE_ACCESS: Record<string, string[]> = {
  "/hotel/front-desk": ["stays.view"],
  "/hotel/reservations": ["reservations.view"],
  "/hotel/guests": ["guests.view"],
  "/hotel/finance": ["finance.view"],
  "/hotel/expenses": ["expenses.view"],
  "/hotel/guest-folio": ["service_orders.create", "services.view", "finance.view"],
  "/hotel/services": ["services.view", "service_orders.view"],
  "/hotel/operations": ["housekeeping.view", "maintenance.view", "lost_found.view"],
  "/hotel/staff": ["staff.view"],
  "/hotel/shifts": ["shifts.view"],
  "/hotel/daily-close": ["daily_close.view"],
  "/hotel/reports": ["reports.view"],
  "/hotel/notifications": ["notifications.view", "activity.view"],
  "/hotel/rooms": ["rooms.view"],
  "/hotel/settings": ["settings.view"],
};

/** Required codes for a pathname, or null when the route is unrestricted. */
export function requiredPermissionsFor(pathname: string): string[] | null {
  for (const [prefix, codes] of Object.entries(HOTEL_ROUTE_ACCESS)) {
    if (pathname === prefix || pathname.startsWith(`${prefix}/`)) return codes;
  }
  return null;
}
