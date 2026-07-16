"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell } from "lucide-react";

import { Badge, IconButton } from "@/components/ui";
import { getUnreadCount } from "@/lib/api/notifications";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useHotelAccess } from "@/lib/session/HotelAccessContext";

const POLL_MS = 60_000;

/**
 * Topbar bell (Phase 14 + notifications closure): unread badge with light
 * polling every 60s — no realtime, no WebSocket. Polling pauses while the tab
 * is hidden and never overlaps requests; the interval is cleared on unmount.
 * Clicking navigates to the notifications page. Hidden entirely when the user
 * lacks `notifications.view`.
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
    let inFlight = false;
    const load = () => {
      if (inFlight || (typeof document !== "undefined" && document.hidden)) return;
      inFlight = true;
      getUnreadCount()
        .then((data) => {
          if (!cancelled) setUnread(data.unread);
        })
        .catch(() => {
          if (!cancelled) setUnread(null);
        })
        .finally(() => {
          inFlight = false;
        });
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [canView]);

  if (!canView) return null;

  const hasUnread = unread !== null && unread > 0;
  // Fold the unread count into the button's accessible name so screen-reader
  // users hear it (the visual count Badge alone is not part of the name).
  const bellLabel = hasUnread
    ? t.notifications.bellUnread.replace("{count}", String(unread))
    : t.notifications.bell;

  return (
    <span className="cluster">
      <IconButton
        label={bellLabel}
        icon={Bell}
        onClick={() => router.push("/hotel/notifications")}
      />
      {hasUnread ? (
        // Hidden from AT: the count already lives in the button's accessible
        // name above, so this visual pill would otherwise be announced twice.
        <span aria-hidden="true">
          <Badge tone="danger">{unread}</Badge>
        </span>
      ) : null}
    </span>
  );
}
