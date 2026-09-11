import { chromium, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const directory = path.resolve(process.argv[2] || ".data/internal-mvp/blender-glb-orbit");
const content = await readFile(path.join(directory, "orbit.mp4"));
const browser = await chromium.launch({ channel: "msedge", headless: true });
const results = [];
try {
  for (const [name, width, height] of [["desktop", 1440, 900], ["mobile", 390, 844]]) {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.setContent(`<style>body{margin:0;background:#161616}video{display:block;width:100%;height:100dvh;object-fit:contain}</style><video controls muted playsinline src="data:video/mp4;base64,${content.toString("base64")}"></video>`);
    const video = page.locator("video");
    await expect.poll(() => video.evaluate((v) => v.readyState)).toBeGreaterThanOrEqual(2);
    const frame = async (time) => video.evaluate(async (v, time) => {
      v.pause();
      await new Promise((resolve) => { v.addEventListener("seeked", resolve, { once: true }); v.currentTime = time; });
      const canvas = document.createElement("canvas");
      canvas.width = 54; canvas.height = 96;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(v, 0, 0, 54, 96);
      return Array.from(ctx.getImageData(0, 0, 54, 96).data);
    }, time);
    const first = await frame(0.1);
    const opposite = await frame(1.1);
    const difference = first.reduce((sum, value, i) => sum + Math.abs(value - opposite[i]), 0) / first.length;
    expect(new Set(first).size).toBeGreaterThan(50);
    expect(difference).toBeGreaterThan(4);
    await video.evaluate(async (v) => { v.currentTime = 0; await v.play(); });
    await expect.poll(() => video.evaluate((v) => v.currentTime)).toBeGreaterThan(0.4);
    await video.evaluate((v) => v.pause());
    await page.screenshot({ path: path.join(directory, `browser-${name}.png`) });
    const metadata = await video.evaluate((v) => ({ width: v.videoWidth, height: v.videoHeight, duration: v.duration }));
    expect(metadata).toEqual({ width: 540, height: 960, duration: 2 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    results.push({ viewport: name, ...metadata, distinctChannels: new Set(first).size, meanPixelDifference: difference });
    await page.close();
  }
} finally {
  await browser.close();
}
const evidence = { scope: "diagnostic geometry only; not a motorcycle sample", sha256: createHash("sha256").update(content).digest("hex"), results };
await writeFile(path.join(directory, "browser-verification.json"), JSON.stringify(evidence, null, 2));
console.log(JSON.stringify(evidence, null, 2));
