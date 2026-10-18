import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

declare const process: { env: Record<string, string | undefined> };

// In docker-compose the dev server proxies to the `backend` service instead of localhost.
const API_TARGET = process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    host: true,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
      "/uploads": { target: API_TARGET, changeOrigin: true },
    },
  },
  preview: { port: 5173 },
});
