import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Command Center is a static SPA. In development it proxies /api to the
// AUTONOMUS backend (uvicorn, default 127.0.0.1:8000); in production the same
// FastAPI process serves this build under /app, so the API base is relative.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 600,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
