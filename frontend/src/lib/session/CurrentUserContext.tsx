"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { CurrentUser } from "@/lib/api/types";

const CurrentUserContext = createContext<CurrentUser | null>(null);

/** Provides the authenticated platform owner to client components under the
 * AppShell (e.g. the dashboard welcome). The server layout resolves the user;
 * this only shares it — it is never the authorization source of truth. */
export function CurrentUserProvider({
  user,
  children,
}: {
  user: CurrentUser;
  children: ReactNode;
}) {
  return (
    <CurrentUserContext.Provider value={user}>
      {children}
    </CurrentUserContext.Provider>
  );
}

export function useCurrentUser(): CurrentUser | null {
  return useContext(CurrentUserContext);
}
