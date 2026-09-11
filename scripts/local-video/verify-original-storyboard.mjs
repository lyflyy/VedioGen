import { chromium, expect as baseExpect } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';

if (process.env.RUN_ORIGINAL_WORKFLOW !== '1') throw new Error('Explicit opt-in required for real local inference.');
const origin = 'http://127.0.0.1:3001';
const projectId = '323873ba-8568-474e-b956-ada42cc7263c';
const directory = path.resolve('.data/internal-mvp/original-storyboard-verification');
await mkdir(directory, { recursive: true });
const resultPath = path.join(directory, 'result.json');
let evidence;
try { evidence = JSON.parse(await readFile(resultPath, 'utf8')); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
evidence ??= { projectId, startedAt: new Date().toISOString(), errors: [] };
const persist = () => writeFile(resultPath, JSON.stringify(evidence, null, 2));
const expect = baseExpect.configure({ timeout: 60_000 });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.on('pageerror', error => evidence.errors.push(error.message));
const get = async url => {
  const response = await page.request.get(`${origin}/api/v1${url}`);
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
};
try {
  const config = await get('/admin/video-settings');
  expect(config.backend).toBe('comfyui');
  expect(config.enabled && config.localCallsAllowed).toBe(true);
  const workspace = await get(`/projects/${projectId}/workspace`);
  const boardId = workspace.project.currentStoryboardVersionId;
  const board = await get(`/projects/${projectId}/storyboards/${boardId}`);
  if (!evidence.originalStoryboard) {
    evidence.originalStoryboard = board;
    evidence.originalAssets = workspace.assetVersions;
    await persist();
  }
  await page.goto(`${origin}/projects/${projectId}/storyboard`);
  await expect(page.getByRole('button', { name: '准备并生成视频', exact: true })).toBeVisible();
  await expect(page.locator('.vertical-stage img')).toBeVisible();
  await page.screenshot({ path: path.join(directory, 'storyboard-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(directory, 'storyboard-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  if (!evidence.materialRunId) {
    const responsePromise = page.waitForResponse(r => r.url().includes('/material-runs?generate=true') && r.request().method() === 'POST');
    await page.getByRole('button', { name: '准备并生成视频', exact: true }).click();
    const response = await responsePromise;
    expect(response.status(), await response.text()).toBe(202);
    evidence.materialRunId = (await response.json()).id;
    await persist();
  }
  for (let i = 0; i < 300; i++) {
    const { run } = await get(`/projects/${projectId}/material-runs/latest`);
    expect(run.id).toBe(evidence.materialRunId);
    evidence.materialRun = run;
    await persist();
    if (!['queued', 'running'].includes(run.status)) {
      expect(run.status, JSON.stringify(run)).toBe('completed');
      expect(run.generationRunId).toBeTruthy();
      evidence.generationId = run.generationRunId;
      await persist();
      break;
    }
    await page.waitForTimeout(2000);
  }
  expect(evidence.generationId).toBeTruthy();
  const prepared = await get(`/projects/${projectId}/storyboards/${boardId}`);
  expect(prepared.shots.map(s => s.durationMs)).toEqual(evidence.originalStoryboard.shots.map(s => s.durationMs));
  expect(prepared.shots.map(s => s.visual)).toEqual(evidence.originalStoryboard.shots.map(s => s.visual));
  expect(prepared.shots.every(s => s.sourceStrategy === 'image-to-video')).toBe(true);
  evidence.preparedStoryboard = prepared;
  await page.goto(`${origin}/projects/${projectId}/generation`);
  await page.screenshot({ path: path.join(directory, 'generation-started.png'), fullPage: true });
  let previous = '';
  for (let i = 0; i < 1080; i++) {
    const run = await get(`/generation-runs/${evidence.generationId}`);
    evidence.generation = run;
    await persist();
    const state = `${run.status}: ${run.shotRuns.map(s => `${s.status}/${s.providerStatus ?? ''}`).join(', ')}`;
    if (state !== previous) { console.log(state); previous = state; }
    if (!['queued', 'running', 'composing'].includes(run.status)) {
      expect(run.status, JSON.stringify(run)).toBe('completed');
      break;
    }
    await page.waitForTimeout(5000);
  }
  expect(evidence.generation.finalArtifactId).toBeTruthy();
  if (process.env.REFRAME_ORIGINAL_WORKFLOW === '1') {
    evidence.originalGenerationId ??= evidence.generationId;
    if (!evidence.recompositionId) {
      await page.goto(`${origin}/projects/${projectId}/generation`);
      const responsePromise = page.waitForResponse(r => r.url().endsWith('/recomposition') && r.request().method() === 'POST');
      await page.getByRole('button', { name: '优化画幅并合成', exact: true }).click();
      const response = await responsePromise;
      expect(response.status(), await response.text()).toBe(202);
      evidence.recompositionId = (await response.json()).id;
      await persist();
    }
    evidence.generationId = evidence.recompositionId;
    for (let i = 0; i < 180; i++) {
      evidence.generation = await get(`/generation-runs/${evidence.generationId}`);
      await persist();
      if (!['queued', 'running', 'composing'].includes(evidence.generation.status)) break;
      await page.waitForTimeout(2000);
    }
    expect(evidence.generation.status, JSON.stringify(evidence.generation)).toBe('completed');
  }
  const artifact = await get(`/artifacts/${evidence.generation.finalArtifactId}`);
  evidence.artifact = artifact;
  await page.goto(`${origin}/projects/${projectId}/final`);
  const video = page.getByLabel('生成的视频成片');
  await expect.poll(() => video.evaluate(v => v.readyState)).toBeGreaterThanOrEqual(2);
  evidence.playback = await video.evaluate(async v => {
    v.muted = true;
    await v.play();
    await new Promise(resolve => setTimeout(resolve, 800));
    v.pause();
    const c = document.createElement('canvas'); c.width = 108; c.height = 192;
    const ctx = c.getContext('2d');
    const samples = [];
    let previousPixels;
    for (const time of [0.3, 1.5, 3.3, 5.1, 7.0, 8.6, 10.3]) {
      await new Promise(resolve => { v.addEventListener('seeked', resolve, { once: true }); v.currentTime = time; });
      ctx.drawImage(v, 0, 0, c.width, c.height);
      const pixels = ctx.getImageData(0, 0, c.width, c.height).data;
      let sum = 0, squares = 0;
      for (let i = 0; i < pixels.length; i += 4) { sum += pixels[i]; squares += pixels[i] ** 2; }
      const n = pixels.length / 4;
      const changed = previousPixels ? pixels.filter((v, i) => i % 4 !== 3 && Math.abs(v - previousPixels[i]) > 5).length : 0;
      samples.push({ time, variance: squares / n - (sum / n) ** 2, changed });
      previousPixels = new Uint8ClampedArray(pixels);
    }
    return { width: v.videoWidth, height: v.videoHeight, duration: v.duration, samples };
  });
  expect(evidence.playback.duration).toBeCloseTo(11, 0);
  expect(evidence.playback.samples.every(s => s.variance > 20)).toBe(true);
  expect(evidence.playback.samples.at(-1).changed).toBeGreaterThan(100);
  await page.screenshot({ path: path.join(directory, 'final-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(directory, 'final-mobile.png'), fullPage: true });
  const download = await page.request.get(`${origin}/api/v1/artifacts/${artifact.id}/content`);
  expect(download.status()).toBe(200);
  const bytes = await download.body();
  evidence.download = { bytes: bytes.length, sha256: 'sha256:' + createHash('sha256').update(bytes).digest('hex') };
  await writeFile(path.join(directory, 'final.mp4'), bytes);
  expect(evidence.errors).toEqual([]);
  evidence.completedAt = new Date().toISOString();
  await persist();
  console.log(JSON.stringify({ artifactId: artifact.id, playback: evidence.playback, download: evidence.download }));
} finally { await persist(); await browser.close(); }
