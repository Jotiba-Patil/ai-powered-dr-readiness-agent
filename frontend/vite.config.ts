import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, strictPort: true },
  // Recharts dominates the single bundle (~550 kB, ~165 kB gzip); fine for an internal dashboard.
  build: { chunkSizeWarningLimit: 700 },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    css: false,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/api/schema.d.ts", "src/test/**", "src/**/*.test.{ts,tsx}"],
      thresholds: { lines: 80, functions: 80, statements: 80, branches: 80 },
    },
  },
});
