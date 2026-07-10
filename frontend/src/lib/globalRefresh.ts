"use client";

import { useEffect } from "react";

/** Central refresh signal (owner spec): ONE small topbar button fires this
 * event; pages that support refreshing listen and refetch their own data.
 * Pages that don't listen are simply unaffected — no full app reload, no
 * page coupling, deliberately no bigger system than this. */
const REFRESH_EVENT = "funduqii:refresh";

export function triggerGlobalRefresh(): void {
  window.dispatchEvent(new Event(REFRESH_EVENT));
}

export function useGlobalRefresh(onRefresh: () => void): void {
  useEffect(() => {
    const handler = () => onRefresh();
    window.addEventListener(REFRESH_EVENT, handler);
    return () => window.removeEventListener(REFRESH_EVENT, handler);
  }, [onRefresh]);
}
