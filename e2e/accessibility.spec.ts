import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function expectNoSeriousViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = results.violations.filter(
    (violation) =>
      violation.impact === "serious" || violation.impact === "critical",
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
}

test("登入與工作台符合關鍵 WCAG 規則並可用鍵盤跳到主內容", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登入工作台" })).toBeVisible();
  await expectNoSeriousViolations(page);

  await page.getByRole("button", { name: "進入 LessonForge" }).click();
  await expect(
    page.getByRole("heading", { name: "今天要準備哪一堂課？" }),
  ).toBeVisible();
  await expectNoSeriousViolations(page);

  await page.reload();
  await expect(
    page.getByRole("heading", { name: "今天要準備哪一堂課？" }),
  ).toBeVisible();
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "跳到主要內容" });
  await expect(skipLink).toBeFocused();
  await skipLink.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
});
