import { expect, test } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';
import crypto from 'node:crypto';
import { expectNoHorizontalOverflow, expectNoSeriousA11yIssues } from './helpers';

test('horizontal advice, persisted preparation progress, upload binding, save and missing-material guard', async ({ page }, testInfo) => {
  test.setTimeout(150_000);
  await page.goto('/projects/new');
  await page.getByLabel('视频想法').fill(`流程回归 ${Date.now()}：张雪820RR，简单图片展示。`);
  await page.getByRole('button', { name: '获取创意建议' }).click();
  await expect(page.getByRole('button', { name: '采用这个方向' })).toHaveCount(3);
  const projectId = page.url().split('/').at(-2);
  const cards = page.locator('.proposal-card');
  const boxes = await cards.evaluateAll(nodes => nodes.map(node => ({ x: node.getBoundingClientRect().x, y: node.getBoundingClientRect().y })));
  expect(new Set(boxes.map(box => Math.round(box.y))).size).toBe(1);
  expect(boxes[1].x).toBeGreaterThan(boxes[0].x);
  await expectNoHorizontalOverflow(page);
  await expectNoSeriousA11yIssues(page);
  await page.screenshot({ path: testInfo.outputPath('strategy-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  const comparison = page.getByRole('region', { name: '叙事方向比较' });
  expect(await comparison.evaluate(node => node.scrollWidth > node.clientWidth)).toBe(true);
  await comparison.focus();
  await page.keyboard.press('ArrowRight');
  await page.screenshot({ path: testInfo.outputPath('strategy-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('button', { name: '采用这个方向' }).first().click();
  let holdProgress = true;
  await page.route('**/storyboard-runs/latest', async route => {
    const response = await route.fetch();
    const data = await response.json();
    if (holdProgress && data.run) data.run = { ...data.run, status: 'running', phase: 'writing-script', storyboardVersionId: null };
    await route.fulfill({ response, json: data });
  });
  await page.getByRole('button', { name: '确认并生成脚本' }).click();
  const progress = page.getByRole('region', { name: '脚本生成进度' });
  await expect(progress).toBeVisible();
  await page.reload();
  await expect(progress).toBeVisible();
  await expect(progress.getByRole('status')).toHaveText('大模型正在生成脚本');
  holdProgress = false;
  await page.waitForURL('**/storyboard');
  await expect(page.getByRole('button', { name: '生成选项', exact: true })).toBeVisible();
  await page.unroute('**/storyboard-runs/latest');
  await page.getByRole('button', { name: '生成选项', exact: true }).click();
  await expect(page.getByRole('region', { name: '素材准备结果' })).toContainText('个镜头待处理');
  await expect(page).toHaveURL(/\/storyboard$/);
  const file = path.resolve(__dirname, '../public/images/motorcycle-studio.jpg');
  await page.locator('.media-upload input[type=file]').setInputFiles(file);
  await expect(page.getByRole('status').filter({ hasText: '素材已上传并绑定当前镜头' })).toBeVisible();
  await page.getByText('高级设置', { exact: true }).click();
  const selected = page.getByRole('combobox', { name: '镜头素材', exact: true });
  const id = await selected.inputValue();
  expect(id).toBeTruthy();
  const source = page.getByRole('combobox', { name: '来源', exact: true });
  const originalStrategy = await source.inputValue();
  await source.selectOption('image-to-video');
  await expect(selected).toHaveValue(id);
  await source.selectOption('image-motion');
  await expect(selected).toHaveValue(id);
  await source.selectOption(originalStrategy);
  await expect.poll(() => page.locator('.vertical-stage img').evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await expect(page.getByText('有未保存修改', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: '保存分镜', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: '分镜已保存' })).toBeVisible();
  await expect(page).toHaveURL(/\/storyboard$/);
  await page.reload();
  await page.getByText('高级设置', { exact: true }).click();
  await expect(selected).toHaveValue(id);
  await page.getByRole('button', { name: '自动准备素材' }).click();
  await expect(page.getByRole('region', { name: '素材准备结果' })).toContainText('素材已就绪');
  const state = await (await page.request.get(`/api/v1/projects/${projectId}/workspace`)).json();
  expect(state.generationReadiness.ready).toBe(true);
  await page.getByRole('button', { name: '准备并生成视频', exact: true }).click();
  await page.waitForURL('**/generation');
  await expect(page.getByRole('link', { name: '查看成片' })).toBeVisible({ timeout: 90_000 });
});

test('workspace read failure has an explicit recovery action', async ({ page }) => {
  const created = await page.request.post('/api/v1/projects', { data: { title: '恢复工作区测试', initialMessage: '车型展示' } });
  const project = await created.json();
  await page.route('**/workspace', route => route.fulfill({ status: 503, json: { detail: '暂时不可用' } }));
  await page.goto(`/projects/${project.id}/storyboard`);
  await expect(page.getByRole('alert').filter({ hasText: '工作区加载失败' })).toBeVisible();
  await page.unroute('**/workspace');
  await page.getByRole('button', { name: '重新载入', exact: true }).click();
  await expect(page.getByText('还没有可编辑的 Storyboard', { exact: true })).toBeVisible();
});

test('single-shot preparation shows progress and failed tasks survive refresh without a result version', async ({ page }, testInfo) => {
  const prefix = '/api/v1/projects';
  const project = await (await page.request.post(prefix, { data: { title: '素材任务可见性', initialMessage: '张雪820RR，简单图片展示' } })).json();
  const root = `${prefix}/${project.id}`;
  const advisor = await (await page.request.post(`${root}/advisor-runs`)).json();
  const brief = await (await page.request.post(`${root}/creative-briefs`, { data: {
    advisorRunId: advisor.id, proposalKey: advisor.result.proposals[0].proposalKey, overrides: {},
  } })).json();
  await page.request.post(`${root}/creative-briefs/${brief.id}/approval`, { data: {} });
  const generated = await (await page.request.post(`${root}/storyboard-runs`)).json();
  const board = await (await page.request.get(`${root}/storyboards/${generated.storyboardVersionId}`)).json();
  const target = board.shots[1].id;
  const createdAt = new Date().toISOString();
  let submitted = false;
  let failed = false;
  const run = () => ({ id: 'test-material-run', storyboardVersionId: board.id, inputVersion: board.rowVersion,
    shotId: target, status: failed ? 'failed' : 'running', phase: failed ? 'failed' : 'searching-web', createdAt,
    completedAt: failed ? new Date().toISOString() : undefined,
    errorMessage: failed ? '平台：测试 GPT · 模型：测试模型，HTTP 429，请稍后重试' : null,
    checks: [], changes: [], events: [{ phase: 'searching-web', at: createdAt, message: '官网无可用结果，正在检索网络参考图' }],
  });
  await page.route('**/material-runs/latest', route => route.fulfill({ json: { run: submitted ? run() : null } }));
  await page.route('**/material-runs?*', route => {
    expect(new URL(route.request().url()).searchParams.get('shot_id')).toBe(target);
    expect(route.request().method()).toBe('POST');
    submitted = true;
    return route.fulfill({ status: 202, json: run() });
  });
  await page.goto(`/projects/${project.id}/storyboard`);
  await page.locator('.shot-item').nth(1).click();
  await page.getByRole('button', { name: '准备当前镜头素材', exact: true }).click();
  const report = page.getByRole('region', { name: '素材准备结果' });
  await expect(report).toContainText('正在检索网络参考图');
  await expect(report).toContainText('镜头 2');
  await expect(report).toContainText('已等待');
  await expect(page.getByRole('button', { name: '自动准备素材', exact: true })).toBeDisabled();
  await page.reload();
  await expect(report).toContainText('正在检索网络参考图');
  failed = true;
  await expect(report).toContainText('素材准备失败');
  await expect(report.getByRole('alert')).toContainText('HTTP 429');
  await expect(page.getByRole('button', { name: '自动准备素材', exact: true })).toBeEnabled();
  await page.reload();
  await expect(report.getByRole('alert')).toContainText('HTTP 429');
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('material-failure-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('material-failure-mobile.png'), fullPage: true });
});

test('reference display confirmation produces a separate playable film without overwriting the original', async ({ page }, testInfo) => {
  const project = await (await page.request.post('/api/v1/projects', { data: { title: '独立展示版验收', initialMessage: '张雪820RR，车辆展示' } })).json();
  const root = `/api/v1/projects/${project.id}`;
  const advisor = await (await page.request.post(`${root}/advisor-runs`)).json();
  const brief = await (await page.request.post(`${root}/creative-briefs`, { data: { advisorRunId: advisor.id, proposalKey: advisor.result.proposals[0].proposalKey, overrides: {} } })).json();
  await page.request.post(`${root}/creative-briefs/${brief.id}/approval`, { data: {} });
  const script = await (await page.request.post(`${root}/storyboard-runs`)).json();
  const content = fs.readFileSync(path.resolve(__dirname, '../public/images/motorcycle-studio.jpg'));
  const intent = await (await page.request.post('/api/v1/assets/upload-intents', { data: {
    projectId: project.id, fileName: 'reference.jpg', mimeType: 'image/jpeg', sizeBytes: content.length,
    sha256: 'sha256:' + crypto.createHash('sha256').update(content).digest('hex'),
  } })).json();
  await page.request.put(intent.uploadUrl, { data: content });
  await page.goto(`/projects/${project.id}/storyboard`);
  await page.getByRole('button', { name: '生成选项', exact: true }).click();
  await page.getByRole('button', { name: '制作参考图展示版', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '参考图展示版', exact: true });
  await expect(dialog).toContainText('原脚本保留');
  await expect(dialog).toContainText('不包含原脚本的人物动作');
  const before = await (await page.request.get(`${root}/storyboards/${script.storyboardVersionId}`)).json();
  await page.screenshot({ path: testInfo.outputPath('reference-cut-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('reference-cut-mobile.png'), fullPage: true });
  await dialog.getByRole('button', { name: '确认并制作展示版', exact: true }).click();
  await page.waitForURL('**/generation');
  expect(page.url()).not.toContain(project.id);
  await page.getByRole('link', { name: '查看成片' }).click({ timeout: 60_000 });
  const video = page.locator('video').first();
  await expect(video).toBeVisible();
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState >= 2 && v.videoWidth > 0)).toBe(true);
  const after = await (await page.request.get(`${root}/storyboards/${script.storyboardVersionId}`)).json();
  expect(after).toEqual(before);
});
