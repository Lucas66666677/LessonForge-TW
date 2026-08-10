# 架構決策紀錄

## ADR-001：模組化 monorepo，而非微服務群

前端位於 repository 根層的 Vinext/Vite React surface；Python API 與 worker 位於 `services/`，共享 Pydantic domain schemas。部署時有 web/api/worker 三個程序，但商業邏輯集中在單一 Python package，降低小團隊維護成本。

## ADR-002：PostgreSQL 正式、SQLite 本機 fallback

正式與 Docker Compose 使用 PostgreSQL + pgvector；測試與無 Docker Demo 可使用 SQLite。Repository/service 層只使用 SQLAlchemy 2 async API。向量能力不可用時退回 tenant-filtered SQL/文字檢索，產品仍可操作且 UI 顯示 fallback。

## ADR-003：Redis queue 與 in-process fallback

正式拓樸以 Redis 支援 worker 工作；本機 Mock Demo 可啟用明確標示的 in-process runner，避免把外部基礎設施變成 Demo 的硬依賴。兩種執行路徑共用同一個 tenant-scoped generation pipeline。

## ADR-004：Schema single source of truth

Pydantic models 與 FastAPI OpenAPI 是 API contract 的唯一來源；TypeScript client/type 由 OpenAPI 生成。禁止長期手動維護兩套 domain schema。

## ADR-005：結構化教材編輯器

教材以 typed block/question 結構編輯，不導入通用 WYSIWYG。每次 mutation 建立 immutable version snapshot；鎖定欄位由 service 層強制保留。

## ADR-006：檔案與內容安全

上傳內容以 UUID 命名、以 signature/MIME 雙重驗證、尺寸限制、tenant directory 隔離。輸出模板只插入 escaped text。掃描 PDF 回報 OCR 不支援，不嘗試偷偷 OCR。

## ADR-007：本機優先 LLM

Provider 介面支援 mock、Ollama、OpenAI-compatible、Gemini。預設正式 provider 是 Ollama `qwen3:8b`；Demo/CI 預設 mock。所有 provider 回傳皆先經 Pydantic 驗證與有限 repair。
