"use client";

import { useState } from "react";
import { LogOut } from "lucide-react";

import { Button } from "@/components/ui";
import { useI18n } from "@/lib/i18n/I18nProvider";

/** Signs out via the BFF logout route (blacklists refresh, clears cookies). */
export function LogoutButton() {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);

  async function handleLogout() {
    setBusy(true);
    try {
      await fetch("/api/session/logout", { method: "POST" });
    } finally {
      // Full navigation clears all client state and re-hits the proxy gate.
      window.location.href = "/login";
    }
  }

  return (
    <Button
      variant="dangerSoft"
      size="sm"
      icon={LogOut}
      onClick={handleLogout}
      disabled={busy}
    >
      {busy ? t.auth.loggingOut : t.auth.logout}
    </Button>
  );
}
