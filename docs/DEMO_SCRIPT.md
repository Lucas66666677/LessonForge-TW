# 本機 Demo 腳本

預估 10–15 分鐘。使用 Owner 帳號與 Mock Provider，可離線重現；教材 fixture 是 repository 自製內容。

## 事前準備

1. 依 README 完成 install、migration、seed，啟動 API 與 web。
2. 確認 `/health` 為 200，設定頁顯示 Mock Provider。
3. 準備 `fixtures/demo_material.md`。
4. 使用 `.env` 中自行設定的 `DEMO_OWNER_EMAIL`／`DEMO_OWNER_PASSWORD` 登入。

## 走查

1. 儀表板：說明班級、教材、教材包與 fatal issue 摘要；指出最近教材包與下一堂課建議。
2. 班級：建立「Demo 國三驗收班」，填入已學內容、常見錯誤、教學偏好與作業設定；新增「學生 A／B」代號與不同弱點，不輸入真實姓名。
3. 教材庫：上傳 `fixtures/demo_material.md`，填章節 `E2E Evidence`、主題 `Claim and Evidence`、標籤；展示解析狀態與 chunks/來源定位。
4. 產生教材：選剛建立的班級與教材，目標填「辨認主張與證據」「運用上下文判斷詞義」，保留 120 分鐘與完整 modules，開始生成。
5. 進度：展示 queued/running/completed 與每階段訊息；Mock 通常數秒完成。
6. 編輯器：修改第一區塊學生內容並儲存，鎖定它；對第二區塊按「單獨重生」，確認第二區塊更新、第一區塊人工文字完全不變，且鎖定區塊的重生按鈕停用。
7. 版本：展示版本紀錄；說明每個 mutation 都有 snapshot 與 audit。若示範還原，確認會再建立新版本。
8. 核准：確認沒有 fatal issue，按「核准教材」。Teacher 帳號只能送審，Owner/Admin 才能核准。
9. 預覽：學生版搜尋不到「答案：」「解析：」「教師備註」；教師版可看到這些內容與來源。
10. 匯出：各下載學生、教師 PDF；再到匯出中心展示作業、週考、家長報告與 DOCX 選項。
11. 組織與成員：切換 Teacher Demo 帳號，展示教師看得到成員但沒有建立帳號／核准權限。
12. Tenant 隔離：說明 `scripts/demo_check.py` 會建立第二組織並以 foreign UUID 驗證 404，UI 不依賴隱藏按鈕作為安全邊界。

## 自動驗收

API 在 8000 埠時：

```powershell
.\.venv\Scripts\python.exe scripts/demo_check.py
```

腳本會建立唯一組織、成員、班級、匿名學生、教材與 package，驗證跨 tenant 404、鎖定 exact preservation、409、核准、四個 PDF/DOCX 下載，以及學生／教師內容分離；成功時輸出 `DEMO_CHECK=PASS`。

真正瀏覽器流程：

```powershell
npm run e2e
```

成功條件為核心流程與 axe/鍵盤測試全部通過。測試使用 `artifacts/e2e-*.db` 與獨立 upload/export 目錄，不污染 Demo DB。
