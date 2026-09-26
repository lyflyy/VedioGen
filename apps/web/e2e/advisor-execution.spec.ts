import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow, expectNoSeriousA11yIssues } from './helpers';

test('strategy shows live invocation records and retains edits typed during generation', async ({ page }, testInfo) => {
  const project = await (await page.request.post('/api/v1/projects', { data: { title: '执行过程验收', initialMessage: '张雪机车展示，突出外观细节' } })).json();
  let started = false;
  let released = false;
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/projects/${project.id}/advisor-runs`, async route => {
    started = true;
    await gate;
    released = true;
    await route.continue();
  });
  // Isolated slow-provider fixture; the actual result still comes from the test API.
  await page.route(`**/projects/${project.id}/activity?**`, async route => {
    const response = await route.fetch();
    const data = await response.json();
    if (started && !released) data.items = [{ id: 'slow-advisor-fixture', at: new Date(Date.now() - 4000).toISOString(), title: 'creative-advisor', category: 'model', status: 'calling', provider: '隔离测试平台', model: 'slow-test-model', detail: '请求已提交，等待模型响应' }];
    await route.fulfill({ response, json: data });
  });
  try {
    await page.goto(`/projects/${project.id}/strategy`);
    const progress = page.getByRole('region', { name: '创意生成执行过程' });
    await expect(progress.getByRole('heading', { name: '等待模型响应' })).toBeVisible();
    await expect(progress).toContainText('slow-test-model');
    await expect(progress).toContainText('请求已提交，等待模型响应');
    await expect(progress).toContainText('slow-advisor-fixture');
    await expect(progress.getByText(/已等待 \d+ 秒/)).toBeVisible();
    await expect(page.getByText('整理车型事实、视觉机会和制作约束')).toHaveCount(0);
    await page.getByLabel('补充创意要求').fill('下一轮强调红色车身');
    await expect(page.getByRole('button', { name: '发送', exact: true })).toBeDisabled();
    await expectNoSeriousA11yIssues(page);
    await page.screenshot({ path: testInfo.outputPath('strategy-execution-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: testInfo.outputPath('strategy-execution-mobile.png'), fullPage: true });
    release();
    await expect(page.getByRole('button', { name: '采用这个方向' })).toHaveCount(3);
    await expect(progress.getByRole('heading', { name: '创意建议已保存' })).toBeVisible();
    await expect(page.getByLabel('补充创意要求')).toHaveValue('下一轮强调红色车身');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await expect(page.getByLabel('补充创意要求')).toHaveValue('');
    await expect(page.getByText('2 条输入', { exact: true })).toBeVisible();
  } finally { release(); }
});

test('failed strategy shows recorded errors after refresh and feedback retry does not duplicate input', async ({ page }) => {
  const project = await (await page.request.post('/api/v1/projects', { data: { title: '失败调整验收', initialMessage: '车辆展示' } })).json();
  let attempts = 0;
  const detail = '模型平台返回 HTTP 429\n上游返回（已脱敏）：\nAll available accounts are currently rate-limited.\n请求 ID：strategy-error-fixture';
  await page.route(`**/projects/${project.id}/advisor-runs`, async route => {
    attempts += 1;
    await route.fulfill({ status: 429, json: { detail } });
  });
  await page.route(`**/projects/${project.id}/activity?**`, async route => {
    await route.fulfill({ json: { items: attempts ? [{ id: `failure-${attempts}`, at: new Date().toISOString(), title: 'creative-advisor', category: 'model', status: 'failed', model: 'error-test-model', provider: '隔离测试平台', detail, errorCode: 'RATE_LIMITED', requestId: 'strategy-error-fixture', durationMs: 2000 }] : [], total: attempts ? 1 : 0 } });
  });
  await page.goto(`/projects/${project.id}/strategy`);
  await expect(page.getByRole('heading', { name: '创意建议未完成' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: '创意建议未完成' })).toBeVisible();
  expect(attempts).toBe(1);
  const progress = page.getByRole('region', { name: '创意生成执行过程' });
  await expect(progress).toContainText('strategy-error-fixture');
  await page.getByLabel('补充创意要求').fill('改成静态外观细节展示');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await expect(page.getByRole('heading', { name: '创意建议未完成' })).toBeVisible();
  await page.getByRole('button', { name: '重新生成建议', exact: true }).click();
  await expect(page.getByRole('heading', { name: '创意建议未完成' })).toBeVisible();
  expect(attempts).toBe(3);
  const workspace = await (await page.request.get(`/api/v1/projects/${project.id}/workspace`)).json();
  expect(workspace.messages).toHaveLength(2);
});
