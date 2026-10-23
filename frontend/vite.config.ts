import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg", "apple-touch-icon.png"],
      manifest: {
        name: "Grzyby Podkarpacia",
        short_name: "Grzyby",
        description: "Gdzie i kiedy warto szukać grzybów na Podkarpaciu — wskaźnik potencjału siedliska i warunków.",
        lang: "pl",
        theme_color: "#2f4a2c",
        background_color: "#f6f4ee",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "apple-touch-icon.png", sizes: "180x180", type: "image/png" },
        ],
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          // kroje pisma motywów — w lesie bez zasięgu z pamięci podręcznej
          { urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com\//, handler: "CacheFirst",
            options: { cacheName: "fonty", expiration: { maxEntries: 30, maxAgeSeconds: 365 * 86400 }, cacheableResponse: { statuses: [0, 200] } } },
          // Atlas: zdjęcia zatwierdzone są niezmienne — z pamięci podręcznej (działa w lesie bez zasięgu).
          { urlPattern: /\/api\/atlas\/zdjecie\//, handler: "CacheFirst",
            options: { cacheName: "atlas-zdjecia", expiration: { maxEntries: 500, maxAgeSeconds: 365 * 86400 }, cacheableResponse: { statuses: [200] } } },
          { urlPattern: /\/api\/atlas/, handler: "NetworkFirst",
            options: { cacheName: "atlas", networkTimeoutSeconds: 4, expiration: { maxEntries: 100, maxAgeSeconds: 365 * 86400 } } },
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
