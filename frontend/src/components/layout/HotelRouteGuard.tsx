"use client";

import { usePathname } from "next/navigation";
import { ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";

import { EmptyState, LoadingState } from "@/components/ui";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";
import { requiredPermissionsFor } from "@/lib/session/hotelRouteAccess";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Blocks direct URL entry into hotel routes the user has no view permission
 * for (Phase 11). Cosmetic only — the APIs behind every page refuse on their
 * own; this simply shows a clear access-denied state instead of error toasts.
 */
export function HotelRouteGuard({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const pathname = usePathname();
  const access = useHotelAccess();

  const required = requiredPermissionsFor(pathname);
  if (required === null || access === null) return <>{children}</>;
  if (access.loading) return <LoadingState label={t.common.loading} />;
  if (!access.can(...required)) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title={t.staff.accessDenied.title}
        hint={t.staff.accessDenied.hint}
      />
    );
  }
  return <>{children}</>;
}
