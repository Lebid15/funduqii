/**
 * Server-only session helpers.
 *
 * All JWT handling lives here and in the route handlers that call it — the only
 * places allowed to read/write the HttpOnly token cookies. Refresh-token
 * rotation (the API blacklists the old refresh on every refresh) is handled by
 * ALWAYS persisting the rotated pair, so tokens are never left stale.
 */
import "server-only";

import { cookies } from "next/headers";

import type { CurrentUser, MeResponse } from "@/lib/api/types";

import {
  ACCESS_COOKIE,
  DJANGO_API_BASE,
  REFRESH_COOKIE,
  sessionCookieOptions,
} from "./config";

export async function getAccessToken(): Promise<string | null> {
  return (await cookies()).get(ACCESS_COOKIE)?.value ?? null;
}

export async function getRefreshToken(): Promise<string | null> {
  return (await cookies()).get(REFRESH_COOKIE)?.value ?? null;
}

export async function persistSession(
  access: string,
  refresh: string,
): Promise<void> {
  const store = await cookies();
  const options = sessionCookieOptions();
  store.set(ACCESS_COOKIE, access, options);
  store.set(REFRESH_COOKIE, refresh, options);
}

export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.delete(ACCESS_COOKIE);
  store.delete(REFRESH_COOKIE);
}

/** Exchange email/password for tokens; persists them. Returns ok + status. */
export async function login(
  email: string,
  password: string,
): Promise<{ ok: boolean; status: number }> {
  const res = await fetch(`${DJANGO_API_BASE}/auth/token/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    cache: "no-store",
  });
  if (!res.ok) {
    return { ok: false, status: res.status };
  }
  const data = (await res.json()) as { access: string; refresh: string };
  await persistSession(data.access, data.refresh);
  return { ok: true, status: 200 };
}

/** Blacklist the refresh token on the API and clear cookies. */
export async function logout(): Promise<void> {
  const access = await getAccessToken();
  const refresh = await getRefreshToken();
  if (access && refresh) {
    try {
      await fetch(`${DJANGO_API_BASE}/auth/logout/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${access}`,
        },
        body: JSON.stringify({ refresh }),
        cache: "no-store",
      });
    } catch {
      // Best effort — we clear local cookies regardless.
    }
  }
  await clearSession();
}

/** Refresh the access token (rotating the refresh token) and persist both. */
async function refreshAccessToken(): Promise<string | null> {
  const refresh = await getRefreshToken();
  if (!refresh) {
    return null;
  }
  const res = await fetch(`${DJANGO_API_BASE}/auth/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
    cache: "no-store",
  });
  if (!res.ok) {
    await clearSession();
    return null;
  }
  const data = (await res.json()) as { access: string; refresh?: string };
  // ROTATE_REFRESH_TOKENS is on, so a new refresh is returned — persist both so
  // the rotated refresh is never left stale.
  await persistSession(data.access, data.refresh ?? refresh);
  return data.access;
}

/**
 * Call a Django endpoint with the current access token. On 401, refresh once
 * (persisting the rotated pair) and retry. Returns the raw Response.
 */
export async function djangoRequest(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const access = await getAccessToken();
  const doFetch = (token: string | null) =>
    fetch(`${DJANGO_API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init.headers ?? {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      cache: "no-store",
    });

  let res = await doFetch(access);
  if (res.status === 401) {
    const refreshed = await refreshAccessToken();
    if (!refreshed) {
      return res;
    }
    res = await doFetch(refreshed);
  }
  return res;
}

/**
 * Current authenticated user, or null. Used by the platform layout to gate the
 * console. Does not trigger a refresh itself — refresh is owned by the route
 * handlers so rotated tokens are always persisted.
 */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  const access = await getAccessToken();
  if (!access) {
    return null;
  }
  const res = await fetch(`${DJANGO_API_BASE}/auth/me/`, {
    headers: { Authorization: `Bearer ${access}` },
    cache: "no-store",
  });
  if (!res.ok) {
    return null;
  }
  const data = (await res.json()) as MeResponse;
  return data.user;
}
