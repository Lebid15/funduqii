/**
 * Anonymous public proxy: /api/public/<...>  →  Django /api/v1/public/<...>/
 *
 * No session, no token, no hotel header — the public website is for visitors.
 * The Django side is throttled and only ever exposes published, public-safe
 * data (Phase 15). Only GET and POST exist publicly; everything else is 405.
 */
import { NextResponse } from "next/server";

import { DJANGO_API_BASE } from "@/lib/session/config";

type Ctx = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  const search = new URL(request.url).search;
  const target = `${DJANGO_API_BASE}/v1/public/${path.join("/")}/${search}`;

  const method = request.method;
  const hasBody = method === "POST";
  const res = await fetch(target, {
    method,
    headers: hasBody ? { "Content-Type": "application/json" } : undefined,
    body: hasBody ? await request.text() : undefined,
    cache: "no-store",
  });

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
