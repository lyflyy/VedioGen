import { expect, test } from "@playwright/test";
import path from "node:path";

import {
  expectNoHorizontalOverflow,
  expectNoSeriousA11yIssues,
} from "./helpers";

test("creator uses fixture advice and real uploaded media to compose, retry and download", async ({
  page,
}, testInfo) => {
  test.setTimeout(180_000);
  const title = `张雪 800X 最酷视频 ${Date.now()}`;
  await page.goto("/projects/new");
  await page
    .getByLabel("视频想法")
    .fill(
      `${title}：车辆 360 度环绕，聚焦灯组、发动机和轮胎细节，最后是穿皮衣的骑手高速驾驶镜头。`,
    );
  await page.locator('input[type="file"]').setInputFiles(path.resolve(__dirname, "../public/images/motorcycle-studio.jpg"));
  await page.getByRole("button", { name: "获取创意建议" }).click();

  await expect(page).toHaveURL(/\/projects\/[^/]+\/strategy/);
  const projectId = page.url().split("/").at(-2);
  const workspaceResponse = await page.request.get(
    `/api/v1/projects/${projectId}/workspace`,
  );
  expect((await workspaceResponse.json()).assetVersions).toHaveLength(1);
  await expect(
    page.getByRole("heading", { name: "选择一个叙事方向" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "采用这个方向" })).toHaveCount(
    3,
  );
  const invocationCountBeforeReload = (
    await (
      await page.request.get(
        "/api/v1/admin/model-invocations?capabilityAlias=creative-advisor&pageSize=100",
      )
    ).json()
  ).items.filter(
    (item: { projectId: string }) => item.projectId === projectId,
  ).length;
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "选择一个叙事方向" }),
  ).toBeVisible();
  const invocationCountAfterReload = (
    await (
      await page.request.get(
        "/api/v1/admin/model-invocations?capabilityAlias=creative-advisor&pageSize=100",
      )
    ).json()
  ).items.filter(
    (item: { projectId: string }) => item.projectId === projectId,
  ).length;
  expect(invocationCountAfterReload).toBe(invocationCountBeforeReload);
  await page
    .getByLabel("补充创意要求")
    .fill("最后一个镜头必须是皮衣骑手高速驾驶，不要追加 CTA。 ");
  const regenerated = page.waitForResponse(
    (response) =>
      response.url().includes(`/projects/${projectId}/advisor-runs`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发送" }).click();
  expect((await regenerated).status()).toBe(202);
  await expect(page.getByText("2 条输入")).toBeVisible();
  await page.getByRole("button", { name: "采用这个方向" }).first().click();

  await expect(page).toHaveURL(/\/brief$/);
  await expect(page.getByText("Creative Brief · 版本 1")).toBeVisible();
  await page.getByRole("button", { name: "确认并生成脚本" }).click();

  await expect(page).toHaveURL(/\/storyboard$/);
  await expect(page.getByText("5 个镜头")).toBeVisible();
  await page.getByText("高级设置", { exact: true }).click();
  await page.getByRole("combobox", { name: "镜头素材", exact: true }).selectOption({ index: 1 });
  await page.getByRole("button", { name: "应用到同类镜头" }).click();
  const originalAssetId = await page.getByRole("combobox", { name: "镜头素材", exact: true }).inputValue();
  await page.getByRole("button", { name: "调整参考图" }).click();
  const cropDialog = page.getByRole("dialog", { name: "参考图构图" });
  await expect(cropDialog.getByRole("img", { name: "待裁剪参考图" })).toBeVisible();
  await expect(cropDialog.getByRole("button", { name: "保存并应用到当前镜头" })).toBeEnabled();
  await cropDialog.getByRole("slider", { name: "裁剪水平位置" }).press("End");
  await expectNoSeriousA11yIssues(page);
  await page.screenshot({ path: testInfo.outputPath("crop-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("crop-mobile.png") });
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect((await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json()).assetVersions).toHaveLength(1);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("button", { name: "调整参考图" }).click();
  await cropDialog.getByRole("slider", { name: "裁剪水平位置" }).press("End");
  await page.route("**/assets/*/crops", (route) => route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: "裁剪保存失败，请重试" }) }));
  await cropDialog.getByRole("button", { name: "保存并应用到当前镜头" }).click();
  await expect(cropDialog.getByRole("alert")).toHaveText("裁剪保存失败，请重试");
  await expect(page.getByRole("combobox", { name: "镜头素材", exact: true, includeHidden: true })).toHaveValue(originalAssetId);
  await page.unroute("**/assets/*/crops");
  const cropResult = page.waitForResponse((response) => response.url().endsWith("/crops") && response.request().method() === "POST");
  await cropDialog.getByRole("button", { name: "保存并应用到当前镜头" }).click();
  const cropResponse = await cropResult;
  expect(cropResponse.status()).toBe(201);
  const croppedAsset = await cropResponse.json();
  expect(croppedAsset.sourceAssetId).toBe(originalAssetId);
  await expect(page.getByRole("combobox", { name: "镜头素材", exact: true })).toHaveValue(croppedAsset.id);
  await page.locator(".shot-item").nth(1).click();
  await expect(page.getByRole("combobox", { name: "镜头素材", exact: true })).toHaveValue(originalAssetId);
  const saveResult = page.waitForResponse((response) => response.url().includes("/storyboards/") && response.request().method() === "PUT");
  await page.getByRole("button", { name: "保存分镜", exact: true }).click();
  expect((await saveResult).status()).toBe(200);
  await page.reload();
  await page.getByText("高级设置", { exact: true }).click();
  await expect(page.getByRole("combobox", { name: "镜头素材", exact: true })).toHaveValue(croppedAsset.id);
  for (let index = 0; index < 5; index++) {
    await page.locator(".shot-item").nth(index).click();
    await page.getByLabel("字幕", { exact: true }).fill(`镜头 ${index + 1} 上传素材`);
  }
  await page.screenshot({ path: testInfo.outputPath("storyboard-assets.png"), fullPage: true });
  await page.getByRole("button", { name: "自动准备素材" }).click();
  await expect(page.getByRole("region", { name: "素材准备结果" })).toContainText("素材已就绪");
  await page.getByRole("button", { name: "生成选项" }).click();

  await expect(page).toHaveURL(/\/generation$/);
  await page.getByLabel("输出尺寸").selectOption("preview");
  const creation = page.waitForResponse((response) => response.url().endsWith("/generation-runs") && response.request().method() === "POST");
  await page.getByRole("button", { name: "开始生成" }).click();
  const run = await (await creation).json();
  expect(run.status).toBe("queued");
  await page.reload();
  await expect(page.getByText(`运行 ${run.id.slice(0, 8)}`)).toBeVisible();
  await expect(page.getByRole("link", { name: "查看成片" })).toBeVisible({ timeout: 90_000 });
  const original = await (await page.request.get(`/api/v1/generation-runs/${run.id}`)).json();
  expect(original.shotRuns[0].sourceAssetId).toBe(croppedAsset.id);
  expect(original.shotRuns[1].sourceAssetId).toBe(originalAssetId);
  await page.getByRole("button", { name: "重做镜头 2", exact: true }).click();
  await expect(page.getByRole("link", { name: "查看成片" })).toBeVisible({ timeout: 90_000 });
  const retried = await (await page.request.get(`/api/v1/generation-runs/${run.id}`)).json();
  expect(retried.shotRuns).toHaveLength(6);
  expect(retried.shotRuns[0].artifactId).toBe(original.shotRuns[0].artifactId);
  expect(retried.finalArtifactId).not.toBe(original.finalArtifactId);
  await page.screenshot({ path: testInfo.outputPath("generation-shots.png"), fullPage: true });
  await page.getByRole("link", { name: "查看成片" }).click();
  await expect(page).toHaveURL(/\/final$/);
  await expect(
    page.getByRole("heading", { name: "成片已生成" }),
  ).toBeVisible();
  await expect(page.getByText("540 x 960")).toBeVisible();
  await expect(page.getByText(/12\.[0-2] 秒/)).toBeVisible();

  const video = page.getByLabel("生成的视频成片");
  await expect(video).toBeVisible();
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.readyState)).toBeGreaterThanOrEqual(2);
  const media = await video.evaluate((element: HTMLVideoElement) => ({
    readyState: element.readyState,
    width: element.videoWidth,
    height: element.videoHeight,
    duration: element.duration,
  }));
  expect(media.readyState).toBeGreaterThanOrEqual(1);
  expect(media.width).toBe(540);
  expect(media.height).toBe(960);
  expect(media.duration).toBeGreaterThan(11.9);
  const pixels = await video.evaluate(async (element: HTMLVideoElement) => {
    const canvas = document.createElement("canvas");
    canvas.width = 54; canvas.height = 96;
    const context = canvas.getContext("2d")!;
    async function sample(time: number) {
      await new Promise<void>((resolve) => {
        element.addEventListener("seeked", () => resolve(), { once: true });
        element.currentTime = time;
      });
      context.drawImage(element, 0, 0, 54, 96);
      return Array.from(context.getImageData(0, 0, 54, 96).data);
    }
    const first = await sample(0.2);
    const second = await sample(1.8);
    return { range: Math.max(...first.filter((_, i) => i % 4 !== 3)) - Math.min(...first.filter((_, i) => i % 4 !== 3)),
      changed: first.filter((value, index) => index % 4 !== 3 && Math.abs(value - second[index]) > 3).length };
  });
  expect(pixels.range).toBeGreaterThan(50);
  expect(pixels.changed).toBeGreaterThan(100);
  await expect(page.getByRole("link", { name: "下载 MP4" })).toHaveAttribute(
    "href",
    /\/api\/v1\/artifacts\/.*\/content/,
  );
  await expectNoHorizontalOverflow(page);
  await expectNoSeriousA11yIssues(page);
  await page.screenshot({
    path: testInfo.outputPath("creator-final.png"),
    fullPage: true,
  });
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载 MP4" }).click();
  expect(await (await download).failure()).toBeNull();
  for (const viewport of [{ width: 390, height: 844 }, { width: 320, height: 568 }]) {
    await page.setViewportSize(viewport);
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: testInfo.outputPath(`final-${viewport.width}.png`), fullPage: true });
    await page.goto(`/projects/${projectId}/storyboard`);
    await page.getByText("高级设置", { exact: true }).click();
    await expect(page.getByRole("combobox", { name: "镜头素材", exact: true })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: testInfo.outputPath(`storyboard-${viewport.width}.png`), fullPage: true });
    await page.goto(`/projects/${projectId}/final`);
  }
});
