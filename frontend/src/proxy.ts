/**
 * Proxy (formerly Middleware, renamed in Next.js 16).
 *
 * A cheap optimistic gate for the platform console: if there is no session
 * cookie, redirect to /login before rendering. This is UX only — real
 * authorization is enforced by the backend on every API call and by the
 * platform layout (which verifies the platform-owner account server-side).
 */
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { REFRESH_COOKIE } from "@/lib/session/config";

export function proxy(request: NextRequest) {
  const hasSession = request.cookies.has(REFRESH_COOKIE);
  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/platform/:path*", "/hotel/:path*"],
};
