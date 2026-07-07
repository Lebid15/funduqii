import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@/styles/globals.css";
import { defaultLocale, dir } from "@/lib/i18n/config";

export const metadata: Metadata = {
  title: "Funduqii",
  description: "Funduqii — hotel management platform (foundation).",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang={defaultLocale} dir={dir(defaultLocale)}>
      <body>{children}</body>
    </html>
  );
}
