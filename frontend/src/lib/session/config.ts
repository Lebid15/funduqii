/**
 * Session/auth configuration for the Backend-for-Frontend (BFF) layer.
 *
 * JWTs are NEVER exposed to client JavaScript or localStorage. The Next.js
 * route handlers exchange credentials with Django and store the access/refresh
 * tokens in HttpOnly cookies; the browser only ever holds opaque cookies.
 */

/** Django API base, used only from the Next.js server (never shipped to JS). */
export const DJANGO_API_BASE =
  process.env.API_INTERNAL_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000/api";

export const ACCESS_COOKIE = "funduqii_access";
export const REFRESH_COOKIE = "funduqii_refresh";

/** Cookie lifetime (7 days) — matches the refresh-token lifetime in the API. */
export const SESSION_MAX_AGE = 60 * 60 * 24 * 7;

export function sessionCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: SESSION_MAX_AGE,
  };
}
