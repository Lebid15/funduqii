import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { getHotelId, getMe } from "@/lib/session/server";

/**
 * Server-side gate for the hotel console. Requires an authenticated user with
 * an ACTIVE hotel membership — a platform owner without an explicit membership
 * is not a hotel member and is bounced. The backend still enforces membership,
 * permissions, and tenant isolation on every API call; this is defense in depth
 * and picks the current hotel (from the hotel cookie) for the shell.
 */
export default async function HotelLayout({
  children,
}: {
  children: ReactNode;
}) {
  const me = await getMe();

  if (!me) {
    redirect("/api/session/refresh?next=/hotel");
  }

  const activeMemberships = me.memberships.filter((m) => m.is_active);
  if (activeMemberships.length === 0) {
    redirect("/login");
  }

  const hotelId = await getHotelId();
  const current =
    activeMemberships.find((m) => String(m.hotel_id) === hotelId) ??
    activeMemberships[0];

  return (
    <AppShell variant="hotel" user={me.user} hotelName={current.hotel_name}>
      {children}
    </AppShell>
  );
}
