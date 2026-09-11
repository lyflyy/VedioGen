import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers';

test('429 ends advice loading without an automatic retry loop', async ({ page }, testInfo) => {
  let requests = 0;
  await page.route('**/projects/*/advisor-runs', route => {
    requests++;
    return route.fulfill({ status: 429, headers: { 'Retry-After': '60' }, json: {
      detail: '模型凭据仍在 HTTP 429 冷却期，未发送请求；请在 60 秒后手动重试',
    } });
  });
  await page.goto('/projects/new');
  await page.getByLabel('视频想法').fill('春风450MT，沙漠中的冒险短片');
  await page.getByRole('button', { name: '获取创意建议' }).click();
  await expect(page.getByText('创意建议未完成', { exact: true })).toBeVisible();
  await expect(page.locator('.workspace-error')).toContainText('429 冷却期');
  await expect(page.getByText('正在形成创意判断', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '重新载入', exact: true }).click();
  await expect(page.getByRole('button', { name: '重新生成建议', exact: true })).toBeEnabled();
  expect(requests).toBe(1);
  await page.screenshot({ path: testInfo.outputPath('rate-limited-strategy.png'), fullPage: true });
});

test('admin shows quota pause and explicitly restores scheduling without a model probe', async ({ page }, testInfo) => {
  let paused = true;
  let resets = 0;
  await page.route('**/admin/model-credentials', async route => {
    const response = await route.fetch();
    const data = await response.json();
    data.items = data.items.slice(0, 1).map((item: object) => ({ ...item, cooldown: paused ? {
      errorCode: 'QUOTA_EXCEEDED', retryAfterSeconds: null,
      message: '模型凭据因 HTTP 429 额度不足已暂停，未发送请求；请检查中转站额度',
    } : null }));
    await route.fulfill({ response, json: data });
  });
  await page.route('**/cooldown-reset', route => {
    paused = false;
    resets++;
    return route.fulfill({ json: { status: 'cleared' } });
  });
  await page.goto('/admin/credentials');
  await expect(page.getByRole('button', { name: '恢复调度' })).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: 'HTTP 429' })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('quota-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath('quota-mobile.png'), fullPage: true });
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: '恢复调度' }).click();
  await expect(page.getByRole('button', { name: '连通性测试' })).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: 'HTTP 429' })).toHaveCount(0);
  expect(resets).toBe(1);
});
