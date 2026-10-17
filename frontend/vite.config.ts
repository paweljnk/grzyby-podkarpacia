import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "Grzyby Podkarpacia",
        short_name: "Grzyby",
        description: "Gdzie i kiedy warto szukać grzybów na Podkarpaciu — wskaźnik potencjału siedliska i warunków.",
        lang: "pl",
        theme_color: "#2f4a2c",
        background_color: "#f6f4ee",
        display: "standalone",
        start_url: "/",
        icons: [{ src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          { urlPattern: /\/api\/(gatunki|zrodla)/, handler: "StaleWhileRevalidate", options: { cacheName: "api-static" } },
          { urlPattern: /\/api\//, handler: "NetworkFirst",
            options: { cacheName: "api", networkTimeoutSeconds: 8, expiration: { maxEntries: 200, maxAgeSeconds: 7 * 86400 } } },
        ],
      },
    }),
  ],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  preview: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
