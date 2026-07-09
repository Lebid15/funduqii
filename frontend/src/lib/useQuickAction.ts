"use client";

import { useEffect, useRef } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/** One-shot params consumed together with `action` (quick-operation extras
 * like a preselected room). Stripped from the URL after firing. */
const EXTRA_PARAMS = ["room", "room_type", "q"];

/**
 * Consumes a one-shot `?action=<expected>` param (quick actions / the rooms
 * operational board): fires the callback ONCE with the CURRENT search params
 * — to open an EXISTING create form/modal, optionally preselecting an entity
 * — then strips `action` (+ its extras) from the URL (keeping ?tab= etc.),
 * so closing the form, refreshing, or navigating back never re-opens it.
 * Clicking the same quick action again re-adds the param and fires again.
 */
export function useQuickAction(
  expected: string,
  onFire: (params: URLSearchParams) => void,
) {
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
    onFire(new URLSearchParams(searchParams.toString()));
    const params = new URLSearchParams(searchParams.toString());
    params.delete("action");
    for (const key of EXTRA_PARAMS) params.delete(key);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, {
      scroll: false,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot consumer
  }, [shouldFire]);
}
