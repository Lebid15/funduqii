/**
 * POST /api/session/login — exchange credentials for an HttpOnly cookie session.
 *
 * On success the access/refresh JWTs are stored in HttpOnly cookies (never
 * returned to JS). The response includes a `redirect` target based on the
 * account: platform owners go to /platform; hotel users with an active
 * membership go to /hotel (and their current hotel is stored in an HttpOnly
 * cookie). A hotel user with no active membership is signed out and rejected.
 */
import { NextResponse } from "next/server";

import { clearSession, getMe, login, setHotelId } from "@/lib/session/server";

export async function POST(request: Request) {
  let body: { email?: string; password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ code: "invalid_request" }, { status: 400 });
  }

  const email = body.email?.trim();
  const password = body.password;
  if (!email || !password) {
    return NextResponse.json({ code: "invalid_request" }, { status: 400 });
  }

  const result = await login(email, password);
  if (!result.ok) {
    return NextResponse.json({ code: "invalid_credentials" }, { status: 401 });
  }

  const me = await getMe();
  if (!me) {
    await clearSession();
    return NextResponse.json({ code: "not_authenticated" }, { status: 401 });
  }

  if (me.user.is_platform_owner) {
    return NextResponse.json({ user: me.user, redirect: "/platform" });
  }

  const activeMembership = me.memberships.find((m) => m.is_active);
  if (!activeMembership) {
    await clearSession();
    return NextResponse.json({ code: "no_hotel_access" }, { status: 403 });
  }

  await setHotelId(activeMembership.hotel_id);
  return NextResponse.json({ user: me.user, redirect: "/hotel" });
}
