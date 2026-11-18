import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { pretendToBeVisual: true } },
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.tsx"],
    fileParallelism: false,
    maxWorkers: 1,
    testTimeout: 10_000,
  },
});
