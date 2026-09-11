import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const root = path.resolve(__dirname, "../..");
const webPort = 3107;
const apiPort = 8107;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], channel: "msedge", viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    {
      command: `uv run --project services/api uvicorn vediogen_api.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: root,
      url: `http://127.0.0.1:${apiPort}/api/v1/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        VEDIOGEN_DATABASE_URL: "sqlite:///./.data/e2e/vediogen.db",
        VEDIOGEN_DATA_DIR: "./.data/e2e",
        VEDIOGEN_ALLOW_FAKE_PROVIDER: "true",
        VEDIOGEN_ALLOW_EXTERNAL_MODELS: "false",
        VEDIOGEN_ALLOW_EXTERNAL_SEARCH: "false",
        VEDIOGEN_ALLOW_LOCAL_MODELS: "false",
      },
    },
    {
      command: `npm run dev -- --hostname 127.0.0.1 --port ${webPort}`,
      cwd: path.join(root, "apps/web"),
      url: `http://127.0.0.1:${webPort}/projects`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: { VEDIOGEN_API_ORIGIN: `http://127.0.0.1:${apiPort}`, VEDIOGEN_NEXT_DIST_DIR: ".next-e2e" },
    },
  ],
});
