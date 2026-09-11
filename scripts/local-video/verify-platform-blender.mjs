import { chromium, expect as baseExpect } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

if (process.env.RUN_PLATFORM_BLENDER !== "1") throw new Error("Set RUN_PLATFORM_BLENDER=1 for real GPT and local Blender engineering verification.");
const origin = "http://127.0.0.1:3001";
const reportPath = process.env.PLATFORM_BLENDER_REPORT ? path.resolve(process.env.PLATFORM_BLENDER_REPORT)
  : path.resolve(`.data/internal-mvp/platform-blender-${Date.now()}/result.json`);
const directory = path.dirname(reportPath);
await mkdir(directory, { recursive: true });
const evidence = process.env.PLATFORM_BLENDER_REPORT ? JSON.parse(await readFile(reportPath, "utf8"))
  : { scope: "Real platform execution using non-vehicle calibration GLB. Not a motorcycle sample or 80-point acceptance.", errors: [] };
const persist = () => writeFile(reportPath, JSON.stringify(evidence, null, 2));
await persist();
console.log(JSON.stringify({ reportPath }));
const expect = baseExpect.configure({ timeout: 120_000 });
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
page.setDefaultTimeout(120_000);
page.on("pageerror", (error) => evidence.errors.push(error.message));
await page.route("**/api/v1/generation-runs", async (route) => {
  const request = route.request();
  const body = request.postDataJSON();
  expect(body.confirmVideoCost ?? false).toBe(false);
  const storyboard = await (await page.request.get(`${origin}/api/v1/projects/${evidence.projectId}/storyboards/${body.storyboardVersionId}`)).json();
  expect(storyboard.shots.every((shot) => ["blender-3d", "user-video"].includes(shot.sourceStrategy))).toBe(true);
  await route.continue();
});
try {
  await page.goto(`${origin}/admin/video-settings`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Blender 可执行文件", { exact: true }).fill("D:/VedioGen-local/Blender/blender-4.5.13-windows-x64/blender.exe");
  await page.getByLabel("Blender 超时（秒）").fill("1800");
  await page.getByLabel("启用 Blender 环绕").check();
  await page.getByRole("button", { name: "保存视频配置" }).click();
  await expect(page.getByRole("status").filter({ hasText: "配置已保存" })).toBeVisible();
  await page.getByRole("button", { name: "检查已保存的 Blender", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Blender 4.5.13" })).toBeVisible();
  await page.screenshot({ path: path.join(directory, "admin.png"), fullPage: true });
  if (!evidence.projectId) {
    await page.goto(`${origin}/projects/new`, { waitUntil: "domcontentloaded" });
    await page.getByLabel("视频想法").fill("Blender平台工程校准验证，不是任何车型样片，不做车型宣传。本次唯一主体是已有 GLB 中的三个红绿蓝校准方块。只要一个分镜，时长3秒，摄影机完整360度环绕静止方块，纯竖屏，字幕为‘工程校准’，不加旁白，不加CTA，不添加车辆或骑手。请提供简短创意建议，然后生成且只生成这个单镜头。已有GLB会由平台工程人员导入，不能说已取得真实摩托车模型。");
    await expect(page.getByRole("button", { name: "获取创意建议" })).toBeEnabled({ timeout: 15_000 });
    await page.screenshot({ path: path.join(directory, "intake.png") });
    const created = page.waitForResponse((r) => r.url().endsWith("/projects") && r.request().method() === "POST");
    await page.getByRole("button", { name: "获取创意建议" }).click();
    const response = await created;
    expect(response.status()).toBe(201);
    evidence.projectId = (await response.json()).id;
    await persist();
    await page.waitForURL("**/strategy", { waitUntil: "domcontentloaded" });
  }
  const root = `${origin}/api/v1/projects/${evidence.projectId}`;
  let workspace = await (await page.request.get(root + "/workspace")).json();
  if (!workspace.project.currentStoryboardVersionId) {
    if (!workspace.project.currentBriefVersionId) {
      if (!page.url().endsWith(`/projects/${evidence.projectId}/strategy`)) {
        await page.goto(`${origin}/projects/${evidence.projectId}/strategy`, { waitUntil: "domcontentloaded" });
      }
      await page.getByRole("button", { name: "采用这个方向" }).first().click();
    } else {
      await page.goto(`${origin}/projects/${evidence.projectId}/brief`, { waitUntil: "domcontentloaded" });
    }
    await page.getByRole("button", { name: "确认并生成脚本" }).click();
    await page.waitForURL("**/storyboard", { waitUntil: "domcontentloaded" });
  }
  workspace = await (await page.request.get(root + "/workspace")).json();
  evidence.storyboardId = workspace.project.currentStoryboardVersionId;
  if (evidence.original?.id !== evidence.storyboardId) {
    if (evidence.original) evidence.previousStoryboards = [...(evidence.previousStoryboards ?? []), evidence.original];
    evidence.original = await (await page.request.get(`${root}/storyboards/${evidence.storyboardId}`)).json();
    await persist();
  }
  expect(evidence.original.shots).toHaveLength(1);
  evidence.shotId = evidence.original.shots[0].id;
  await persist();
  await page.goto(`${origin}/projects/${evidence.projectId}/storyboard`, { waitUntil: "domcontentloaded" });
  if (!workspace.assetVersions.some((asset) => asset.kind === "model")) {
    const uploaded = page.waitForResponse((r) => r.url().includes("/assets/uploads/") && r.request().method() === "PUT");
    await page.locator(".media-upload input[type=file]").setInputFiles(path.resolve(".data/internal-mvp/blender-calibration.glb"));
    expect((await uploaded).status()).toBe(201);
  }
  workspace = await (await page.request.get(root + "/workspace")).json();
  evidence.model = workspace.assetVersions.find((asset) => asset.kind === "model");
  const preview = page.getByRole("region", { name: "单镜头试片" });
  const current = (await (await page.request.get(`${root}/storyboards/${evidence.storyboardId}/shots/${evidence.shotId}/preview`)).json()).run;
  if (!current) {
    await page.getByLabel("时长（毫秒）").fill("3000");
    await page.getByRole("combobox", { name: "来源", exact: true }).selectOption("blender-3d");
    await page.getByLabel("渲染模板").selectOption("orbit-360");
    await page.getByLabel("镜头素材", { exact: true }).selectOption(evidence.model.id);
    const started = page.waitForResponse((r) => r.url().endsWith("/generation-runs") && r.request().method() === "POST");
    await preview.getByRole("button", { name: "保存并试片" }).click();
    const response = await started;
    expect(response.status()).toBe(202);
    evidence.previewRunId = (await response.json()).id;
  } else {
    evidence.previewRunId = current.id;
  }
  await persist();
  console.log(JSON.stringify({ projectId: evidence.projectId, previewRunId: evidence.previewRunId }));
  await expect.poll(async () => {
    evidence.preview = await (await page.request.get(`${origin}/api/v1/generation-runs/${evidence.previewRunId}`)).json();
    await persist();
    return !["queued", "running", "composing"].includes(evidence.preview.status);
  }, { timeout: 600_000, intervals: [2000] }).toBe(true);
  expect(evidence.preview.status, JSON.stringify(evidence.preview)).toBe("completed");
  expect(evidence.preview.mode).toBe("local-blender");
  expect(evidence.preview.finalArtifactId).toBeNull();
  expect(evidence.preview.shotRuns.at(-1).renderedFrames).toBe(90);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(preview.getByRole("button", { name: "采用到当前镜头" })).toBeVisible();
  const video = page.getByLabel("镜头试片视频");
  await expect.poll(() => video.evaluate((v) => v.readyState)).toBeGreaterThanOrEqual(2);
  const samples = [];
  for (const seconds of [0.05, 1.5, 2.95]) {
    const sample = await video.evaluate(async (v, seconds) => {
      v.pause();
      await new Promise((resolve) => { v.addEventListener("seeked", resolve, { once: true }); v.currentTime = seconds; });
      const canvas = document.createElement("canvas"); canvas.width = v.videoWidth; canvas.height = v.videoHeight;
      const context = canvas.getContext("2d"); context.drawImage(v, 0, 0);
      return { png: canvas.toDataURL().split(",")[1], pixels: Array.from(context.getImageData(0, 0, canvas.width, canvas.height).data) };
    }, seconds);
    await writeFile(path.join(directory, `frame-${seconds}.png`), Buffer.from(sample.png, "base64"));
    expect(new Set(sample.pixels).size).toBeGreaterThan(100);
    samples.push(sample.pixels);
  }
  evidence.halfOrbitPixelDifference = samples[0].reduce((sum, value, i) => sum + Math.abs(value - samples[1][i]), 0) / samples[0].length;
  expect(evidence.halfOrbitPixelDifference).toBeGreaterThan(4);
  for (const [name, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844]]) {
    await page.setViewportSize({ width, height });
    await video.evaluate(async (v) => { v.currentTime = 0; v.muted = true; await v.play(); });
    await expect.poll(() => video.evaluate((v) => v.currentTime)).toBeGreaterThan(0.4);
    await video.evaluate((v) => v.pause());
    await preview.scrollIntoViewIfNeeded();
    await preview.evaluate((section) => window.scrollBy(0, section.getBoundingClientRect().top - 30));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.join(directory, `preview-${name}.png`) });
  }
  workspace = await (await page.request.get(root + "/workspace")).json();
  if (workspace.activeGenerationRunId) evidence.fullRunId = workspace.activeGenerationRunId;
  else {
    const adopted = page.waitForResponse((r) => r.url().endsWith("/adoption") && r.request().method() === "POST");
    await preview.getByRole("button", { name: "采用到当前镜头" }).click();
    expect((await adopted).status()).toBe(200);
    await page.getByRole("button", { name: "确认分镜", exact: true }).click();
    await page.waitForURL("**/generation", { waitUntil: "domcontentloaded" });
    const started = page.waitForResponse((r) => r.url().endsWith("/generation-runs") && r.request().method() === "POST");
    await page.getByRole("button", { name: "开始生成", exact: true }).click();
    const response = await started;
    expect(response.status()).toBe(202);
    evidence.fullRunId = (await response.json()).id;
  }
  await persist();
  await expect.poll(async () => {
    evidence.fullRun = await (await page.request.get(`${origin}/api/v1/generation-runs/${evidence.fullRunId}`)).json();
    return !["queued", "running", "composing"].includes(evidence.fullRun.status);
  }, { timeout: 180_000, intervals: [1000] }).toBe(true);
  expect(evidence.fullRun.status).toBe("completed");
  await persist();
  await page.goto(`${origin}/projects/${evidence.projectId}/final`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("link", { name: "下载 MP4" })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载 MP4" }).click();
  await (await download).saveAs(path.join(directory, "final.mp4"));
  const finalVideo = page.locator("video").first();
  await expect.poll(() => finalVideo.evaluate((v) => v.readyState)).toBeGreaterThanOrEqual(2);
  await finalVideo.evaluate(async (v) => { v.muted = true; await v.play(); });
  await expect.poll(() => finalVideo.evaluate((v) => v.currentTime)).toBeGreaterThan(0.4);
  await page.screenshot({ path: path.join(directory, "final-mobile.png") });
  evidence.sha256 = createHash("sha256").update(await readFile(path.join(directory, "final.mp4"))).digest("hex");
  expect(evidence.errors).toEqual([]);
  evidence.verifiedAt = new Date().toISOString();
  delete evidence.failure;
  await persist();
  console.log(JSON.stringify({ reportPath, projectId: evidence.projectId, finalArtifactId: evidence.fullRun.finalArtifactId, sha256: evidence.sha256 }));
} catch (error) {
  evidence.failure = String(error);
  await persist();
  await page.screenshot({ path: path.join(directory, "failure.png"), fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
