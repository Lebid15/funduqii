"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell } from "lucide-react";

import { Badge, IconButton } from "@/components/ui";
import { getUnreadCount } from "@/lib/api/notifications";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

/**
 * Topbar bell (Phase 14): unread badge loaded ONCE per shell mount — no
 * realtime, no polling (deliberate). Clicking navigates to the notifications
 * page. Hidden entirely when the user lacks `notifications.view`.
 */
export function NotificationBell() {
  const { t } = useI18n();
  const router = useRouter();
  const access = useHotelAccess();
  const [unread, setUnread] = useState<number | null>(null);

  const canView = access !== null && !access.loading && access.can("notifications.view");

  useEffect(() => {
    if (!canView) return;
    let cancelled = false;
    getUnreadCount()
      .then((data) => {
        if (!cancelled) setUnread(data.unread);
      })
      .catch(() => {
        if (!cancelled) setUnread(null);
      });
    return () => {
      cancelled = true;
    };
  }, [canView]);

  if (!canView) return null;

  return (
    <span className="cluster">
      <IconButton
        label={t.notifications.bell}
        icon={Bell}
        onClick={() => router.push("/hotel/notifications")}
      />
      {unread !== null && unread > 0 ? <Badge tone="danger">{unread}</Badge> : null}
    </span>
  );
}
