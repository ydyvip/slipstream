/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // IPv4 loopback: binding to ::1 (the default `localhost` first candidate
    // on Windows) fails with EACCES on this machine.
    host: "127.0.0.1",
    // 5173 falls inside a Hyper-V/WSL reserved port range (5141-5240) on this
    // host, so the bind is refused; 4173 is outside the reserved ranges.
    port: 4173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
