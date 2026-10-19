/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Dev-server settings come from frontend/.env (see .env.example) or the shell:
//   VITE_HOST          bind address (default 127.0.0.1; 0.0.0.0 = LAN access)
//   VITE_PORT          listen port (default 4173)
//   VITE_API_TARGET    backend the /api proxy forwards to (default local :8000)
// No server URLs are hardcoded; the built app served by the backend uses
// relative /api paths and works over the network as-is.
export default defineConfig(({ mode }) => {
  // Read frontend/.env (VITE_HOST / VITE_PORT / VITE_API_TARGET — see
  // .env.example). `loadEnv(mode, ".")` resolves from the frontend folder,
  // which is the CWD for every npm script.
  const env = loadEnv(mode, ".", "");
  const host = env.VITE_HOST || "127.0.0.1";
  const port = Number(env.VITE_PORT || 4173);
  const apiTarget = env.VITE_API_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    server: {
      host,
      port,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "node",
      include: ["src/**/*.test.ts"],
    },
  };
});
