import { chromium, expect as baseExpect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

if (process.env.RUN_GLOBAL_REFERENCE !== "1") throw new Error("Set RUN_GLOBAL_REFERENCE=1 for live official search. No models or asset adoption.");
const origin = "http://127.0.0.1:3001";
const projectId = "3c21b6ed-7fbd-4a4e-a38d-4983f26340ff";
const root = `${origin}/api/v1/projects/${projectId}`;
const directory = path.resolve(`.data/internal-mvp/global-reference-live-${Date.now()}`);
await mkdir(directory, { recursive: true });
const evidence = { directory, projectId, errors: [], scope: "Candidate search only; no formal version adoption" };
const persist = () => writeFile(path.join(directory, "result.json"), JSON.stringify(evidence, null, 2));
const expect = baseExpect.configure({ timeout: 60_000 });
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(60_000);
page.on("pageerror", (error) => evidence.errors.push(error.message));
await page.route("**/api/v1/**", async (route) => {
  const request = route.request();
  if (!["GET", "HEAD"].includes(request.method()) && !request.url().endsWith("/asset-discoveries")) {
    evidence.errors.push(`Unexpected mutation: ${new URL(request.url()).pathname}`);
    return route.abort();
  }
  return route.continue();
});
try {
  const before = await (await page.request.get(root + "/workspace")).json();
  evidence.assetsBefore = before.assetVersions;
  const endpoint = `${root}/storyboards/${before.project.currentStoryboardVersionId}`;
  evidence.storyboardBefore = await (await page.request.get(endpoint)).json();
  await persist();
  await page.goto(`${origin}/projects/${projectId}/intake`, { waitUntil: "domcontentloaded" });
  const latest = (await (await page.request.get(root + "/asset-discoveries/latest")).json()).run;
  const matches = latest?.result.subject === "春风800MT SPORT" && latest?.result.searchFocus === "棚拍" && latest?.result.source === "manufacturer";
  if (matches) {
    evidence.runId = latest.id;
  } else {
    expect(["queued", "running"].includes(latest?.status)).toBe(false);
    await page.getByLabel("素材来源").selectOption("manufacturer");
    await page.getByLabel("检索主体").fill("春风800MT SPORT");
    await page.getByLabel("镜头关键词").fill("棚拍");
    const queued = page.waitForResponse((r) => r.url().endsWith("/asset-discoveries") && r.request().method() === "POST");
    await page.getByRole("button", { name: "搜索参考素材" }).click();
    const response = await queued;
    expect(response.status()).toBe(202);
    evidence.runId = (await response.json()).id;
  }
  await persist();
  console.log(JSON.stringify({ directory, runId: evidence.runId }));
  await expect.poll(async () => {
    evidence.run = (await (await page.request.get(root + "/asset-discoveries/latest")).json()).run;
    await persist();
    expect(evidence.run.id).toBe(evidence.runId);
    return !["queued", "running"].includes(evidence.run.status);
  }, { timeout: 90_000, intervals: [1000] }).toBe(true);
  expect(evidence.run.status).toBe("ready");
  expect(evidence.run.result.candidates).toHaveLength(4);
  expect(evidence.run.result.candidates.every((c) => c.modelName === "春风 800MT SPORT" && c.sceneMatchStatus === "unverified")).toBe(true);
  await page.reload({ waitUntil: "domcontentloaded" });
  const candidates = page.locator(".reference-candidate");
  await expect(candidates).toHaveCount(4);
  await expect.poll(() => candidates.locator("img").evaluateAll((images) => images.every((img) => img.complete && img.naturalWidth > 0))).toBe(true);
  await candidates.first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(directory, "desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await candidates.first().scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(directory, "mobile.png") });
  const after = await (await page.request.get(root + "/workspace")).json();
  expect(after.assetVersions).toEqual(before.assetVersions);
  expect(await (await page.request.get(endpoint)).json()).toEqual(evidence.storyboardBefore);
  expect(evidence.errors).toEqual([]);
  evidence.verifiedAt = new Date().toISOString();
  await persist();
  console.log(JSON.stringify({ directory, runId: evidence.runId, candidateCount: 4, assetsUnchanged: true }));
} catch (error) {
  evidence.failure = String(error);
  await persist();
  await page.screenshot({ path: path.join(directory, "failure.png"), fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
