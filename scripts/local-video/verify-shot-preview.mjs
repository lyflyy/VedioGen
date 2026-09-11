import { chromium, expect as baseExpect } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

// Opt-in live GPT and local GPU test. Never call this from isolated E2E.
if (process.env.RUN_REAL_SHOT_PREVIEW !== "1") throw new Error("Set RUN_REAL_SHOT_PREVIEW=1 to call configured GPT and local Wan.");
const origin = "http://127.0.0.1:3001";
const expect = baseExpect.configure({ timeout: 120_000 });
const directory = path.resolve(`.data/internal-mvp/shot-preview-live-${Date.now()}`);
await mkdir(directory, { recursive: true });
const evidence = { scope: "Engineering ES variant only, not formal vehicle choice or 80-point acceptance", directory, errors: [] };
const persist = async () => writeFile(path.join(directory, "result.json"), JSON.stringify(evidence, null, 2));
await persist();
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
page.setDefaultTimeout(120_000);
page.on("pageerror", (error) => evidence.errors.push(error.message));
try {
  const settings = await (await page.request.get(`${origin}/api/v1/admin/video-settings`)).json();
  expect(settings.backend).toBe("comfyui");
  expect(settings.enabled).toBe(true);
  if (process.env.SHOT_PREVIEW_PROJECT) {
    evidence.projectId = process.env.SHOT_PREVIEW_PROJECT;
    await persist();
    await page.goto(`${origin}/projects/${evidence.projectId}/strategy`, { waitUntil: "domcontentloaded" });
  } else {
  await page.goto(`${origin}/projects/new`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("视频想法").fill("单镜头试片工程验证，非正式样片。本工程测试仅以春风800MT-ES为参考，不代表项目方已确认正式采用ES版本。制作15秒摩托车短片，保留五个独立分镜，每段3秒：第一段整车真实360度环绕；第二段沙漠骑行尘土飞扬；第三段转速表仪表特写；第四段涉水路面抬头；第五段山林无人机远拉。五段顺序必须保留，不追加CTA，不得删掉困难镜头。目前只有文字，没有用户照片；由平台准备官网仪表参考，先做第三段的试片，其他段缺素材时保持待准备，不能用仪表图替代。请给出叙事建议、简短文案和分镜，旁白每段最多六个汉字。");
  const created = page.waitForResponse((r) => r.url().endsWith("/projects") && r.request().method() === "POST");
  await page.getByRole("button", { name: "获取创意建议" }).click();
  const createResponse = await created;
  expect(createResponse.status()).toBe(201);
  evidence.projectId = (await createResponse.json()).id;
  await persist();
  await page.waitForURL("**/strategy", { waitUntil: "domcontentloaded" });
  }
  const root = `${origin}/api/v1/projects/${evidence.projectId}`;
  const existing = await (await page.request.get(root + "/workspace")).json();
  if (!existing.project.currentStoryboardVersionId) {
    if (existing.project.currentBriefVersionId) {
      await page.goto(`${origin}/projects/${evidence.projectId}/brief`, { waitUntil: "domcontentloaded" });
    } else {
      await page.getByRole("button", { name: "采用这个方向" }).first().click();
    }
    await page.getByRole("button", { name: "确认并生成脚本" }).click();
    await page.waitForURL("**/storyboard", { waitUntil: "domcontentloaded" });
  }
  let workspace = await (await page.request.get(root + "/workspace")).json();
  evidence.storyboardId = workspace.project.currentStoryboardVersionId;
  const original = await (await page.request.get(`${root}/storyboards/${evidence.storyboardId}`)).json();
  evidence.originalStoryboard = original;
  await persist();
  expect(original.shots).toHaveLength(5);
  const visuals = original.shots.map((shot) => `${shot.purpose} ${shot.visual} ${shot.camera}`);
  expect(visuals[0]).toMatch(/360|三百六十/);
  expect(visuals[1]).toMatch(/沙漠|沙地/);
  expect(visuals[2]).toMatch(/仪表|转速/);
  expect(visuals[3]).toMatch(/涉水/);
  expect(visuals[4]).toMatch(/无人机|航拍/);
  await page.goto(`${origin}/projects/${evidence.projectId}/intake`, { waitUntil: "domcontentloaded" });
  workspace = await (await page.request.get(root + "/workspace")).json();
  if (!workspace.assetVersions.some((asset) => asset.referenceSource === "manufacturer")) {
  const previousSearch = (await (await page.request.get(root + "/asset-discoveries/latest")).json()).run;
  let search = previousSearch;
  if (!previousSearch || (["failed", "interrupted", "empty"].includes(previousSearch.status) && process.env.RETRY_REFERENCE_SEARCH === "1")) {
  await page.getByLabel("素材来源").selectOption("manufacturer");
  await page.getByLabel("检索主体").fill("春风800MT-ES");
  await page.getByLabel("镜头关键词").fill("仪表");
  const queuedSearch = page.waitForResponse((r) => r.url().endsWith("/asset-discoveries") && r.request().method() === "POST");
  await page.getByRole("button", { name: "搜索参考素材" }).click();
  const searchResponse = await queuedSearch;
  expect(searchResponse.status()).toBe(202);
  search = await searchResponse.json();
  } else {
    expect(previousSearch.result.subject).toBe("春风800MT-ES");
    expect(previousSearch.result.source).toBe("manufacturer");
    expect(previousSearch.result.searchFocus).toBe("仪表");
  }
  evidence.discoveryId = search.id;
  await persist();
  await expect.poll(async () => {
    search = (await (await page.request.get(root + "/asset-discoveries/latest")).json()).run;
    return search?.id === evidence.discoveryId && !["queued", "running"].includes(search.status);
  }, { timeout: 120_000, intervals: [1500] }).toBe(true);
  evidence.discovery = search;
  await persist();
  expect(search.status, search.errorMessage || JSON.stringify(search)).toBe("ready");
  const adoptReference = page.getByRole("button", { name: "确认主体并采用" });
  await expect(adoptReference).toBeEnabled();
  page.once("dialog", (dialog) => dialog.accept());
  await adoptReference.click();
  await expect(page.getByRole("button", { name: "已采用", exact: true })).toBeVisible();
  }
  workspace = await (await page.request.get(root + "/workspace")).json();
  expect(workspace.assetVersions.filter((asset) => asset.referenceSource === "manufacturer")).toHaveLength(1);
  evidence.reference = workspace.assetVersions.find((asset) => asset.referenceSource === "manufacturer");
  expect(evidence.reference.referenceSource).toBe("manufacturer");
  await persist();
  await page.goto(`${origin}/projects/${evidence.projectId}/storyboard`, { waitUntil: "domcontentloaded" });
  await page.locator(".shot-item").nth(2).click();
  const existingPreview = (await (await page.request.get(`${root}/storyboards/${evidence.storyboardId}/shots/${original.shots[2].id}/preview`)).json()).run;
  const preview = page.getByRole("region", { name: "单镜头试片" });
  if (!existingPreview) {
  await page.getByRole("combobox", { name: "来源", exact: true }).selectOption("image-to-video");
  await page.getByRole("combobox", { name: "镜头素材", exact: true }).selectOption(evidence.reference.id);
  await page.getByLabel("模型片段时长").selectOption("3000");
  await page.getByLabel("视频提示词").fill("A continuous locked close-up of the exact motorcycle dashboard in the reference image. Preserve the rectangular instrument screen, bezel, existing digits, labels, colors and motorcycle structure. Very subtle natural camera vibration from an idling engine, small changing daylight reflections on the glass. No scene change, no new text, no camera orbit, no added controls. Keep the whole instrument screen visible throughout.");
  const submitted = page.waitForResponse((r) => r.url().endsWith("/generation-runs") && r.request().method() === "POST");
  await preview.getByRole("button", { name: "保存并试片" }).click();
  const response = await submitted;
  expect(response.status()).toBe(202);
  evidence.run = await response.json();
  } else {
    evidence.run = existingPreview;
  }
  await persist();
  console.log(JSON.stringify({ report: path.join(directory, "result.json"), projectId: evidence.projectId, runId: evidence.run.id }));
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator(".shot-item").nth(2).click();
  await expect.poll(async () => {
    evidence.run = await (await page.request.get(`${origin}/api/v1/generation-runs/${evidence.run.id}`)).json();
    await persist();
    return ["completed", "failed", "cancelled", "interrupted"].includes(evidence.run.status);
  }, { timeout: 900_000, intervals: [5000] }).toBe(true);
  expect(evidence.run.status, JSON.stringify(evidence.run)).toBe("completed");
  expect(evidence.run.mode).toBe("local-ai-video");
  expect(evidence.run.finalArtifactId).toBeNull();
  expect(evidence.run.shotRuns).toHaveLength(1);
  const clip = page.getByLabel("镜头试片视频");
  await expect(clip).toBeVisible();
  await expect.poll(() => clip.evaluate((v) => v.readyState)).toBeGreaterThanOrEqual(2);
  await clip.evaluate(async (v) => { v.muted = true; await v.play(); });
  await expect.poll(() => clip.evaluate((v) => v.currentTime)).toBeGreaterThan(0.4);
  await preview.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(directory, "preview-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await preview.scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(directory, "preview-mobile.png") });
  const downloadEvent = page.waitForEvent("download");
  await preview.getByRole("link", { name: "下载试片" }).click();
  await (await downloadEvent).saveAs(path.join(directory, "preview.mp4"));
  const bytes = await (await page.request.get(`${origin}/api/v1/artifacts/${evidence.run.shotRuns[0].artifactId}/content`)).body();
  evidence.sha256 = "sha256:" + createHash("sha256").update(bytes).digest("hex");
  // Adoption verifies mechanics only in this explicitly engineering-only project.
  const adoption = page.waitForResponse((r) => r.url().endsWith("/adoption") && r.request().method() === "POST");
  await preview.getByRole("button", { name: "采用到当前镜头" }).click();
  expect((await adoption).status()).toBe(200);
  await expect(page.getByRole("combobox", { name: "来源", exact: true })).toHaveValue("user-video");
  workspace = await (await page.request.get(root + "/workspace")).json();
  evidence.workspace = workspace;
  const after = await (await page.request.get(`${root}/storyboards/${evidence.storyboardId}`)).json();
  evidence.adoptedStoryboard = after;
  expect(workspace.activeGenerationRunId).toBeNull();
  expect(workspace.generationReadiness.ready).toBe(false);
  expect(after.shots).toHaveLength(5);
  for (const index of [0, 1, 3, 4]) {
    expect(after.shots[index].visual).toBe(original.shots[index].visual);
    expect(after.shots[index].sourceAssetId).toBe(original.shots[index].sourceAssetId);
  }
  evidence.errors = [...evidence.errors];
  await persist();
  expect(evidence.errors).toEqual([]);
  console.log(JSON.stringify({ projectId: evidence.projectId, runId: evidence.run.id, sha256: evidence.sha256, directory }));
} catch (error) {
  evidence.failure = String(error);
  await persist();
  await page.screenshot({ path: path.join(directory, "failure.png"), fullPage: true });
  throw error;
} finally { await browser.close(); }
