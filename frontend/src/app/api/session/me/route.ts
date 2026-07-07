/**
 * GET /api/session/me — the current platform owner, or 401.
 */
import { NextResponse } from "next/server";

import { getCurrentUser } from "@/lib/session/server";

export async function GET() {
  const user = await getCurrentUser();
  if (!user) {
    return NextResponse.json({ code: "not_authenticated" }, { status: 401 });
  }
  return NextResponse.json({ user });
}
