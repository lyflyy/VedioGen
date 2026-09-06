import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

export async function expectNoSeriousA11yIssues(page: Page) {
  const result = await new AxeBuilder({ page }).analyze();
  const blocking = result.violations.filter((item) => item.impact === "critical" || item.impact === "serious");
  expect(blocking, blocking.map((item) => `${item.id}: ${item.help}`).join("\n")).toEqual([]);
}

export async function expectNoHorizontalOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
}
