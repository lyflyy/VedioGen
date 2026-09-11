import { chromium, expect as baseExpect } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

if (process.env.RUN_TEXT_WORKFLOW !== '1') throw new Error('Set RUN_TEXT_WORKFLOW=1; uses configured GPT and official images, never paid video APIs.');
const origin = 'http://127.0.0.1:3001';
const directory = path.resolve('.data/internal-mvp/text-workflow');
await mkdir(directory, { recursive: true });
let evidence;
try { evidence = JSON.parse(await readFile(path.join(directory, 'result.json'), 'utf8')); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
evidence ??= { scope: 'Separate simple image-motion workflow demonstration, not the formal 360-degree/riding deliverable.', errors: [] };
const persist = () => writeFile(path.join(directory, 'result.json'), JSON.stringify(evidence, null, 2));
const expect = baseExpect.configure({ timeout: 240_000 });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(240_000);
page.on('pageerror', error => evidence.errors.push(error.message));
page.on('dialog', dialog => dialog.accept());
const workspace = async () => (await page.request.get(`${origin}/api/v1/projects/${evidence.projectId}/workspace`)).json();
try {
  if (!evidence.projectId) {
    await page.goto(`${origin}/projects/new`);
    await page.getByLabel('视频想法').fill('制作张雪机车 ZXMOTO 820RR 的简单竖屏展示视频，用于内部测试。只有文字没有上传素材，请平台自动从官网准备同一配色的图片，配色不限。成片12秒，严格3个镜头，每个4秒，只使用 image-motion 图片推近或平移，不需要真360度、不需要骑手、不生成骑行或3D镜头。主题是外观欣赏，不介绍未经验证的参数，不使用其他品牌。字幕简短，旁白留空，无背景音乐。请直接推荐可执行的图片展示方案。');
    await page.getByRole('button', { name: '获取创意建议' }).click();
    await page.waitForURL('**/strategy');
    evidence.projectId = page.url().split('/').at(-2);
    await persist();
  }
  let state = await workspace();
  if (process.env.REFRESH_TEXT_WORKFLOW === '1') {
    if (evidence.projectId !== '61854956-1af0-4704-8114-16510f40416b') throw new Error('Only the isolated verification project can be reset.');
    const url = `${origin}/api/v1/projects/${evidence.projectId}/storyboards/${state.project.currentStoryboardVersionId}`;
    const previous = await (await page.request.get(url)).json();
    expect((await page.request.put(url, { data: { shots: previous.shots.map(s => ({ ...s, sourceAssetId: null })), totalDurationMs: previous.totalDurationMs } })).status()).toBe(200);
    evidence.previousGenerationIds = [...(evidence.previousGenerationIds ?? []), evidence.generationId];
    delete evidence.generationId;
    delete evidence.previewId;
    await persist();
    await page.goto(`${origin}/projects/${evidence.projectId}/storyboard`);
    const prepared = page.waitForResponse(r => r.url().endsWith('/auto-materials') && r.request().method() === 'POST');
    await page.getByRole('button', { name: '自动准备素材' }).click();
    expect((await prepared).status()).toBe(200);
    state = await workspace();
  }
  if (!state.project.currentBriefVersionId) {
    await page.goto(`${origin}/projects/${evidence.projectId}/strategy`);
    await expect(page.getByRole('button', { name: '采用这个方向' }).first()).toBeVisible();
    await page.screenshot({ path: path.join(directory, 'strategy-desktop.png'), fullPage: true });
    await page.getByRole('button', { name: '采用这个方向' }).first().click();
    await page.waitForURL('**/brief');
  }
  state = await workspace();
  if (!state.project.currentStoryboardVersionId) {
    await page.goto(`${origin}/projects/${evidence.projectId}/brief`);
    const latest = await (await page.request.get(`${origin}/api/v1/projects/${evidence.projectId}/storyboard-runs/latest`)).json();
    if (!['queued', 'running'].includes(latest.run?.status)) {
      await page.getByRole('button', { name: '确认并生成脚本' }).click();
    }
    await expect(page.getByRole('region', { name: '脚本生成进度' })).toBeVisible();
    await page.screenshot({ path: path.join(directory, 'script-progress.png'), fullPage: true });
    await page.reload();
    await page.waitForURL('**/storyboard', { timeout: 480_000 });
  }
  state = await workspace();
  if (!state.assetVersions.length && state.project.currentStoryboardVersionId) {
    await page.goto(`${origin}/projects/${evidence.projectId}/storyboard`);
    const prepared = page.waitForResponse(r => r.url().endsWith('/auto-materials') && r.request().method() === 'POST');
    await page.getByRole('button', { name: '自动准备素材' }).click();
    const response = await prepared;
    expect(response.status(), await response.text()).toBe(200);
    state = await workspace();
  }
  evidence.assets = state.assetVersions;
  evidence.storyboardId = state.project.currentStoryboardVersionId;
  const board = await (await page.request.get(`${origin}/api/v1/projects/${evidence.projectId}/storyboards/${evidence.storyboardId}`)).json();
  evidence.storyboard = board;
  evidence.preparation = await (await page.request.get(`${origin}/api/v1/projects/${evidence.projectId}/storyboard-runs/latest`)).json();
  await persist();
  expect(state.assetVersions.length).toBeGreaterThan(0);
  expect(board.shots.every(shot => shot.sourceStrategy === 'image-motion' && shot.sourceAssetId)).toBe(true);
  await page.goto(`${origin}/projects/${evidence.projectId}/storyboard`);
  await expect(page.locator('.vertical-stage img')).toBeVisible();
  await expect.poll(() => page.locator('.vertical-stage img').evaluate(img => img.complete && img.naturalWidth > 0)).toBe(true);
  await page.getByRole('button', { name: '保存分镜', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: '分镜已保存' })).toBeVisible();
  await expect(page).toHaveURL(/\/storyboard$/);
  await page.screenshot({ path: path.join(directory, 'storyboard-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(directory, 'storyboard-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  if (!evidence.previewId) {
    const preview = page.getByRole('region', { name: '单镜头试片' });
    const started = page.waitForResponse(r => r.url().endsWith('/generation-runs') && r.request().method() === 'POST');
    await preview.getByRole('button', { name: '保存并试片' }).click();
    const response = await started;
    expect(response.status()).toBe(202);
    evidence.previewId = (await response.json()).id;
    await persist();
    await expect(preview.getByRole('button', { name: '采用到当前镜头' })).toBeVisible();
    await page.screenshot({ path: path.join(directory, 'shot-preview.png'), fullPage: true });
  }
  if (!evidence.generationId) {
    await page.getByRole('button', { name: '确认分镜', exact: true }).click();
    await page.waitForURL('**/generation');
    await page.getByLabel('输出尺寸').selectOption('standard');
    const started = page.waitForResponse(r => r.url().endsWith('/generation-runs') && r.request().method() === 'POST');
    await page.getByRole('button', { name: /^(开始生成|按当前分镜生成)$/ }).click();
    const response = await started;
    expect(response.status()).toBe(202);
    evidence.generationId = (await response.json()).id;
    await persist();
  } else await page.goto(`${origin}/projects/${evidence.projectId}/generation`);
  await expect(page.getByRole('link', { name: '查看成片' })).toBeVisible({ timeout: 300_000 });
  await page.getByRole('link', { name: '查看成片' }).click();
  const video = page.getByLabel('生成的视频成片');
  await expect.poll(() => video.evaluate(v => v.readyState)).toBeGreaterThanOrEqual(2);
  evidence.video = await video.evaluate(async v => {
    v.muted = true;
    await v.play();
    await new Promise(resolve => setTimeout(resolve, 700));
    v.pause();
    const canvas = document.createElement('canvas');
    canvas.width = 54; canvas.height = 96;
    const context = canvas.getContext('2d');
    const sample = async time => {
      await new Promise(resolve => { v.addEventListener('seeked', resolve, { once: true }); v.currentTime = time; });
      context.drawImage(v, 0, 0, 54, 96);
      return Array.from(context.getImageData(0, 0, 54, 96).data);
    };
    const playbackTime = v.currentTime;
    const a = await sample(0.2), b = await sample(2.5);
    return { width: v.videoWidth, height: v.videoHeight, duration: v.duration, playbackTime,
      range: Math.max(...a) - Math.min(...a), changed: a.filter((n, i) => i % 4 !== 3 && Math.abs(n - b[i]) > 3).length };
  });
  expect(evidence.video.playbackTime).toBeGreaterThan(0.3);
  expect(evidence.video.changed).toBeGreaterThan(100);
  evidence.run = await (await page.request.get(`${origin}/api/v1/generation-runs/${evidence.generationId}`)).json();
  evidence.downloadUrl = origin + await page.getByRole('link', { name: '下载 MP4' }).getAttribute('href');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('link', { name: '下载 MP4' }).click();
  await (await downloadEvent).saveAs(path.join(directory, 'zxmoto-820rr-simple.mp4'));
  await page.screenshot({ path: path.join(directory, 'final-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(directory, 'final-mobile.png'), fullPage: true });
  evidence.verifiedAt = new Date().toISOString();
  delete evidence.failure;
  await persist();
  console.log(JSON.stringify({ projectId: evidence.projectId, video: evidence.video, downloadUrl: evidence.downloadUrl, errors: evidence.errors }));
} catch (error) {
  evidence.failure = String(error);
  await persist();
  await page.screenshot({ path: path.join(directory, 'failure.png'), fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
