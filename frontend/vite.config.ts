import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// npm run dev serves the page on 5173 and sends API calls to uvicorn on 8000.
// No changeOrigin: the Host header must stay localhost:5173, because from phase 1b
// the API refuses writes whose Origin doesn't match the Host.
const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../taskly/static", emptyOutDir: true },
  server: { port: 5173, strictPort: true, proxy: { "/api": backend, "/health": backend } },
  test: { environment: "node" },
});
