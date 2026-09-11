import { chromium, expect as baseExpect } from "@playwright/test";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

if (process.env.RUN_ZXMOTO_REFERENCE !== "1") throw new Error("Set RUN_ZXMOTO_REFERENCE=1 for official reference search and delegated adoption. No model calls.");
const origin = "http://127.0.0.1:3001";
const directory = path.resolve(".data/internal-mvp/zxmoto-820rr-platform");
await mkdir(directory, { recursive: true });
const reportPath = path.join(directory, "result.json");
let evidence;
try { evidence = JSON.parse(await readFile(reportPath, "utf8")); }
catch (error) { if (error.code !== "ENOENT") throw error; }
evidence ??= { scope: "User delegated selection of any real ZXMOTO; platform chose red 820RR. References only, not a completed video.", searches: {}, errors: [] };
const persist = () => writeFile(reportPath, JSON.stringify(evidence, null, 2));
const expect = baseExpect.configure({ timeout: 60_000 });
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(60_000);
page.on("pageerror", (error) => evidence.errors.push(error.message));
page.on("dialog", (dialog) => dialog.accept());
await page.route("**/api/v1/**", (route) => {
  const request = route.request();
  const pathname = new URL(request.url()).pathname;
  if (!["GET", "HEAD"].includes(request.method()) && !pathname.endsWith("/asset-discoveries") && !pathname.endsWith("/import")) {
    evidence.errors.push(`Unexpected mutation: ${pathname}`);
    return route.abort();
  }
  return route.continue();
});
try {
  if (!evidence.projectId) {
    const response = await page.request.post(`${origin}/api/v1/projects`, { data: {
      title: "张雪 820RR 最酷视频", contentPackId: "motorcycle", mode: "real-subject",
      targetPlatform: "douyin", locale: "zh-CN", assetVersionIds: [],
      initialMessage: "用户已明确可以任选一辆真实张雪机车，不再限定800X。平台根据官网素材选择张雪820RR红色版本。保留原始目标：车辆细节特写、完整360度3D环绕，最后一个分镜必须是穿皮衣的骑手骑在车上的高速驾驶镜头，结尾后不得追加CTA。用户只有文字，素材由平台准备。官网多角度图片只是参考，不代表已获得三维模型。不要虚构车辆参数，也不要用其他品牌或其他配色替代。",
    } });
    expect(response.status()).toBe(201);
    evidence.projectId = (await response.json()).id;
    await persist();
  }
  const root = `${origin}/api/v1/projects/${evidence.projectId}`;
  const referenceCatalog = JSON.parse(await readFile(path.resolve(".data/internal-mvp/zxmoto-820rr-official/catalog.json"), "utf8"));
  for (const [focus, indices] of [["配色组 3", [17,18,19,20,21,22,23,24]], ["细节", [25,26,27,28,29,30]]]) {
    const workspace = await (await page.request.get(root + "/workspace")).json();
    if (indices.every((index) => workspace.assetVersions.some((asset) => asset.sourceImageUrl === referenceCatalog.candidates.find((c) => c.index === index).imageUrl))) continue;
    await page.goto(`${origin}/projects/${evidence.projectId}/intake`, { waitUntil: "domcontentloaded" });
    let run = (await (await page.request.get(root + "/asset-discoveries/latest")).json()).run;
    if (run?.result.subject !== "张雪 820RR" || run?.result.searchFocus !== focus || run?.result.source !== "manufacturer") {
      expect(["queued", "running"].includes(run?.status)).toBe(false);
      await page.getByLabel("素材来源").selectOption("manufacturer");
      await page.getByLabel("检索主体").fill("张雪 820RR");
      await page.getByLabel("镜头关键词").fill(focus);
      const queued = page.waitForResponse((r) => r.url().endsWith("/asset-discoveries") && r.request().method() === "POST");
      await page.getByRole("button", { name: "搜索参考素材" }).click();
      expect((await queued).status()).toBe(202);
    }
    await expect.poll(async () => {
      run = (await (await page.request.get(root + "/asset-discoveries/latest")).json()).run;
      return !["queued", "running"].includes(run?.status);
    }, { timeout: 90_000, intervals: [1000] }).toBe(true);
    expect(run.status, run.errorMessage ?? "").toBe("ready");
    expect(run.result.candidates.map((c) => c.referenceIndex)).toEqual(indices);
    evidence.searches[focus] = run;
    await persist();
    await page.reload({ waitUntil: "domcontentloaded" });
    const cards = page.locator(".reference-candidate");
    await expect(cards).toHaveCount(indices.length);
    for (let index = 0; index < indices.length; index++) {
      const candidate = run.result.candidates[index];
      if (candidate.assetId) continue;
      const card = cards.nth(index);
      await card.scrollIntoViewIfNeeded();
      await expect.poll(() => card.locator("img").evaluate((img) => img.complete && img.naturalWidth > 0)).toBe(true);
      const imported = page.waitForResponse((r) => r.url().endsWith(`/candidates/${candidate.id}/import`) && r.request().method() === "POST");
      await card.getByRole("button", { name: "确认主体并采用", exact: true }).click();
      const response = await imported;
      expect(response.status(), await response.text()).toBe(201);
      await expect(card.getByRole("button", { name: "已采用", exact: true })).toBeVisible();
    }
    await cards.first().scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(directory, `references-${indices[0]}-desktop.png`) });
    await page.setViewportSize({ width: 390, height: 844 });
    await cards.first().scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.join(directory, `references-${indices[0]}-mobile.png`) });
    await page.setViewportSize({ width: 1440, height: 1000 });
  }
  evidence.workspace = await (await page.request.get(root + "/workspace")).json();
  expect(evidence.workspace.assetVersions).toHaveLength(14);
  for (const asset of evidence.workspace.assetVersions) {
    const expected = referenceCatalog.candidates.find((c) => c.imageUrl === asset.sourceImageUrl);
    expect(asset.sha256).toBe(`sha256:${expected.sha256}`);
    expect(asset.subject).toBe("张雪 820RR");
  }
  expect(evidence.workspace.project.currentStoryboardVersionId).toBeNull();
  expect(evidence.errors).toEqual([]);
  evidence.verifiedAt = new Date().toISOString();
  delete evidence.failure;
  await persist();
  console.log(JSON.stringify({ projectId: evidence.projectId, imported: 14, directory }));
} catch (error) {
  evidence.failure = String(error);
  await persist();
  await page.screenshot({ path: path.join(directory, "failure.png"), fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
