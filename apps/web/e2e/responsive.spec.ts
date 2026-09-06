import { expect, test } from "@playwright/test";

import { expectNoHorizontalOverflow, expectNoSeriousA11yIssues } from "./helpers";

test("@chromium-only creator and admin shells remain usable across target viewports", async ({ page, browserName }, testInfo) => {
  test.skip(browserName !== "chromium");
  const viewports = [
    { width: 1440, height: 900 },
    { width: 1024, height: 768 },
    { width: 390, height: 844 },
    { width: 320, height: 568 },
  ];

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.goto("/projects/new");
    await expect(page.getByRole("heading", { name: "你想制作什么视频？" })).toBeVisible();
    await expect(page.getByRole("button", { name: "获取创意建议" })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await page.goto("/admin/model-providers");
    await expect(page.getByRole("heading", { name: "模型平台", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "添加平台" })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    if (viewport.width === 320) await page.screenshot({ path: testInfo.outputPath("admin-320.png"), fullPage: true });
  }

  await expectNoSeriousA11yIssues(page);
});
