import { expect, test } from "@playwright/test";
import { expectNoHorizontalOverflow, expectNoSeriousA11yIssues } from "./helpers";

test("text-only project exposes clarification and search failure without fabricated assets", async ({ page }) => {
  const response = await page.request.post("/api/v1/projects", { data: { title: "文字素材准备", initialMessage: "春风 800MT，车辆环绕和山林远拉" } });
  const project = await response.json();
  await page.goto(`/projects/${project.id}/intake`);
  await page.getByRole("button", { name: "从描述准备素材" }).click();
  await expect(page.getByText("隔离测试未调用真实模型；请填写要检索的主体名称")).toBeVisible();
  await page.getByLabel("检索主体").fill("春风 800MT");
  await page.getByLabel("镜头关键词").fill("仪表特写");
  await page.getByRole("button", { name: "搜索参考素材" }).click();
  await expect(page.getByText("当前环境禁止外部素材检索")).toBeVisible();
  await page.reload();
  await expect(page.getByText("当前环境禁止外部素材检索")).toBeVisible();
  await expect(page.getByLabel("镜头关键词")).toHaveValue("仪表特写");
  expect((await (await page.request.get(`/api/v1/projects/${project.id}/workspace`)).json()).assetVersions).toHaveLength(0);
  await expect(page.locator(".reference-candidate")).toHaveCount(0);
});

test("reference candidate UI contract handles confirmation, download error and responsive layout", async ({ page }, testInfo) => {
  const response = await page.request.post("/api/v1/projects", { data: { title: "候选界面测试", initialMessage: "CFMOTO 800MT 环绕" } });
  const project = await response.json();
  const candidate = { id: "candidate-test", title: "CFMOTO 800MT - UI test fixture", imageUrl: "/images/motorcycle-studio.jpg", thumbnailUrl: "https://media.example.test/thumb.jpg", sourceUrl: "https://source.example.test/800mt", assetId: null };
  await page.route("https://media.example.test/thumb.jpg", (route) => route.abort());
  await page.route(`**/projects/${project.id}/asset-discoveries/latest`, (route) => route.fulfill({ json: { run: { id: "run-test", status: "ready", errorMessage: null, result: { subject: "CFMOTO 800MT", requiredShots: ["环绕", "山林远拉"], candidates: [candidate] } } } }));
  let confirmations = 0;
  await page.route(`**/projects/${project.id}/asset-discoveries/run-test/candidates/candidate-test/import`, (route) => {
    expect(route.request().postDataJSON()).toEqual({ confirmSubject: true });
    confirmations += 1;
    return route.fulfill({ status: 422, json: { detail: "素材站点暂时无法下载（HTTP 403）" } });
  });
  await page.goto(`/projects/${project.id}/intake`);
  await page.getByRole("button", { name: "选择镜头 2 关键词" }).click();
  await expect(page.getByLabel("镜头关键词")).toHaveValue("山林远拉");
  await expect(page.getByLabel("检索主体")).toHaveValue("CFMOTO 800MT");
  await expect(page.getByRole("button", { name: "确认主体并采用" })).toBeEnabled();
  await expect(page.locator(".reference-image img")).toHaveAttribute("src", candidate.imageUrl);
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "确认主体并采用" }).click();
  expect(confirmations).toBe(0);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "确认主体并采用" }).click();
  await expect(page.getByText("素材站点暂时无法下载（HTTP 403）")).toBeVisible();
  expect(confirmations).toBe(1);
  await expectNoHorizontalOverflow(page);
  await expectNoSeriousA11yIssues(page);
  await page.screenshot({ path: testInfo.outputPath("reference-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("reference-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 320, height: 740 });
  await expectNoHorizontalOverflow(page);
  await page.route("**/images/motorcycle-studio.jpg", (route) => route.abort());
  await page.reload();
  await expect(page.getByText("预览加载失败")).toBeVisible();
  await expect(page.getByRole("button", { name: "确认主体并采用" })).toBeDisabled();
});

test("official candidate requires explicit model-version adoption", async ({ page }, testInfo) => {
  const project = await (await page.request.post("/api/v1/projects", { data: { title: "官网版本确认测试", initialMessage: "春风800MT 仪表" } })).json();
  const candidate = { id: "official-test", title: "CFMOTO 800MT-ES · 仪表", imageUrl: "/images/motorcycle-studio.jpg", thumbnailUrl: "/images/motorcycle-studio.jpg", sourceUrl: "https://www.cfmoto.com/motorcycles/800mt-es", assetId: null, modelName: "春风 800MT-ES", sourceType: "manufacturer", requiresVariantConfirmation: true };
  await page.route(`**/projects/${project.id}/asset-discoveries/latest`, (route) => route.fulfill({ json: { run: { id: "official-run", status: "ready", errorMessage: null, result: { subject: "春风800MT", source: "manufacturer", searchFocus: "仪表", candidates: [candidate] } } } }));
  let imports = 0;
  await page.route(`**/projects/${project.id}/asset-discoveries/official-run/candidates/official-test/import`, (route) => {
    expect(route.request().postDataJSON()).toEqual({ confirmSubject: true, confirmVariant: true });
    imports += 1;
    return route.fulfill({ status: 422, json: { detail: "隔离测试没有下载官网图片" } });
  });
  await page.goto(`/projects/${project.id}/intake`);
  await expect(page.getByLabel("素材来源")).toHaveValue("manufacturer");
  await expect(page.getByText("官网版本：春风 800MT-ES · 尚未确认采用")).toBeVisible();
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("确认采用该版本为本项目车型");
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: "确认版本并采用" }).click();
  expect(imports).toBe(0);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "确认版本并采用" }).click();
  await expect(page.getByText("隔离测试没有下载官网图片")).toBeVisible();
  expect(imports).toBe(1);
  await expectNoSeriousA11yIssues(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("official-variant-mobile.png"), fullPage: true });
});
