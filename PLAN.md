# LessonForge TW 實作計畫

| 里程碑 | 狀態 | 交付內容 | 驗證 |
|---|---|---|---|
| M0 基礎 | 完成 | 規格文件、monorepo 骨架、Compose、CI、可啟動 web/api | `npm run lint`, API health smoke |
| M1 身分與資料 | 完成 | schema、migration、seed、JWT、角色、組織、班級、學生、tenant scope | auth/role/CRUD/tenant pytest |
| M2 教材 | 完成 | 上傳驗證、解析、chunk、metadata、全文／向量 fallback、教材 UI | file/parser/retrieval pytest |
| M3 AI | 完成 | provider abstraction、schema、prompt、背景 pipeline、progress、validators | provider/repair/pipeline pytest |
| M4 產品操作 | 完成 | wizard、editor、lock/regenerate、version、approval、previews | Vitest + API integration |
| M5 匯出 | 完成 | 學生／教師／作業／週考／家長 PDF 與 DOCX、中文字型 | export separation + render smoke |
| M6 品質 | 完成 | 20+ eval、Playwright E2E、安全、a11y、桌面／平板視覺 QA | `make test e2e eval demo-check` |
| M7 交付 | 完成 | README、架構、API、部署、troubleshooting、Demo script、最終報告 | clean bootstrap rehearsal |

## 依賴關係

資料模型與 tenant scope 是所有 API 的前置；教材解析是 retrieval 的前置；schema/provider/validator 是 generator 的前置；核准與匯出依賴版本與 validation。每個里程碑失敗先修復，不帶著核心紅燈前進。

## 本機無 Docker 驗證策略

本機開發與 CI 可用 SQLite、檔案儲存及 in-process queue fallback 執行全部 Mock 流程；Docker Compose 使用 PostgreSQL + pgvector、Redis 與獨立 worker 驗證正式拓樸。此環境目前未安裝 Docker，因此 Compose 的實際啟動會在 `STATUS.md` 明確標為未執行，不會誤報。
