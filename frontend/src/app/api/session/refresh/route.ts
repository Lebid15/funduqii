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

import type { MeResponse } from "@/lib/api/types";
import { clearSession, djangoRequest } from "@/lib/session/server";

function safeNext(raw: string | null): string {
  // Only allow internal platform paths to prevent open redirects.
  if (raw && raw.startsWith("/platform")) {
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

  const data = (await res.json()) as MeResponse;
  if (!data.user.is_platform_owner) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.redirect(new URL(next, request.url));
}
