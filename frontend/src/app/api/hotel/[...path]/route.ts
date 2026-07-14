/**
 * Authenticated hotel proxy: /api/hotel/<...>  →  Django /api/v1/hotel/<...>/
 *
 * Attaches the HttpOnly access token AND the current hotel context
 * (X-Hotel-ID, from the HttpOnly hotel cookie) server-side, then forwards.
 * Unlike the platform proxy this preserves the incoming Content-Type (so
 * multipart/form-data image uploads pass through with their boundary intact).
 * The backend still enforces membership, permissions, and tenant isolation.
 */
import { NextResponse } from "next/server";

import { djangoRequest, getHotelId } from "@/lib/session/server";

type Ctx = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, ctx: Ctx): Promise<Response> {
  const hotelId = await getHotelId();
  if (!hotelId) {
    return NextResponse.json({ code: "session_expired" }, { status: 401 });
  }

  const { path } = await ctx.params;
  const search = new URL(request.url).search;
  // Django URLs end with a slash EXCEPT file-like endpoints (e.g. the Phase
  // 13 `export.csv` routes) where a trailing slash would 404.
  const isFileLike = path[path.length - 1]?.includes(".");
  const target = `/v1/hotel/${path.join("/")}${isFileLike ? "" : "/"}${search}`;

  const method = request.method;
  const hasBody = method !== "GET" && method !== "HEAD";
  // Preserve the raw body + content type so multipart uploads survive.
  const body = hasBody ? await request.arrayBuffer() : undefined;
  const contentType = request.headers.get("content-type");

  const res = await djangoRequest(target, {
    method,
    headers: {
      "X-Hotel-ID": hotelId,
      ...(hasBody && contentType ? { "Content-Type": contentType } : {}),
    },
    body,
  });

  if (res.status === 401) {
    return NextResponse.json({ code: "session_expired" }, { status: 401 });
  }

  // Binary passthrough: for a non-JSON/text upstream response (image/*,
  // application/pdf, application/octet-stream, … — anything NOT starting with
  // `application/json` or `text/`) the bytes must be forwarded UNTOUCHED.
  // `res.text()` would decode them as UTF-8 and corrupt the file, so stream the
  // raw body and forward the security headers the backend set on private files.
  // JSON/text (every existing endpoint) keeps the exact text behavior below.
  const upstreamType = res.headers.get("Content-Type") ?? "";
  const isTextual =
    upstreamType.startsWith("application/json") ||
    upstreamType.startsWith("text/");
  if (upstreamType && !isTextual) {
    const headers = new Headers();
    for (const name of [
      "Content-Type",
      "Content-Disposition",
      "Cache-Control",
      "X-Content-Type-Options",
      "Referrer-Policy",
    ]) {
      const value = res.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new NextResponse(res.body, { status: res.status, headers });
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
