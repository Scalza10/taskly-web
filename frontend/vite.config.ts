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
        theme_color: "#eae7e7",
        background_color: "#eae7e7",
        icons: [
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
          { src: "maskable-icon-512x512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // The fonts too (Archivo, bundled from @fontsource), so the page looks the same offline.
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff2}"],
        // The page handles data itself (store.ts, sync.ts); the service worker only serves the page's files.
        // /oauth/ is the server's sign-in page for AI agents (MCP); it must never get index.html.
        navigateFallbackDenylist: [/^\/api\//, /^\/health$/, /^\/docs/, /^\/redoc/, /^\/openapi\.json$/,
          /^\/oauth\//, /^\/mcp/, /^\/\.well-known\//],
      },
    }),
  ],
  build: { outDir: "../taskly/static", emptyOutDir: true },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: backend },
      "/health": { target: backend },
      "/oauth": { target: backend },
      "/mcp": { target: backend },
      "/.well-known": { target: backend },
    },
  },
  test: { environment: "node" },
});
