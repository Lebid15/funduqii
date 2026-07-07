/**
 * POST /api/session/logout — blacklist the refresh token and clear cookies.
 */
import { NextResponse } from "next/server";

import { logout } from "@/lib/session/server";

export async function POST() {
  await logout();
  return NextResponse.json({ ok: true });
}
