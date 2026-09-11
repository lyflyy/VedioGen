import { expect, test } from "@playwright/test";
import { expectNoHorizontalOverflow, expectNoSeriousA11yIssues } from "./helpers";

test("Blender configuration is independent of video provider and cannot probe in isolation", async ({ page }) => {
  await page.goto("/admin/video-settings");
  await page.getByLabel("Blender 可执行文件", { exact: true }).fill("D:/tools/blender.exe");
  await page.getByLabel("Blender 超时（秒）").fill("600");
  await page.getByRole("button", { name: "保存视频配置" }).click();
  await expect(page.getByRole("status").filter({ hasText: "配置已保存" })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Blender 可执行文件", { exact: true })).toHaveValue("D:/tools/blender.exe");
  await expect(page.getByLabel("Blender 超时（秒）")).toHaveValue("600");
  await expect(page.getByLabel("启用 Blender 环绕")).not.toBeChecked();
  await page.getByRole("button", { name: "检查已保存的 Blender", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "当前环境禁止本地 Blender 执行" })).toBeVisible();
  await expectNoSeriousA11yIssues(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
});
