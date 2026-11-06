import { defineConfig } from "@playwright/test";
import { resolve } from "node:path";
import { tmpdir } from "node:os";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:8000",
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: {
    gracefulShutdown: { signal: "SIGTERM", timeout: 10000 },
    command: "../.venv/bin/python ../scripts/run.py",
    url: "http://127.0.0.1:8000/api/settings",
    reuseExistingServer: !process.env.CI,
    env: { TOOLKIT_DB: resolve(tmpdir(), `toolkit-browser-${process.pid}.db`) },
  },
});
