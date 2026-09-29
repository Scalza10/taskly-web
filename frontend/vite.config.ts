import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { VitePWA } from "vite-plugin-pwa";

// npm run dev serves the page on 5173 and sends API calls to uvicorn on 8000.
// No changeOrigin: the Host header must stay localhost:5173, because from phase 1b
// the API refuses writes whose Origin doesn't match the Host.
// Objects, not strings: Vite turns `"/api": "http://..."` into { target, changeOrigin: true }.
const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // A new deploy's page takes over the next time the app is opened.
      registerType: "autoUpdate",
      includeAssets: ["favicon.ico", "apple-touch-icon-180x180.png", "icon.svg"],
      manifest: {
        name: "Taskly",
        short_name: "Taskly",
        description: "Shared to-do lists",
        start_url: "/",
        display: "standalone",
        theme_color: "#f6f6f4",
        background_color: "#f6f6f4",
        icons: [
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
          { src: "maskable-icon-512x512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // The page handles data itself (store.ts, sync.ts); the service worker only serves the page's files.
        navigateFallbackDenylist: [/^\/api\//, /^\/health$/, /^\/docs/, /^\/redoc/, /^\/openapi\.json$/],
      },
    }),
  ],
  build: { outDir: "../taskly/static", emptyOutDir: true },
  server: { port: 5173, strictPort: true, proxy: { "/api": { target: backend }, "/health": { target: backend } } },
  test: { environment: "node" },
});
