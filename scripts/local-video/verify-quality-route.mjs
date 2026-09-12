import { chromium, expect as baseExpect } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import path from 'node:path';

if (process.env.RUN_QUALITY_ROUTE !== '1') throw new Error('Set RUN_QUALITY_ROUTE=1: configured GPT, public references, local inference only.');
const origin = 'http://127.0.0.1:3001';
const reuse = process.env.REUSE_QUALITY_SCRIPT === '1';
const directory = path.resolve(`.data/internal-mvp/${reuse ? 'quality-route-reuse' : 'quality-route'}`);
await mkdir(directory, { recursive: true });
let evidence;
try { evidence = JSON.parse(await readFile(path.join(directory, 'result.json'), 'utf8')); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
evidence ??= { scope: 'New feasible mixed-production benchmark; not acceptance of the original exact-360/riding brief.', errors: [] };
const persist = () => writeFile(path.join(directory, 'result.json'), JSON.stringify(evidence, null, 2));
const expect = baseExpect.configure({ timeout: 600_000 });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(30_000);
page.on('pageerror', error => evidence.errors.push(error.message));
page.on('dialog', dialog => dialog.accept());
let providerFailure;
page.on('response', async response => {
  if (response.url().endsWith('/advisor-runs') && response.status() >= 400) {
    providerFailure = await response.text();
    console.log(`Creative advice failed: ${providerFailure}`);
  }
});
const get = async route => {
  const response = await page.request.get(`${origin}/api/v1${route}`);
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
};
const workspace = () => get(`/projects/${evidence.projectId}/workspace`);
const board = () => get(`/projects/${evidence.projectId}/storyboards/${evidence.storyboardId}`);
const waitRun = async id => {
  let run;
  await expect.poll(async () => {
    run = await get(`/generation-runs/${id}`);
    console.log(JSON.stringify({ runId: id, status: run.status, shots: run.shotRuns.map(s => ({ status: s.status, strategy: s.strategy })) }));
    return ['queued', 'running', 'composing'].includes(run.status);
  }, { timeout: 1_500_000, intervals: [5000, 15000, 30000] }).toBe(false);
  expect(run.status, run.errorMessage).toBe('completed');
  return run;
};
try {
  if (reuse && !evidence.projectId) {
    evidence.scope = 'Existing real GPT script and official references reused through the UI; current GPT relay is rate-limited. New local inference and soundtrack composition, not fresh text-to-GPT acceptance.';
    evidence.sourceProjectId = '61854956-1af0-4704-8114-16510f40416b';
    await page.goto(`${origin}/projects/${evidence.sourceProjectId}/storyboard`);
    await page.getByRole('button', { name: '复用脚本与素材' }).click();
    await page.waitForURL(url => url.pathname.endsWith('/storyboard') && !url.pathname.includes(evidence.sourceProjectId));
    evidence.projectId = page.url().split('/').at(-2);
    await persist();
  }
  if (!evidence.projectId) {
    await page.goto(`${origin}/projects/new`);
    evidence.input = '制作一条红色张雪机车 ZXMOTO 820RR 的竖屏外观欣赏短片，只有文字，由平台自动准备同车型官网参考。严格3个镜头，每镜4秒，共12秒。第一镜展示红色整车侧面，第二镜欣赏车头灯具与整流罩细节，这两镜用高清图片轻推近，保留原图结构。第三镜仍为静止的红色整车，用本地视频模型做很轻微的机位横移和光影变化，作为本片唯一的动态图生视频镜头，不要转动车轮、不让车辆驾驶。不做完整360度、不做骑手、不介绍参数、不假装真实测试。希望画面干净，字幕每镜6到10个字，旁白留空，配本地电子节奏音乐。请提供能基于现有官网图片执行的方案，不创造新场景或更换配色。';
    await page.getByLabel('视频想法').fill(evidence.input);
    await page.getByRole('button', { name: '获取创意建议' }).click();
    await page.waitForURL('**/strategy');
    evidence.projectId = page.url().split('/').at(-2);
    await persist();
  }
  let state = await workspace();
  if (!state.project.currentBriefVersionId) {
    await page.goto(`${origin}/projects/${evidence.projectId}/strategy`);
    await expect.poll(async () => {
      if (providerFailure) throw new Error(providerFailure);
      return (await workspace()).latestAdvisorRunId;
    }, { timeout: 180_000, intervals: [2000, 5000] }).toBeTruthy();
    await expect(page.getByRole('button', { name: '采用这个方向' }).first()).toBeVisible();
    await page.screenshot({ path: path.join(directory, 'strategy-desktop.png'), fullPage: true });
    await page.getByRole('button', { name: '采用这个方向' }).first().click();
    await page.waitForURL('**/brief');
  }
  state = await workspace();
  if (!state.project.currentStoryboardVersionId) {
    await page.goto(`${origin}/projects/${evidence.projectId}/brief`);
    const latest = await get(`/projects/${evidence.projectId}/storyboard-runs/latest`);
    if (!['queued', 'running'].includes(latest.run?.status)) {
      if (latest.run?.status === 'failed') throw new Error(`Preparation previously failed: ${latest.run.errorMessage}`);
      await page.getByRole('button', { name: '确认并生成脚本' }).click();
    }
    await expect.poll(async () => {
      const result = await get(`/projects/${evidence.projectId}/storyboard-runs/latest`);
      if (result.run?.status === 'failed') throw new Error(result.run.errorMessage);
      return result.run?.status;
    }, { timeout: 900_000, intervals: [5000, 15000] }).toBe('completed');
    await page.reload();
  }
  state = await workspace();
  evidence.storyboardId = state.project.currentStoryboardVersionId;
  if (reuse && process.env.LOW_MEMORY_QUALITY_PREVIEW === '1' && !evidence.lowMemoryRetried) {
    evidence.rejectedPreviews = [...(evidence.rejectedPreviews ?? []), { id: evidence.previewRunId, reason: 'Full-frame VAE decoding stalled under shared 8GB VRAM pressure. Cancelled and confirmed terminal before switching to tiled decoding.' }];
    delete evidence.previewRunId;
    delete evidence.awaitingVisualReview;
    await page.goto(`${origin}/admin/video-settings`);
    await page.getByLabel('视频解码', { exact: true }).selectOption('tiled');
    await page.getByRole('button', { name: '保存视频配置', exact: true }).click();
    await expect(page.getByText('配置已保存；尚未验证真实推理。', { exact: true })).toBeVisible();
    evidence.lowMemoryRetried = true;
    await persist();
  }
  const correctReference = reuse && process.env.CORRECT_QUALITY_REFERENCE === '1' && !evidence.referenceCorrected;
  if (correctReference) {
    evidence.rejectedPreviews = [...(evidence.rejectedPreviews ?? []), { id: evidence.previewRunId, reason: 'Prompt color contradicted the white official reference; cancelled before adoption.' }];
    delete evidence.previewRunId;
    delete evidence.awaitingVisualReview;
    await persist();
  }
  if (reuse && (!evidence.localRouteEdited || correctReference)) {
    await page.goto(`${origin}/projects/${evidence.projectId}/storyboard`);
    const original = await board();
    evidence.importedGptBoard = original;
    const last = original.shots[2];
    await page.locator('.shot-list .shot-item').nth(2).click();
    await page.getByText('高级设置', { exact: true }).click();
    await page.getByRole('combobox', { name: '来源', exact: true }).selectOption('image-to-video');
    await page.getByRole('combobox', { name: '镜头素材', exact: true }).selectOption(last.sourceAssetId);
    await page.getByLabel('画面描述').fill('静止的白色张雪820RR整车展示，摄影机仅做轻微横向移动，车辆、车轮和车身结构保持不动。');
    await page.getByLabel('视频提示词').fill('A white ZXMOTO 820RR motorcycle standing completely still in a dark studio. Very subtle slow camera slide, gentle reflections across white body panels. Preserve the exact motorcycle shape, wheels, lights, frame and white color of the reference image. Both wheels remain stationary. No rider, no driving, no rotation, no full orbit. Clean cinematic product display, stable subject, restrained movement.');
    await page.getByLabel('时长（秒）').fill('3');
    await page.getByLabel('字幕', { exact: true }).fill('目光停在这一刻');
    await page.getByRole('button', { name: '保存分镜', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: '分镜已保存' })).toBeVisible();
    evidence.localRouteEdited = true;
    evidence.referenceCorrected = true;
    await persist();
  }
  evidence.initialBoard ??= await board();
  evidence.assets = state.assetVersions;
  await persist();
  let current = await board();
  expect(current.shots).toHaveLength(3);
  expect(current.shots.filter(s => s.sourceStrategy === 'image-motion')).toHaveLength(evidence.previewFallback ? 3 : 2);
  await page.goto(`${origin}/projects/${evidence.projectId}/storyboard`);
  await expect(page.getByLabel('整片配乐')).toBeVisible();
  await page.getByLabel('整片配乐').selectOption('local-pulse');
  await page.getByLabel('整片使用中文旁白').uncheck();
  await page.getByRole('button', { name: '保存分镜', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: '分镜已保存' })).toBeVisible();
  current = await board();
  if (reuse && process.env.REJECT_QUALITY_PREVIEW === '1' && !evidence.previewFallback) {
    evidence.rejectedPreviews = [...(evidence.rejectedPreviews ?? []), {
      id: evidence.previewRunId,
      reason: 'Actual contact-sheet review found large blue block-like foreground/background hallucinations. Not adopted; use original-image motion for the feasible benchmark.'
    }];
    await page.locator('.shot-list .shot-item').nth(2).click();
    await page.getByText('高级设置', { exact: true }).click();
    await page.getByLabel('视频提示词').fill('Original white ZXMOTO 820RR reference image with restrained image motion. No synthesized scene, no rider, no driving, no orbit.');
    await page.getByRole('combobox', { name: '来源', exact: true }).selectOption('image-motion');
    await page.getByRole('combobox', { name: '镜头素材', exact: true }).selectOption(evidence.previewRun.shotRuns[0].sourceAssetId);
    await page.getByLabel('画面描述').fill('白色张雪820RR整车侧面，使用官网原图轻微推近，保留车辆结构，不添加骑行或环绕动作。');
    await page.getByRole('button', { name: '保存分镜', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: '分镜已保存' })).toBeVisible();
    evidence.previewFallback = 'image-motion';
    evidence.scope = 'Archived real GPT script and official images, edited through the UI into a feasible 11-second image-motion film with local soundtrack. New local AI preview rejected on visual quality; fresh GPT requests remain blocked by relay 429/502.';
    delete evidence.awaitingVisualReview;
    current = await board();
    await persist();
  }
  if (evidence.previewFallback && !current.shots[2].sourceAssetId) {
    await page.locator('.shot-list .shot-item').nth(2).click();
    await page.getByText('高级设置', { exact: true }).click();
    await page.getByRole('combobox', { name: '镜头素材', exact: true }).selectOption(evidence.previewRun.shotRuns[0].sourceAssetId);
    await page.getByRole('button', { name: '保存分镜', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: '分镜已保存' })).toBeVisible();
    current = await board();
  }
  expect(current.shots.every(s => s.sourceAssetId && !s.productionPlan?.blocker), JSON.stringify(current.shots)).toBe(true);
  for (const shot of current.shots.filter(s => s.sourceStrategy === 'image-to-video')) {
    await page.locator('.shot-list .shot-item').nth(current.shots.findIndex(s => s.id === shot.id)).click();
    const preview = page.getByRole('region', { name: '单镜头试片' });
    if (!evidence.previewRunId) {
      const started = page.waitForResponse(r => r.url().endsWith('/generation-runs') && r.request().method() === 'POST');
      await preview.getByRole('button', { name: '保存并试片' }).click();
      const response = await started;
      expect(response.status(), await response.text()).toBe(202);
      evidence.previewRunId = (await response.json()).id;
      await persist();
    }
    evidence.previewRun = await waitRun(evidence.previewRunId);
    await page.reload();
    await page.locator('.shot-list .shot-item').nth(current.shots.findIndex(s => s.id === shot.id)).click();
    await expect(preview.getByRole('button', { name: '采用到当前镜头' })).toBeVisible();
    await page.screenshot({ path: path.join(directory, 'critical-preview.png'), fullPage: true });
    // The evidence is inspected separately; reruns reuse this same local inference.
    if (process.env.ADOPT_QUALITY_PREVIEW !== '1') {
      evidence.awaitingVisualReview = true;
      await persist();
      console.log(JSON.stringify({ awaitingVisualReview: true, previewRunId: evidence.previewRunId }));
      process.exitCode = 2;
      break;
    }
    await preview.getByRole('button', { name: '采用到当前镜头' }).click();
    await expect.poll(async () => (await board()).shots.find(s => s.id === shot.id).sourceStrategy).toBe('user-video');
    delete evidence.awaitingVisualReview;
    await persist();
  }
  if (!evidence.awaitingVisualReview) {
    const scriptDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: '导出当前脚本' }).click();
    await (await scriptDownload).saveAs(path.join(directory, 'script.md'));
    await writeFile(path.join(directory, 'storyboard.json'), JSON.stringify(await board(), null, 2));
    await page.screenshot({ path: path.join(directory, 'storyboard-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.join(directory, 'storyboard-mobile.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    if (!evidence.generationRunId) {
      if (reuse) {
        await page.getByRole('button', { name: '生成选项', exact: true }).click();
        await page.waitForURL('**/generation');
        const started = page.waitForResponse(r => r.url().endsWith('/generation-runs') && r.request().method() === 'POST');
        await page.getByRole('button', { name: /^(开始生成|按当前分镜生成)$/ }).click();
        const response = await started;
        expect(response.status(), await response.text()).toBe(202);
      } else {
        await page.getByRole('button', { name: '准备并生成视频', exact: true }).click();
        await page.waitForURL('**/generation');
      }
      evidence.generationRunId = (await workspace()).activeGenerationRunId;
      await persist();
    }
    evidence.finalRun = await waitRun(evidence.generationRunId);
    await page.goto(`${origin}/projects/${evidence.projectId}/final`);
    const video = page.getByLabel('生成的视频成片');
    await expect.poll(() => video.evaluate(v => v.readyState)).toBeGreaterThanOrEqual(2);
    evidence.playback = await video.evaluate(async v => {
      v.muted = true;
      await v.play();
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => { v.removeEventListener('timeupdate', check); reject(new Error('Video did not advance during playback')); }, 10_000);
        function check() {
          if (v.currentTime >= .5) { clearTimeout(timer); v.removeEventListener('timeupdate', check); resolve(); }
        }
        v.addEventListener('timeupdate', check);
        check();
      });
      v.pause();
      const canvas = document.createElement('canvas'); canvas.width = 54; canvas.height = 96;
      const ctx = canvas.getContext('2d'); ctx.drawImage(v, 0, 0, 54, 96);
      const pixels = Array.from(ctx.getImageData(0, 0, 54, 96).data).filter((_, i) => i % 4 !== 3);
      const playedSeconds = v.currentTime;
      const sample = async time => {
        await new Promise(resolve => { v.addEventListener('seeked', resolve, { once: true }); v.currentTime = time; });
        ctx.drawImage(v, 0, 0, 54, 96);
        return Array.from(ctx.getImageData(0, 0, 54, 96).data);
      };
      const a = await sample(v.duration - 2.7), b = await sample(v.duration - .3);
      return { width: v.videoWidth, height: v.videoHeight, duration: v.duration, playedSeconds,
        motionPixels: a.filter((n, i) => i % 4 !== 3 && Math.abs(n - b[i]) > 3).length,
        pixelRange: Math.max(...pixels) - Math.min(...pixels) };
    });
    expect(evidence.playback.playedSeconds).toBeGreaterThan(.3);
    expect(evidence.playback.pixelRange).toBeGreaterThan(40);
    expect(evidence.playback.motionPixels).toBeGreaterThan(100);
    const download = page.waitForEvent('download');
    await page.getByRole('link', { name: '下载 MP4' }).click();
    const filename = path.join(directory, 'final.mp4');
    await (await download).saveAs(filename);
    const bytes = await readFile(filename);
    evidence.file = { bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') };
    const pcm = execFileSync('ffmpeg', ['-v', 'error', '-i', filename, '-vn', '-f', 's16le', '-ac', '1', '-ar', '16000', 'pipe:1'], { maxBuffer: 8 * 1024 * 1024 });
    let sum = 0, peak = 0;
    for (let i = 0; i < pcm.length; i += 2) { const sample = pcm.readInt16LE(i); sum += sample * sample; peak = Math.max(peak, Math.abs(sample)); }
    evidence.audio = { rms: Math.sqrt(sum / (pcm.length / 2)), peak };
    expect(evidence.audio.rms).toBeGreaterThan(100);
    expect(evidence.audio.peak).toBeLessThan(32760);
    await page.screenshot({ path: path.join(directory, 'final-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.join(directory, 'final-mobile.png'), fullPage: true });
    evidence.finalBoard = await board(); evidence.verifiedAt = new Date().toISOString();
    delete evidence.failure; await persist();
    console.log(JSON.stringify({ projectId: evidence.projectId, playback: evidence.playback, audio: evidence.audio, file: evidence.file }));
  }
} catch (error) {
  evidence.failure = String(error); await persist();
  await page.screenshot({ path: path.join(directory, 'failure.png'), fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
