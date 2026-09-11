import { expect, test } from "@playwright/test";

test("intake cannot accept text before controlled inputs are hydrated", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route(/\/_next\/static\/.*\.js/, async (route) => {
    await gate;
    await route.continue();
  });
  try {
    await page.goto("/projects/new", { waitUntil: "commit" });
    await expect(page.getByLabel("视频想法")).toBeDisabled();
    await expect(page.getByRole("button", { name: "获取创意建议" })).toBeDisabled();
    release();
    await page.getByLabel("视频想法").fill("纯文字输入");
    await expect(page.locator(".character-count")).toHaveText("5 / 10000");
    await expect(page.getByRole("button", { name: "获取创意建议" })).toBeEnabled();
  } finally { release(); }
});
