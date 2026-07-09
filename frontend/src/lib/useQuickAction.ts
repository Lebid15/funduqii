"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * Consumes a one-shot `?action=<expected>` param (the topbar Quick Actions
 * bar): fires the callback ONCE — to open an EXISTING create form/modal —
 * then strips `action` from the URL (keeping ?tab= etc.) so closing the
 * form, refreshing, or navigating back never re-opens it. Clicking the
 * same quick action again re-adds the param and fires again.
 */
export function useQuickAction(expected: string, onFire: () => void) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const fired = useRef(false);
  const shouldFire = searchParams.get("action") === expected;

  useEffect(() => {
    if (!shouldFire) {
      fired.current = false;
      return;
    }
    if (fired.current) return;
    fired.current = true;
    onFire();
    const params = new URLSearchParams(searchParams.toString());
    params.delete("action");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, {
      scroll: false,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot consumer
  }, [shouldFire]);
}
