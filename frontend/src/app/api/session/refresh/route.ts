/**
 * GET /api/session/refresh?next=/platform/... — refresh the access token
 * (persisting the rotated pair) then bounce back.
 *
 * The platform layout redirects here when its access token has expired: a
 * Server Component cannot write cookies during render, so refresh-and-persist
 * must happen in a route handler. Falls back to /login if refresh fails or the
 * user is not a platform owner.
 */
import { NextResponse } from "next/server";

import { clearSession, djangoRequest } from "@/lib/session/server";

function safeNext(raw: string | null): string {
  // Only allow internal console paths to prevent open redirects.
  if (raw && (raw.startsWith("/platform") || raw.startsWith("/hotel"))) {
    return raw;
  }
  return "/platform";
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const next = safeNext(url.searchParams.get("next"));

  const res = await djangoRequest("/auth/me/", { method: "GET" });
  if (!res.ok) {
    await clearSession();
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // The refresh persisted rotated tokens; the target layout (platform/hotel)
  // performs the role/membership gate. Just bounce back.
  return NextResponse.redirect(new URL(next, request.url));
}
