# LessonForge TW 產品規格

## 產品目標

LessonForge TW 是台灣中小型國高中英文補習班的本機優先 AI 教材生產系統。它會讀取機構自有教材與班級脈絡，產生可編輯、可核准、可列印的學生版、教師版、作業、週考與家長回報。預設 Demo 與 CI 使用 `MockLLMProvider`，不需要任何付費 API；正式本機生成預設使用 Ollama `qwen3:8b`。

## 使用者與範圍

- 語言：繁體中文（zh-TW）。
- 使用者：補習班 owner、admin、teacher。
- 科目：英文；國一至高三；個別家教與小班。
- 輸入：PDF、DOCX、TXT、Markdown，單檔預設 20 MB。
- 輸出：網頁預覽、A4 PDF、DOCX。
- 預設課程：120 分鐘；作業每週 4 天、每天約 30 分鐘。

## 核心流程

1. 使用本機 Demo 帳號登入，建立組織與具角色的成員。
2. 建立班級、匿名學生與七類弱點資訊。
3. 上傳並解析教材；保留檔案、頁碼／段落、章節、標籤與難度 metadata。
4. 以生成精靈設定日期、時間、目標、難度、題型、作業、週考與家長回報。
5. 背景管線依序執行 normalization、retrieval、planning、block/homework/quiz/report generation、validation、persist。
6. 在結構化區塊編輯器修改、排序、鎖定、複製、刪除、單區塊重生、版本還原與核准。
7. 預覽並輸出學生版、教師版、作業版、週考版、家長回報的 PDF／DOCX。

## 安全與品質要求

- 所有租戶資料在資料模型與 service 層帶入 `organization_id`；猜測 UUID 不得跨租戶存取。
- Argon2 密碼雜湊、JWT、基本 rate limiting、MIME 與內容檢查、安全 UUID 檔名。
- AI 輸出一律通過 Pydantic v2 schema 與 deterministic validators，有限次 repair，且預設為草稿。
- raw prompt、教材全文、密碼、JWT、API key 與學生資訊不得寫入一般 log。
- 所有輸出內容做 HTML escaping；fatal issue 阻止核准。
- prompt 模板獨立版本控制；generation run 保存 provider、model、prompt version、設定、狀態、耗時、錯誤、token usage 與驗證摘要。

## 必要驗證器

時間誤差不超過 5 分鐘；客觀題有答案；選擇題至少三個互異選項且答案存在；單選僅一個答案；克漏字答案非空；題目不可高度重複；閱讀題連結文章／來源；學生版不洩漏答案；教師版有答案與解析；區塊分鐘數為正；來源屬於同租戶；鎖定區塊不可被重生修改；fatal issue 阻止核准。

## 非目標

OCR、線上學生作答、金流、排課、點名、家長／學生 App、即時多人協作、全科目、全國課綱資料庫、LINE 自動發送、手寫批改、大型 ERP、fine-tuning、未授權出版社教材皆不屬 MVP。

## 完成與驗收

- Fresh clone 可依 README 啟動；Mock Provider 能完成端到端 Demo。
- Demo 帳號登入、班級 CRUD、教材上傳解析、生成、區塊編輯／鎖定／重生、版本、核准與輸出皆可實際操作。
- 學生 PDF 不含答案；教師 PDF 含答案與解析；DOCX 可開啟。
- 跨租戶、locked block、檔案、provider、schema repair、validation、export separation、背景失敗與重試測試通過。
- 前端表單、wizard、editor、loading/error、權限差異測試通過。
- 20+ synthetic eval、lint、typecheck、unit/integration、production build 與核心 E2E 通過。
- 完整 README、架構、API、部署、安全、Ollama、troubleshooting、Demo 與最終測試報告。
