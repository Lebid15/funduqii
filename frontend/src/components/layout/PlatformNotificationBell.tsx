"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell } from "lucide-react";

import { Badge, IconButton } from "@/components/ui";
import { getPlatformUnreadCount } from "@/lib/api/platform";
import { useI18n } from "@/lib/i18n/I18nProvider";

const POLL_MS = 60_000;

/**
 * Platform-owner topbar bell (notifications closure). Reads the owner's own
 * platform-scoped unread count with light 60s polling (paused while the tab is
 * hidden, cleared on unmount). Clicking opens the platform notifications page.
 * Only mounted inside the platform console shell — never on the public site.
 */
export function PlatformNotificationBell() {
  const { t } = useI18n();
  const router = useRouter();
  const [unread, setUnread] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;
    const load = () => {
      if (inFlight || (typeof document !== "undefined" && document.hidden)) return;
      inFlight = true;
      getPlatformUnreadCount()
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
  }, []);

  return (
    <span className="cluster">
      <IconButton
        label={t.notifications.bell}
        icon={Bell}
        onClick={() => router.push("/platform/notifications")}
      />
      {unread !== null && unread > 0 ? <Badge tone="danger">{unread}</Badge> : null}
    </span>
  );
}
