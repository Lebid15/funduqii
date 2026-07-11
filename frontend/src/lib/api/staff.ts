/**
 * Client-side staff & permissions API (Phase 11). Calls the same-origin hotel
 * BFF proxy. Access is decided by permission GRANTS only — job titles are
 * descriptive labels; the backend owns every rule (last-manager protection,
 * escalation guard, registry validation). Passwords are never echoed back.
 */
import { hotelJson } from "./hotelFetch";
import type {
  MyHotelPermissions,
  PaginatedResponse,
  PermissionRegistrySection,
  StaffMember,
  StaffMemberListItem,
  StaffOverview,
  StaffPermissionsPayload,
} from "./types";

function toQuery(params?: object): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

const B = "/staff";

export function getStaffOverview(): Promise<StaffOverview> {
  return hotelJson<StaffOverview>(`${B}/overview`);
}

export function getMyPermissions(): Promise<MyHotelPermissions> {
  return hotelJson<MyHotelPermissions>(`${B}/my-permissions`);
}

export function getPermissionRegistry(): Promise<{
  sections: PermissionRegistrySection[];
}> {
  return hotelJson<{ sections: PermissionRegistrySection[] }>(
    `${B}/permission-registry`,
  );
}

export interface StaffListParams {
  search?: string;
  is_active?: string;
  membership_type?: string;
  has_permission?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

export function listStaff(
  params?: StaffListParams,
): Promise<PaginatedResponse<StaffMemberListItem>> {
  return hotelJson<PaginatedResponse<StaffMemberListItem>>(
    `${B}${toQuery(params)}`,
  );
}

export function getStaffMember(id: number): Promise<StaffMember> {
  return hotelJson<StaffMember>(`${B}/${id}`);
}

export interface StaffCreateBody {
  full_name: string;
  email: string;
  password: string;
  phone?: string;
  job_title?: string;
  staff_code?: string;
  notes?: string;
  permissions?: string[];
}

export function createStaffMember(body: StaffCreateBody): Promise<StaffMember> {
  return hotelJson<StaffMember>(`${B}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface LinkExistingBody {
  email: string;
  job_title?: string;
  staff_code?: string;
  notes?: string;
  permissions?: string[];
}

export function linkExistingUser(body: LinkExistingBody): Promise<StaffMember> {
  return hotelJson<StaffMember>(`${B}/link-existing-user`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export type StaffUpdateBody = Partial<
  Pick<StaffCreateBody, "full_name" | "phone" | "job_title" | "staff_code" | "notes">
>;

export function updateStaffMember(
  id: number,
  body: StaffUpdateBody,
): Promise<StaffMember> {
  return hotelJson<StaffMember>(`${B}/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deactivateStaffMember(
  id: number,
  reason = "",
): Promise<StaffMember> {
  return hotelJson<StaffMember>(`${B}/${id}/deactivate`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function reactivateStaffMember(id: number): Promise<StaffMember> {
  return hotelJson<StaffMember>(`${B}/${id}/reactivate`, {
    method: "POST",
    body: "{}",
  });
}

export function resetStaffPassword(
  id: number,
  password: string,
): Promise<{ status: string }> {
  return hotelJson<{ status: string }>(`${B}/${id}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export function getStaffPermissions(
  id: number,
): Promise<StaffPermissionsPayload> {
  return hotelJson<StaffPermissionsPayload>(`${B}/${id}/permissions`);
}

export function putStaffPermissions(
  id: number,
  permissions: string[],
): Promise<{ membership: number; granted: string[]; effective: string[] }> {
  return hotelJson<{ membership: number; granted: string[]; effective: string[] }>(
    `${B}/${id}/permissions`,
    { method: "PUT", body: JSON.stringify({ permissions }) },
  );
}
