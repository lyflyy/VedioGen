import { expect, test } from "@playwright/test";
import { expectNoHorizontalOverflow } from "./helpers";

test("failed advice stops loading and retries only on explicit action", async ({ page }, testInfo) => {
  let attempts = 0;
  await page.route("**/projects/*/advisor-runs", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({ status: 502, contentType: "application/json", body: JSON.stringify({ detail: "测试模型超时" }) });
    } else {
      await route.continue();
    }
  });
  await page.goto("/projects/new");
  await page.getByLabel("视频想法").fill("春风 800MT：完整环绕和沙漠驾驶，平台准备素材。");
  await page.getByRole("button", { name: "获取创意建议" }).click();
  await expect(page.getByText("创意建议未完成", { exact: true })).toBeVisible();
  await expect(page.getByText("正在形成创意判断", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("advisor-failed-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("advisor-failed-mobile.png") });
  await page.getByRole("button", { name: "重新载入", exact: true }).click();
  // Reloading workspace data is not authorization for another provider call.
  await expect(page.getByText("创意建议未完成", { exact: true })).toBeVisible();
  expect(attempts).toBe(1);
  await page.getByRole("button", { name: "重新生成建议", exact: true }).click();
  await expect(page.getByRole("button", { name: "采用这个方向" })).toHaveCount(3);
  const projectId = page.url().split("/").at(-2);
  const workspace = await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json();
  expect(workspace.messages).toHaveLength(1);
  expect(attempts).toBe(2);
});

test("text-only advice survives a lost response without another invocation", async ({ page }) => {
  let releaseResponse!: () => void;
  const responseGate = new Promise<void>((resolve) => { releaseResponse = resolve; });
  let completed!: (value: { id: string; projectId: string }) => void;
  const serverResult = new Promise<{ id: string; projectId: string }>((resolve) => { completed = resolve; });

  await page.route("**/projects/*/advisor-runs", async (route) => {
    const response = await route.fetch();
    completed(await response.json());
    await responseGate;
    // Reload intentionally abandons this first response.
    await route.fulfill({ response }).catch(() => {});
  });
  try {
    await page.goto("/projects/new");
    await page.getByLabel("视频想法").fill(
      "春风 800MT：先完整环绕，再沙漠驾驶、仪表特写、涉水抬头，最后山林航拍远拉。只有文字，由平台准备素材。",
    );
    await page.getByRole("button", { name: "获取创意建议" }).click();
    await expect(page).toHaveURL(/\/strategy$/);
    const run = await serverResult;
    await page.reload();
    releaseResponse();
    await expect(page.getByRole("button", { name: "采用这个方向" })).toHaveCount(3);
    const workspace = await (await page.request.get(`/api/v1/projects/${run.projectId}/workspace`)).json();
    expect(workspace.assetVersions).toHaveLength(0);
    expect(workspace.latestAdvisorRunId).toBe(run.id);
    const repeated = await page.request.post(`/api/v1/projects/${run.projectId}/advisor-runs`);
    expect(repeated.status()).toBe(202);
    expect((await repeated.json()).id).toBe(run.id);
    const invocations = await (await page.request.get(
      "/api/v1/admin/model-invocations?capabilityAlias=creative-advisor&pageSize=100",
    )).json();
    expect(invocations.items.filter((item: { projectId: string }) => item.projectId === run.projectId)).toHaveLength(1);
    await page.getByRole("button", { name: "采用这个方向" }).first().click();
    await expect(page).toHaveURL(/\/brief$/);
    await expect(page.getByRole("button", { name: "确认并生成脚本" })).toBeEnabled();
  } finally {
    releaseResponse();
  }
});
