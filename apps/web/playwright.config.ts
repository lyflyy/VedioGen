import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const root = path.resolve(__dirname, "../..");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], channel: "msedge", viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    {
      command: "npm run api:dev",
      cwd: root,
      url: "http://127.0.0.1:8000/api/v1/health",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: {
        VEDIOGEN_DATABASE_URL: "sqlite:///./.data/e2e/vediogen.db",
        VEDIOGEN_DATA_DIR: "./.data/e2e",
      },
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3000",
      cwd: path.join(root, "apps/web"),
      url: "http://127.0.0.1:3000/projects",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: { VEDIOGEN_API_ORIGIN: "http://127.0.0.1:8000" },
    },
  ],
});
