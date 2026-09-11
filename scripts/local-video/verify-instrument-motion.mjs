import { chromium, expect as baseExpect } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

// Uses existing engineering references only. Refuse all model-generation requests.
if (process.env.RUN_INSTRUMENT_MOTION !== "1") throw new Error("Set RUN_INSTRUMENT_MOTION=1 for the local FFmpeg comparison.");
const origin = "http://127.0.0.1:3001";
const expect = baseExpect.configure({ timeout: 60_000 });
const report = process.env.INSTRUMENT_MOTION_REPORT
  ? path.resolve(process.env.INSTRUMENT_MOTION_REPORT)
  : path.resolve(`.data/internal-mvp/instrument-motion-${Date.now()}/result.json`);
const directory = path.dirname(report);
await mkdir(directory, { recursive: true });
const evidence = process.env.INSTRUMENT_MOTION_REPORT
  ? JSON.parse(await readFile(report, "utf8"))
  : { projectId: "3c21b6ed-7fbd-4a4e-a38d-4983f26340ff", referenceId: "1a3fd82b-a570-42c7-a70a-525cbee814db",
    scope: "Engineering ES instrument image motion, not riding telemetry or formal vehicle acceptance", errors: [] };
const persist = () => writeFile(report, JSON.stringify(evidence, null, 2));
await persist();
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
page.setDefaultTimeout(60_000);
page.on("pageerror", (error) => evidence.errors.push(error.message));
await page.route("**/api/v1/**", async (route) => {
  const request = route.request();
  if (request.method() === "POST" && /advisor|storyboard-runs|asset-preparations|asset-discoveries|retries|resumption/.test(request.url())) {
    evidence.errors.push(`Unexpected generation request: ${new URL(request.url()).pathname}`);
    return route.abort();
  }
  if (request.method() === "POST" && request.url().endsWith("/generation-runs")) {
    const payload = request.postDataJSON();
    expect(payload.shotId).toBe(evidence.shotId);
    expect(payload.confirmVideoCost).toBe(false);
    const state = await (await page.request.get(`${origin}/api/v1/projects/${evidence.projectId}/storyboards/${evidence.storyboardId}/shots/${evidence.shotId}/preview`)).json();
    expect(state.readiness.mode).not.toMatch(/ai-video/);
  }
  await route.continue();
});
const root = `${origin}/api/v1/projects/${evidence.projectId}`;
try {
  const workspace = await (await page.request.get(`${root}/workspace`)).json();
  evidence.storyboardId ??= workspace.project.currentStoryboardVersionId;
  expect(workspace.project.currentStoryboardVersionId).toBe(evidence.storyboardId);
  evidence.original ??= await (await page.request.get(`${root}/storyboards/${evidence.storyboardId}`)).json();
  expect(evidence.original.shots).toHaveLength(5);
  evidence.shotId ??= evidence.original.shots[2].id;
  await persist();
  await page.goto(`${origin}/projects/${evidence.projectId}/storyboard`, { waitUntil: "domcontentloaded" });
  await page.locator(".shot-item").nth(2).click();
  const preview = page.getByRole("region", { name: "单镜头试片" });
  if (!evidence.runId) {
    // A recorded submission without a response must be reconciled, not repeated.
    if (evidence.submissionStarted) {
      const latest = (await (await page.request.get(`${root}/storyboards/${evidence.storyboardId}/shots/${evidence.shotId}/preview`)).json()).run;
      expect(latest?.mode).not.toMatch(/ai-video/);
      expect(latest?.id).not.toBe(evidence.previousRunId);
      expect(latest?.shotRuns[0]?.strategy).toBe("image-motion");
      evidence.runId = latest.id;
    } else {
      await page.getByRole("combobox", { name: "来源", exact: true }).selectOption("image-motion");
      await page.getByRole("combobox", { name: "镜头素材", exact: true }).selectOption(evidence.crop?.id ?? evidence.referenceId);
      if (!evidence.crop) {
        await page.getByRole("button", { name: "调整参考图" }).click();
        const dialog = page.getByRole("dialog", { name: "参考图构图" });
        await expect(dialog.getByLabel("裁剪尺寸")).toContainText("810 px");
        await dialog.screenshot({ path: path.join(directory, "crop.png") });
        const cropResponse = page.waitForResponse((r) => r.url().endsWith("/crops") && r.request().method() === "POST");
        await dialog.getByRole("button", { name: "保存并应用到当前镜头" }).click();
        const cropped = await cropResponse;
        expect(cropped.status()).toBe(201);
        evidence.crop = await cropped.json();
        await persist();
      }
      const previous = (await (await page.request.get(`${root}/storyboards/${evidence.storyboardId}/shots/${evidence.shotId}/preview`)).json()).run;
      evidence.previousRunId = previous?.id;
      evidence.submissionStarted = new Date().toISOString();
      await persist();
      const submitted = page.waitForResponse((r) => r.url().endsWith("/generation-runs") && r.request().method() === "POST");
      await preview.getByRole("button", { name: "保存并试片" }).click();
      const response = await submitted;
      expect(response.status()).toBe(202);
      evidence.runId = (await response.json()).id;
    }
    await persist();
  }
  console.log(JSON.stringify({ report, runId: evidence.runId }));
  await expect.poll(async () => {
    evidence.run = await (await page.request.get(`${origin}/api/v1/generation-runs/${evidence.runId}`)).json();
    await persist();
    return ["completed", "failed", "cancelled", "interrupted"].includes(evidence.run.status);
  }, { timeout: 180_000, intervals: [1500] }).toBe(true);
  expect(evidence.run.status).toBe("completed");
  expect(evidence.run.scope).toBe("shot-preview");
  expect(evidence.run.shotRuns).toHaveLength(1);
  expect(evidence.run.shotRuns[0].strategy).toBe("image-motion");
  expect(evidence.run.finalArtifactId).toBeNull();
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator(".shot-item").nth(2).click();
  const video = page.getByLabel("镜头试片视频");
  await expect(video).toBeVisible();
  await expect.poll(() => video.evaluate((v) => v.readyState)).toBeGreaterThanOrEqual(2);
  await video.evaluate(async (v) => { v.muted = true; await v.play(); });
  await expect.poll(() => video.evaluate((v) => v.currentTime)).toBeGreaterThan(0.5);
  const frame = async (time) => video.evaluate(async (v, seconds) => {
    v.pause();
    await new Promise((resolve) => { v.addEventListener("seeked", resolve, { once: true }); v.currentTime = seconds; });
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth; canvas.height = v.videoHeight;
    const context = canvas.getContext("2d");
    context.drawImage(v, 0, 0);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let sum = 0, squares = 0;
    for (let i = 0; i < pixels.length; i += 4) { sum += pixels[i]; squares += pixels[i] ** 2; }
    const count = pixels.length / 4;
    return { width: canvas.width, height: canvas.height, variance: squares / count - (sum / count) ** 2, png: canvas.toDataURL("image/png").split(",")[1] };
  }, time);
  evidence.frames = [];
  for (const seconds of [0.05, 1.5, 2.9]) {
    const { png, ...stats } = await frame(seconds);
    expect(stats.width).toBe(540); expect(stats.height).toBe(960); expect(stats.variance).toBeGreaterThan(100);
    const bytes = Buffer.from(png, "base64");
    evidence.frames.push({ seconds, ...stats, sha256: createHash("sha256").update(bytes).digest("hex") });
    await writeFile(path.join(directory, `frame-${seconds}.png`), bytes);
  }
  expect(new Set(evidence.frames.map((f) => f.sha256)).size).toBe(3);
  for (const [name, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844]]) {
    await page.setViewportSize({ width, height });
    await video.scrollIntoViewIfNeeded();
    await preview.evaluate((section) => window.scrollBy(0, section.getBoundingClientRect().top - 30));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.join(directory, `${name}.png`) });
  }
  const downloadEvent = page.waitForEvent("download");
  await preview.getByRole("link", { name: "下载试片" }).click();
  await (await downloadEvent).saveAs(path.join(directory, "preview.mp4"));
  evidence.sha256 = createHash("sha256").update(await readFile(path.join(directory, "preview.mp4"))).digest("hex");
  evidence.after = await (await page.request.get(`${root}/storyboards/${evidence.storyboardId}`)).json();
  evidence.workspace = await (await page.request.get(`${root}/workspace`)).json();
  for (const index of [0, 1, 3, 4]) expect(evidence.after.shots[index]).toEqual(evidence.original.shots[index]);
  expect(evidence.workspace.activeGenerationRunId).toBeNull();
  expect(evidence.workspace.generationReadiness.ready).toBe(false);
  expect(evidence.errors).toEqual([]);
  evidence.verifiedAt = new Date().toISOString();
  delete evidence.failure;
  await persist();
  console.log(JSON.stringify({ report, sha256: evidence.sha256, frames: evidence.frames }));
} catch (error) {
  evidence.failure = String(error);
  await persist();
  await page.screenshot({ path: path.join(directory, "failure.png"), fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
