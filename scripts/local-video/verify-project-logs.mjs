import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

if (process.env.VERIFY_PROJECT_LOGS !== '1') throw new Error('Set VERIFY_PROJECT_LOGS=1. Optional RETRY_MODEL=1 sends one real creative request.');
const projectId = process.env.PROJECT_ID || 'ab7e2c1a-da94-4519-9e32-6cd3eb05c6d5';
const root = 'http://127.0.0.1:3001';
const directory = path.resolve('.data/internal-mvp/project-management', projectId);
await mkdir(directory, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const evidence = { projectId, errors: [] };
page.on('pageerror', error => evidence.errors.push(error.message));
try {
  if (process.env.RETRY_MODEL === '1') {
    const response = page.waitForResponse(r => r.url().endsWith('/advisor-runs') && r.request().method() === 'POST', { timeout: 180_000 });
    await page.goto(`${root}/projects/${projectId}/strategy`);
    const result = await response;
    evidence.httpStatus = result.status();
    const body = await result.json();
    evidence.error = body.detail;
    console.log(JSON.stringify({ httpStatus: evidence.httpStatus, detail: evidence.error }));
    await page.screenshot({ path: path.join(directory, 'real-model-response.png'), fullPage: true });
  }
  await page.goto(`${root}/projects/${projectId}/logs`);
  await expect(page.locator('.activity-list')).toBeVisible();
  await page.locator('.activity-list li').first().getByText('执行详情', { exact: true }).click();
  await page.screenshot({ path: path.join(directory, 'real-logs-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(directory, 'real-logs-mobile.png'), fullPage: true });
  const response = await page.request.get(`${root}/api/v1/projects/${projectId}/activity?category=model`);
  evidence.activity = await response.json();
  expect(evidence.errors).toEqual([]);
  await writeFile(path.join(directory, 'result.json'), JSON.stringify(evidence, null, 2));
} finally { await browser.close(); }
