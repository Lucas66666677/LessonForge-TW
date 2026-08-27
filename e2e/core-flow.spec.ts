import { expect, test } from "@playwright/test";
import path from "node:path";

test("Mock Provider 完成班級、教材、生成、鎖定、核准與分版匯出", async ({
  page,
}, testInfo) => {
  const unique = Date.now().toString().slice(-8);
  const className = `E2E 國三驗收班 ${unique}`;
  const fixture = path.resolve("fixtures/demo_material.md");

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登入工作台" })).toBeVisible();
  await page.getByLabel("Email").fill("owner@demo.lessonforge.tw");
  await page.getByLabel("密碼").fill("e2e-owner-password-only");
  await page.getByRole("button", { name: "進入 LessonForge" }).click();
  await expect(
    page.getByRole("heading", { name: "今天要準備哪一堂課？" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "班級", exact: true }).click();
  await page.getByRole("button", { name: "建立班級" }).click();
  await page.getByLabel("班級名稱").fill(className);
  await page.getByLabel("已學內容").fill("基礎五大句型與過去式");
  await page.getByLabel("常見錯誤").fill("單字拼寫\n閱讀細節定位");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "建立班級" })
    .click();
  await expect(page.getByRole("heading", { name: className })).toBeVisible();

  await page.getByRole("link", { name: "教材庫" }).click();
  await page.getByRole("button", { name: "上傳教材" }).click();
  await page.locator('input[type="file"]').setInputFiles(fixture);
  await page.getByLabel("章節").fill("E2E Evidence");
  await page.getByLabel("主題").fill("Claim and Evidence");
  await page.getByLabel("標籤").fill("e2e,reading,evidence");
  await page.getByRole("button", { name: "上傳並解析" }).click();
  await expect(page.getByRole("status")).toContainText("教材已完成解析");
  await expect(
    page.getByRole("link", { name: /demo_material\.md/ }),
  ).toBeVisible();

  await page.getByRole("link", { name: "產生教材" }).click();
  await page.getByLabel("班級").selectOption({ label: `${className} · 國三` });
  await page.getByLabel("選擇教材 demo_material.md").check();
  await page.getByRole("button", { name: /下一步/ }).click();
  await page
    .getByLabel("本次學習目標")
    .fill("辨認主張與證據\n運用上下文判斷詞義");
  await page.getByRole("button", { name: /下一步/ }).click();
  await page.getByRole("button", { name: /下一步/ }).click();
  await page.getByRole("button", { name: "開始產生教材" }).click();
  await expect(page.getByRole("heading", { name: "教材包已產生" })).toBeVisible(
    {
      timeout: 30_000,
    },
  );
  await page.getByRole("button", { name: /開啟教材編輯器/ }).click();

  const blocks = page.locator("article.editor-block");
  await expect(blocks).toHaveCount(8);
  const first = blocks.nth(0);
  const second = blocks.nth(1);
  const firstContent = first.getByLabel("學生內容");
  const original = await firstContent.inputValue();
  const edited = `${original}\nE2E 老師人工修訂。`;
  await firstContent.fill(edited);
  await first.getByRole("button", { name: "儲存區塊" }).click();
  await expect(page.getByRole("status")).toContainText("變更已儲存");
  await first.getByRole("button", { name: "鎖定區塊" }).click();
  await expect(first.getByRole("button", { name: "解鎖區塊" })).toBeVisible();
  await second.getByRole("button", { name: "單獨重生" }).click();
  await expect(second.getByLabel("學生內容")).toHaveValue(
    /已依班級弱點重新整理/,
  );
  await expect(firstContent).toHaveValue(edited);
  await expect(first.getByRole("button", { name: "單獨重生" })).toBeDisabled();

  await page.getByRole("button", { name: "核准教材" }).click();
  await expect(page.getByRole("button", { name: "已核准" })).toBeVisible();
  await page.getByRole("button", { name: "預覽" }).click();
  await expect(page.getByRole("heading", { name: "教材預覽" })).toBeVisible();

  const studentFrame = page.frameLocator('iframe[title="學生版預覽"]');
  await expect(studentFrame.locator("body")).not.toContainText("答案：");
  const studentDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "下載此版本" }).click();
  const student = await studentDownload;
  expect(student.suggestedFilename()).toBe("lessonforge-student.pdf");
  await student.saveAs(testInfo.outputPath("lessonforge-student.pdf"));

  await page.getByRole("tab", { name: "教師版" }).click();
  const teacherFrame = page.frameLocator('iframe[title="教師版預覽"]');
  await expect(teacherFrame.locator("body")).toContainText("答案：");
  await expect(teacherFrame.locator("body")).toContainText("解析：");
  const teacherDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "下載此版本" }).click();
  const teacher = await teacherDownload;
  expect(teacher.suggestedFilename()).toBe("lessonforge-teacher.pdf");
  await teacher.saveAs(testInfo.outputPath("lessonforge-teacher.pdf"));
});
