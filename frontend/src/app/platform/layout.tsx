import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { getCurrentUser } from "@/lib/session/server";

/**
 * Server-side gate for the whole platform console. Enforcement is on the
 * backend for every API call; this layer additionally verifies, server-side,
 * that the session belongs to a PLATFORM OWNER before any platform page renders
 * — hiding the sidebar is never the protection.
 *
 * If the access token has expired we bounce through the refresh route (a Server
 * Component cannot write cookies), which persists the rotated tokens and
 * returns here.
 */
export default async function PlatformLayout({
  children,
}: {
  children: ReactNode;
}) {
  const user = await getCurrentUser();

  if (!user) {
    redirect("/api/session/refresh?next=/platform");
  }
  if (!user.is_platform_owner) {
    redirect("/login");
  }

  return <AppShell user={user}>{children}</AppShell>;
}
