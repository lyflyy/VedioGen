import { chromium, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

if (!process.argv[2]) throw new Error("Pass the completed benchmark report.json path.");
const reportPath = path.resolve(process.argv[2]);
const report = JSON.parse(await readFile(reportPath, "utf8"));
if (report.status !== "completed") throw new Error("Benchmark has not completed.");
const content = await readFile(report.video.uri);
const sha256 = `sha256:${createHash("sha256").update(content).digest("hex")}`;
expect(sha256).toBe(report.video.sha256);
const browser = await chromium.launch({ channel: "msedge", headless: true });
const results = [];
try {
  for (const [name, width, height] of [["desktop", 1440, 900], ["mobile", 390, 844]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setContent(`<style>body{margin:0;background:#161616}video{display:block;width:100%;height:100dvh;object-fit:contain}</style><video controls muted playsinline src="data:video/mp4;base64,${content.toString("base64")}"></video>`);
    const video = page.locator("video");
    await expect.poll(() => video.evaluate((v) => v.readyState)).toBeGreaterThanOrEqual(2);
    const metadata = await video.evaluate((v) => ({ width: v.videoWidth, height: v.videoHeight, duration: v.duration }));
    expect(metadata.width).toBe(report.video.width);
    expect(metadata.height).toBe(report.video.height);
    expect(Math.abs(metadata.duration * 1000 - report.video.durationMs)).toBeLessThan(100);
    const sample = async (fraction) => video.evaluate(async (v, fraction) => {
      v.pause();
      await new Promise((resolve) => {
        v.addEventListener("seeked", resolve, { once: true });
        v.currentTime = v.duration * fraction;
      });
      const canvas = document.createElement("canvas");
      canvas.width = 54; canvas.height = 96;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(v, 0, 0, 54, 96);
      return Array.from(ctx.getImageData(0, 0, 54, 96).data);
    }, fraction);
    const first = await sample(0.05);
    const last = await sample(0.9);
    const difference = first.reduce((sum, value, index) => sum + Math.abs(value - last[index]), 0) / first.length;
    expect(new Set(first).size).toBeGreaterThan(50);
    await video.evaluate(async (v) => { v.currentTime = 0; await v.play(); });
    await expect.poll(() => video.evaluate((v) => v.currentTime)).toBeGreaterThan(0.3);
    expect(await video.evaluate((v) => v.error)).toBeNull();
    await sample(0.9);
    await video.evaluate((v) => { v.controls = false; });
    await page.screenshot({ path: path.join(path.dirname(reportPath), `browser-${name}.png`) });
    await video.evaluate((v) => { v.controls = true; });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    results.push({ viewport: name, ...metadata, distinctChannels: new Set(first).size, meanPixelDifference: difference, errors });
    await page.close();
  }
} finally {
  await browser.close();
}
const evidence = { scope: "Standalone real-clip playback only; not platform E2E or identity/motion acceptance.", jobId: report.jobId, sha256, results };
await writeFile(path.join(path.dirname(reportPath), "browser-verification.json"), JSON.stringify(evidence, null, 2));
console.log(JSON.stringify(evidence, null, 2));
