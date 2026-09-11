import { chromium, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const origin = "http://127.0.0.1:3001";
const directory = path.resolve(".data/internal-mvp/official-platform-evidence");
await mkdir(directory, { recursive: true });
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(30_000);
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
try {
  const response = await page.request.post(`${origin}/api/v1/projects`, { data: {
    title: "官网素材链路工程验证（非正式样片）",
    initialMessage: "工程测试：春风800MT 官网版本候选及800MT-ES仪表参考导入。不代替项目方确认正式车型版本。",
  } });
  expect(response.status()).toBe(201);
  const project = await response.json();
  const root = `${origin}/api/v1/projects/${project.id}`;
  await page.goto(`${origin}/projects/${project.id}/intake`);
  await page.getByLabel("素材来源").selectOption("manufacturer");
  await page.getByLabel("检索主体").fill("春风800MT");
  await page.getByLabel("镜头关键词").fill("仪表");
  const search = async () => {
    const queued = page.waitForResponse((r) => r.url().endsWith("/asset-discoveries") && r.request().method() === "POST");
    await page.getByRole("button", { name: "搜索参考素材" }).click();
    const result = await queued;
    expect(result.status()).toBe(202);
    const initial = await result.json();
    let run;
    await expect.poll(async () => {
      run = (await (await page.request.get(root + "/asset-discoveries/latest")).json()).run;
      return run?.id === initial.id && !["queued", "running"].includes(run.status);
    }, { timeout: 90_000, intervals: [1000] }).toBe(true);
    expect(run.status, JSON.stringify(run)).toBe("ready");
    await expect(page.getByRole("button", { name: "搜索参考素材" })).toBeEnabled({ timeout: 10_000 });
    return run;
  };
  const related = await search();
  expect(related.result.candidates[0].requiresVariantConfirmation).toBe(true);
  await expect(page.getByRole("button", { name: "确认版本并采用" })).toBeEnabled({ timeout: 20_000 });
  const rejected = await page.request.post(`${root}/asset-discoveries/${related.id}/candidates/${related.result.candidates[0].id}/import`, { data: { confirmSubject: true } });
  expect(rejected.status()).toBe(422);
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "确认版本并采用" }).click();
  expect((await (await page.request.get(root + "/workspace")).json()).assetVersions).toHaveLength(0);
  await page.screenshot({ path: path.join(directory, "variant-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(directory, "variant-mobile.png"), fullPage: true });

  // Explicit ES selection is confined to this engineering project, not the user's sample.
  await page.getByLabel("检索主体").fill("春风800MT-ES");
  const exact = await search();
  expect(exact.result.candidates[0].requiresVariantConfirmation).toBe(false);
  await page.reload();
  await expect(page.getByLabel("素材来源")).toHaveValue("manufacturer");
  await expect(page.getByLabel("检索主体")).toHaveValue("春风800MT-ES");
  await expect(page.getByLabel("镜头关键词")).toHaveValue("仪表");
  const adopt = page.getByRole("button", { name: "确认主体并采用" });
  await expect(adopt).toBeEnabled({ timeout: 20_000 });
  page.once("dialog", (dialog) => dialog.accept());
  await adopt.click();
  await expect(page.getByRole("button", { name: "已采用", exact: true })).toBeVisible({ timeout: 45_000 });
  const workspace = await (await page.request.get(root + "/workspace")).json();
  expect(workspace.assetVersions).toHaveLength(1);
  const asset = workspace.assetVersions[0];
  expect(asset.subject).toBe("春风 800MT-ES");
  expect(asset.referenceSource).toBe("manufacturer");
  const bytes = await (await page.request.get(origin + asset.previewUrl)).body();
  const sha256 = "sha256:" + createHash("sha256").update(bytes).digest("hex");
  expect(sha256).toBe(asset.sha256);
  await writeFile(path.join(directory, "imported-dashboard.jpg"), bytes);
  await expect.poll(() => page.locator(".reference-image img").first().evaluate((img) => img.naturalWidth)).toBeGreaterThan(500);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(directory, "adopted-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: path.join(directory, "adopted-desktop.png"), fullPage: true });
  expect(errors).toEqual([]);
  const evidence = { scope: "engineering project only; formal ES choice pending", projectId: project.id,
    variantRunId: related.id, exactRunId: exact.id, rejectedWithoutVersionConfirmation: rejected.status(), asset, sha256, errors };
  await writeFile(path.join(directory, "result.json"), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence, null, 2));
} catch (error) {
  await page.screenshot({ path: path.join(directory, "failure.png"), fullPage: true });
  throw error;
} finally {
  await browser.close();
}
