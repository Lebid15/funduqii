import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import type { ReactNode } from "react";

import "@/styles/globals.css";
import { PwaRegistration } from "@/components/PwaRegistration";
import { ToastProvider } from "@/components/ui";
import { LOCALE_COOKIE, dir, resolveLocale } from "@/lib/i18n/config";
import { I18nProvider } from "@/lib/i18n/I18nProvider";

export const metadata: Metadata = {
  title: "Funduqii",
  description: "Funduqii — hotel management platform.",
  // Phase 17 — PWA: apple install metadata (the manifest itself is served
  // from app/manifest.ts).
  appleWebApp: {
    capable: true,
    title: "Funduqii",
    statusBarStyle: "default",
  },
  icons: {
    apple: "/icons/apple-touch-icon.png",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0d6e64",
};

/**
 * Root layout. Reads the locale cookie server-side so `<html lang dir>` is
 * correct on the first paint (no RTL/LTR flash), then hands the locale to the
 * client i18n provider. The toast provider is app-wide.
 */
export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);

  return (
    <html lang={locale} dir={dir(locale)}>
      <body>
        <I18nProvider initialLocale={locale}>
          <ToastProvider>{children}</ToastProvider>
        </I18nProvider>
        <PwaRegistration />
      </body>
    </html>
  );
}
