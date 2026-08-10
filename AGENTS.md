# Repository 指引

## 結構

- `app/`：繁中 React 產品 UI（Vinext + Vite）。
- `services/api/lessonforge/`：FastAPI、domain/service、資料存取與匯出。
- `services/worker/`：背景 worker entrypoint。
- `prompts/`：版本化 prompt templates。
- `templates/`：PDF/DOCX 模板與字型說明。
- `fixtures/`：合法自製教材與 Demo fixtures。
- `evals/`：synthetic eval cases 與報告。
- `scripts/`：bootstrap、seed、demo-check 與跨平台輔助。
- `infra/`：容器設定；根目錄 `docker-compose.yml` 為本機完整拓樸。
- `artifacts/`：可再生輸出與視覺 QA 截圖，不提交個資。

## 開發規範

- UI 與錯誤訊息使用繁體中文；TypeScript strict；Python type annotated。
- 所有 tenant-owned 查詢必須顯式帶入 `organization_id`，不得先用裸 UUID 查詢後再檢查。
- API request/response 用 Pydantic；AI 與上傳內容都視為不可信輸入。
- 不記錄秘密、token、raw 教材／prompt 或學生資料。
- 新增 endpoint 後更新／產生 OpenAPI TypeScript contract。
- 使用 `apply_patch` 修改文字檔；保留使用者無關變更。

## 驗證指令

- `npm run lint`、`npm run typecheck`、`npm run test:unit`、`npm run build`
- `python -m ruff check services`、`python -m mypy services/api/lessonforge`
- `python -m pytest`
- `npm run e2e`
- `python evals/run_eval.py`
- `python scripts/demo_check.py`

## 完成定義

變更必須有適當測試；核心流程需實際操作；lint/typecheck/test/build 不留紅燈；沒有會阻止使用者的假按鈕或 TODO；`STATUS.md` 記錄真實執行結果與環境限制。
