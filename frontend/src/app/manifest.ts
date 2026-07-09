import type { MetadataRoute } from "next";

/**
 * PWA Web App Manifest (Phase 17). Installability only — no offline data,
 * no push, no background sync. Colors mirror the design tokens
 * (--color-primary / --color-bg).
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Funduqii — فندقي",
    short_name: "Funduqii",
    description: "Hotel management platform — hotels, bookings and operations.",
    id: "/",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait-primary",
    theme_color: "#166a53",
    background_color: "#f6f4ee",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/icons/icon-maskable-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
