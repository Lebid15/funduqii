/**
 * Authenticated proxy: /api/platform/<...>  →  Django /api/v1/platform/<...>/
 *
 * Client components call this same-origin endpoint; the HttpOnly access-token
 * cookie is attached server-side (and refreshed on expiry) before forwarding to
 * the API. Tokens never reach the browser. The backend remains the source of
 * truth — every forwarded request is still authorized by `IsPlatformOwner`.
 */
import { NextResponse } from "next/server";

import { djangoRequest } from "@/lib/session/server";

type Ctx = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  const search = new URL(request.url).search;
  // DJANGO_API_BASE already ends with `/api`; Django's platform routes live at
  // `/api/v1/platform/…` and are trailing-slash, so append `/v1/platform/<path>/`.
  const target = `/v1/platform/${path.join("/")}/${search}`;

  const method = request.method;
  const hasBody = method !== "GET" && method !== "HEAD";
  const body = hasBody ? await request.text() : undefined;

  const res = await djangoRequest(target, {
    method,
    headers: hasBody ? { "Content-Type": "application/json" } : {},
    body,
  });

  if (res.status === 401) {
    return NextResponse.json({ code: "session_expired" }, { status: 401 });
  }

  const text = await res.text();
  return new NextResponse(text || null, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("Content-Type") ?? "application/json",
    },
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
