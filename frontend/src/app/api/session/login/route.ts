/**
 * POST /api/session/login — exchange credentials for an HttpOnly cookie session.
 *
 * On success the access/refresh JWTs are stored in HttpOnly cookies (never
 * returned to JS). Only platform owners may use this console: a non-owner is
 * signed straight back out and rejected with 403.
 */
import { NextResponse } from "next/server";

import { clearSession, getCurrentUser, login } from "@/lib/session/server";

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
    return NextResponse.json(
      { code: "invalid_credentials" },
      { status: 401 },
    );
  }

  const user = await getCurrentUser();
  if (!user || !user.is_platform_owner) {
    await clearSession();
    return NextResponse.json({ code: "not_platform_owner" }, { status: 403 });
  }

  return NextResponse.json({ user });
}
