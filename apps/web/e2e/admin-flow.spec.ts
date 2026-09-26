import { expect, test } from "@playwright/test";

import {
  expectNoHorizontalOverflow,
  expectNoSeriousA11yIssues,
} from "./helpers";

test("admin configures and traces a model route without exposing the API key", async ({
  page,
}) => {
  const suffix = `${Date.now()}`;
  const providerId = `e2e-provider-${suffix}`;
  const providerName = `E2E Provider ${suffix}`;
  const credentialAlias = `E2E Key ${suffix}`;
  const deploymentName = `E2E Creative ${suffix}`;
  const secret = `sk-e2e-never-return-${suffix}-4829`;

  await page.goto("/admin/model-providers");
  await expect(page.getByText("Local Fake Provider")).toBeVisible();
  await page.getByRole("button", { name: "添加平台" }).click();
  await page.getByLabel("平台 ID").fill(providerId);
  await page.getByLabel("显示名称").fill(providerName);
  await page.getByLabel("适配器").selectOption("fake");
  await page.getByLabel("Base URL").fill("https://models.example.test/v1");
  await page.getByRole("button", { name: "创建平台" }).click();
  await expect(page.getByText(providerName)).toBeVisible();

  await page.getByRole("link", { name: "API Key", exact: true }).click();
  await page.getByLabel("模型平台").selectOption({ label: providerName });
  await page.getByLabel("凭据别名").fill(credentialAlias);
  await page.getByLabel("API Key").fill(secret);
  await page.getByRole("button", { name: "加密保存" }).click();
  await expect(page.getByText(credentialAlias)).toBeVisible();
  await expect(page.getByLabel("API Key")).toHaveValue("");
  expect(await page.locator("body").textContent()).not.toContain(secret);
  expect(
    await page.evaluate(() =>
      JSON.stringify({ ...localStorage, ...sessionStorage }),
    ),
  ).not.toContain(secret);

  await page.getByRole("link", { name: "模型部署" }).click();
  await page.getByLabel("部署名称").fill(deploymentName);
  await page.getByLabel("模型平台").selectOption({ label: providerName });
  await page.getByLabel("物理模型 ID").fill(`creative-${suffix}`);
  await page
    .getByLabel("调用凭据")
    .selectOption({ label: `${credentialAlias} · 4829` });
  await page.getByRole("button", { name: "创建部署" }).click();
  const deploymentRow = page
    .locator(".deployment-row")
    .filter({ hasText: deploymentName });
  await expect(deploymentRow).toBeVisible();
  await deploymentRow.getByRole("button", { name: "能力探测" }).click();
  await expect(deploymentRow.getByText("就绪")).toBeVisible();

  await page.getByRole("link", { name: "能力路由" }).click();
  await page.getByLabel("主部署").selectOption({ label: deploymentName });
  await page.getByRole("button", { name: "新建草稿" }).click();
  await expect(page.locator(".route-diagram strong")).toHaveText([
    deploymentName,
    deploymentName,
  ]);
  await page.getByRole("button", { name: "验证并发布" }).click();
  await expect(
    page.getByText("Admin console publication").first(),
  ).toBeVisible();

  await page.getByRole("link", { name: "测试台" }).click();
  await page.getByLabel("测试素材").selectOption("zhangxue-800x");
  await page.getByRole("button", { name: "运行测试" }).click();
  await expect(page.getByText("检查完成")).toBeVisible();
  await expect(page.getByText("Fake Provider 结构化探测通过。")).toBeVisible();

  await page.getByRole("link", { name: "调用记录" }).click();
  const firstInvocation = page.locator(".invocation-row").first();
  await expect(firstInvocation).toBeVisible();
  await firstInvocation.click();
  await expect(page.getByText(/^trace-/)).toBeVisible();
  expect(await page.locator("body").textContent()).not.toContain(secret);
  await expectNoHorizontalOverflow(page);
  await expectNoSeriousA11yIssues(page);
});
