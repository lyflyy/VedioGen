import { expect, test } from "@playwright/test";

import {
  expectNoHorizontalOverflow,
  expectNoSeriousA11yIssues,
} from "./helpers";

test("creator confirms AI strategy and generates a downloadable vertical MP4", async ({
  page,
}, testInfo) => {
  const title = `张雪 800X 最酷视频 ${Date.now()}`;
  await page.goto("/projects/new");
  await page
    .getByLabel("视频想法")
    .fill(
      `${title}：车辆 360 度环绕，聚焦灯组、发动机和轮胎细节，最后是穿皮衣的骑手高速驾驶镜头。`,
    );
  await page.locator('input[type="file"]').setInputFiles({
    name: "zhangxue-reference.png",
    mimeType: "image/png",
    buffer: Buffer.from("89504e470d0a1a0a0000000d49484452", "hex"),
  });
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
  await page.getByRole("button", { name: "确认分镜" }).click();

  await expect(page).toHaveURL(/\/generation$/);
  await page.getByRole("button", { name: "开始生成" }).click();
  await expect(page).toHaveURL(/\/final$/, { timeout: 45_000 });
  await expect(
    page.getByRole("heading", { name: "视频可以交付" }),
  ).toBeVisible();
  await expect(page.getByText("540 x 960")).toBeVisible();
  await expect(page.getByText("6.0 秒")).toBeVisible();

  const video = page.getByLabel("生成的视频成片");
  await expect(video).toBeVisible();
  const media = await video.evaluate((element: HTMLVideoElement) => ({
    readyState: element.readyState,
    width: element.videoWidth,
    height: element.videoHeight,
    duration: element.duration,
  }));
  expect(media.readyState).toBeGreaterThanOrEqual(1);
  expect(media.width).toBe(540);
  expect(media.height).toBe(960);
  expect(media.duration).toBeGreaterThan(5.9);
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
});
