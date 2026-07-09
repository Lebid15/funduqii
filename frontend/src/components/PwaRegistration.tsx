"use client";

import { useEffect } from "react";

/**
 * Registers the minimal offline-fallback service worker (Phase 17).
 * Fails silently: the app is fully functional without it, and no feature
 * depends on the worker being active.
 */
export function PwaRegistration() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Registration is a progressive enhancement only.
    });
  }, []);

  return null;
}
