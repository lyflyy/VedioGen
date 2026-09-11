import { expect, test } from "@playwright/test";
import path from "node:path";
import { expectNoHorizontalOverflow, expectNoSeriousA11yIssues } from "./helpers";

test("incomplete storyboard supports real single-shot preview, reload, stale rejection and adoption", async ({ page }, testInfo) => {
  test.setTimeout(150_000);
  await page.goto("/projects/new");
  await page.getByLabel("视频想法").fill(`单镜头试片测试 ${Date.now()}：春风800MT，环绕、沙漠、仪表、涉水和山林航拍。`);
  await page.locator('input[type="file"]').setInputFiles(path.resolve(__dirname, "../public/images/motorcycle-studio.jpg"));
  await page.getByRole("button", { name: "获取创意建议" }).click();
  await page.getByRole("button", { name: "采用这个方向" }).first().click();
  await page.getByRole("button", { name: "确认并生成脚本" }).click();
  await page.waitForURL("**/storyboard");
  const projectId = page.url().split("/").at(-2);
  const before = await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json();
  const storyboardId = before.project.currentStoryboardVersionId;
  const original = await (await page.request.get(`/api/v1/projects/${projectId}/storyboards/${storyboardId}`)).json();
  // Automatic matching now binds images; keep the other shots explicitly incomplete.
  original.shots = original.shots.map((shot: Record<string, unknown>, index: number) =>
    index ? { ...shot, sourceAssetId: null } : shot);
  expect((await page.request.put(`/api/v1/projects/${projectId}/storyboards/${storyboardId}`, {
    data: { shots: original.shots, totalDurationMs: original.totalDurationMs },
  })).status()).toBe(200);
  await page.reload();
  await expectNoHorizontalOverflow(page);
  const upload = page.locator(".media-upload input[type=file]");
  await upload.focus();
  await expect(upload).toBeFocused();
  expect(await upload.evaluate((input) => input.getBoundingClientRect().width)).toBeLessThanOrEqual(1);
  await page.getByLabel("时长（秒）").fill("1");
  await page.getByText("高级设置", { exact: true }).click();
  await page.getByRole("combobox", { name: "来源", exact: true }).selectOption("image-motion");
  await page.getByRole("combobox", { name: "镜头素材", exact: true }).selectOption({ index: 1 });
  const preview = page.getByRole("region", { name: "单镜头试片" });
  const started = page.waitForResponse((response) => response.url().endsWith("/generation-runs") && response.request().method() === "POST");
  await preview.getByRole("button", { name: "保存并试片" }).click();
  const response = await started;
  expect(response.status()).toBe(202);
  const initialRun = await response.json();
  expect(initialRun.scope).toBe("shot-preview");
  await page.reload();
  await expect(preview.getByRole("button", { name: "采用到当前镜头" })).toBeVisible({ timeout: 60_000 });
  const run = await (await page.request.get(`/api/v1/generation-runs/${initialRun.id}`)).json();
  expect(run.finalArtifactId).toBeNull();
  expect(run.shotRuns).toHaveLength(1);
  const video = page.getByLabel("镜头试片视频");
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThanOrEqual(2);
  await video.evaluate(async (v: HTMLVideoElement) => { v.muted = true; await v.play(); });
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(0.3);
  await expectNoSeriousA11yIssues(page);
  await page.screenshot({ path: testInfo.outputPath("preview-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("preview-mobile.png"), fullPage: true });
  await page.getByLabel("时长（秒）").fill("1.5");
  await preview.getByRole("button", { name: "采用到当前镜头" }).click();
  await expect(preview.getByRole("alert")).toContainText("试片对应镜头已改变");
  await page.getByLabel("时长（秒）").fill("1");
  const adopted = page.waitForResponse((r) => r.url().endsWith("/adoption") && r.request().method() === "POST");
  await preview.getByRole("button", { name: "采用到当前镜头" }).click();
  expect((await adopted).status()).toBe(200);
  await page.getByText("高级设置", { exact: true }).click();
  await expect(page.getByRole("combobox", { name: "来源", exact: true })).toHaveValue("user-video");
  const workspace = await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json();
  expect(workspace.activeGenerationRunId).toBeNull();
  expect(workspace.generationReadiness.ready).toBe(false);
  expect(workspace.assetVersions).toHaveLength(2);
  const saved = await (await page.request.get(`/api/v1/projects/${projectId}/storyboards/${storyboardId}`)).json();
  expect(saved.shots).toHaveLength(original.shots.length);
  expect(saved.shots.slice(1).map((s: { id: string; visual: string; sourceAssetId: string }) => [s.id, s.visual, s.sourceAssetId]))
    .toEqual(original.shots.slice(1).map((s: { id: string; visual: string; sourceAssetId: string }) => [s.id, s.visual, s.sourceAssetId]));
  const downloadEvent = page.waitForEvent("download");
  await preview.getByRole("link", { name: "下载试片" }).click();
  await (await downloadEvent).saveAs(testInfo.outputPath("single-shot.mp4"));
  expect(saved.shots[0].sourceAssetId).toBe(run.shotRuns[0].artifactId);
});
