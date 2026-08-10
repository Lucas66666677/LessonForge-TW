# LessonForge TW

給台灣補習班使用的本機優先 AI 英文教材工作台。老師可以把自有 PDF、DOCX、TXT 或 Markdown 教材與班級脈絡組合成可編輯的完整課程，鎖定人工修訂、逐區塊重生、核准版本，最後匯出學生版、教師版、作業、週考與家長報告 PDF／DOCX。

介面、錯誤訊息與 Demo 資料皆為繁體中文；Demo 與 CI 預設使用 deterministic Mock Provider，不需要 API key，也不會把教材送到外部服務。

## 已實作能力

- Owner／Admin／Teacher JWT 登入、組織成員管理與 tenant-scoped 查詢。
- 班級、匿名學生代號、學習弱點、偏好、作業設定與備註。
- PDF／DOCX／TXT／MD 上傳，副檔名、MIME、檔案 signature、大小、SHA-256 與安全檔名檢查；掃描 PDF 明確回報需要 OCR。
- 教材切塊、metadata、PostgreSQL full-text／pgvector 路徑，以及 SQLite 文字 fallback。
- Mock、Ollama、OpenAI-compatible、Gemini Provider；分階段課程規劃、區塊、作業、週考與家長報告生成。
- 背景任務、進度、失敗原因、重試、Pydantic schema repair 與內容驗證器。
- 結構化區塊編輯器、移動、複製、刪除、鎖定、局部重生、不可變版本、還原、送審與核准。
- 學生／教師 HTML 預覽，五種用途的 PDF 與 DOCX；學生版不含答案、解析或教師備註。
- 24 組 synthetic eval、Vitest、pytest、axe、Playwright 完整流程與分離 CI。

## 技術架構

- Web：React 19、TypeScript strict、Vinext/Vite、React Router、TanStack Query、Radix UI。
- API：FastAPI、Pydantic 2、SQLAlchemy 2 async、Alembic、Argon2、JWT。
- 正式資料層：PostgreSQL 17 + pgvector、Redis 8、獨立 worker。
- 本機 fallback：SQLite、檔案儲存、in-process jobs、Mock Provider。
- 匯出：Jinja2 HTML + Playwright PDF、python-docx DOCX。

細節見 [架構文件](docs/ARCHITECTURE.md) 與 [API 摘要](docs/API.md)。

## 最快本機 Demo（Windows、無 Docker）

需求：Node.js 22.13+、npm 10+、Python 3.11+、Git。PowerShell 於 repository 根目錄執行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools==83.0.0
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm ci
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m alembic -c services/api/alembic.ini upgrade head
.\.venv\Scripts\python.exe scripts/seed.py
```

開兩個 PowerShell 視窗。

視窗 A：

```powershell
.\.venv\Scripts\python.exe -m uvicorn lessonforge.main:app --host 127.0.0.1 --port 8000
```

視窗 B：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

開啟 [http://localhost:3000/login](http://localhost:3000/login)。API 健康檢查與 OpenAPI 分別位於 [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) 與 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。

Demo 帳號：

- Owner：`owner@demo.lessonforge.tw`／`LessonForgeDemo!2026`
- Teacher：`teacher@demo.lessonforge.tw`／`LessonForgeDemo!2026`

完整走查順序在 [Demo 腳本](docs/DEMO_SCRIPT.md)。

## Docker Compose

已安裝 Docker Desktop 的環境可使用正式拓樸：

```bash
cp .env.example .env
docker compose up --build
docker compose exec api python scripts/seed.py
```

Compose 會啟動 web、API、worker、PostgreSQL/pgvector 與 Redis。`api` 與 `worker` 會覆寫 `.env` 中的 SQLite／Redis localhost 設定。停止：

```bash
docker compose down
```

本 repository 的建置環境沒有 Docker，因此 Compose 設定已靜態檢查，但未在此機器宣稱實際啟動通過；無 Docker 的完整 Mock 流程已實際驗證。

## 切換 Ollama

1. 安裝並啟動 [Ollama](https://github.com/ollama/ollama)。
2. 下載模型：

```powershell
ollama pull qwen3:8b
ollama pull nomic-embed-text
ollama serve
```

3. 在 `.env` 設定：

```dotenv
LLM_PROVIDER=ollama
LLM_MODEL=qwen3:8b
LLM_BASE_URL=http://localhost:11434
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
```

4. 重啟 API，先跑代表性 live eval：

```powershell
$env:LLM_PROVIDER="ollama"
.\.venv\Scripts\python.exe evals/run_eval.py --live --limit 4
```

實際模型輸出仍必須經 schema、時間、題目、答案、引用與鎖定區塊驗證；不要因為模型在本機就跳過教師核准。

## 驗證指令

```powershell
npm run lint
npm run typecheck
npm run test:unit
npm run build
.\.venv\Scripts\python.exe -m ruff check services scripts evals
.\.venv\Scripts\python.exe -m mypy services/api/lessonforge
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe evals/run_eval.py
npm run e2e
```

API 已在 8000 埠執行時，可再跑不經 UI 的完整 Demo 驗收：

```powershell
.\.venv\Scripts\python.exe scripts/demo_check.py
```

最新實測數字、已知環境限制與安全稽核結果見 [TEST_REPORT.md](docs/TEST_REPORT.md) 與 [STATUS.md](STATUS.md)。

## 正式環境前必做

- 產生至少 32 字元的獨立 `JWT_SECRET`，限制 `CORS_ORIGINS`，在 TLS reverse proxy 後提供服務。
- 使用 PostgreSQL、Redis 與獨立 worker；把檔案儲存改成具備備份、保留期與存取控管的持久儲存。
- 在 ingress/WAF 實作分散式 rate limit、檔案惡意程式掃描、監控、告警與備份還原演練。
- 依機構政策處理教材著作權、學生資料最小化與 AI 供應商資料條款。
- 閱讀 [正式部署](docs/PRODUCTION.md)、[安全說明](SECURITY.md) 與 [第三方授權](THIRD_PARTY_NOTICES.md)。

## Repository 導覽

```text
app/                    繁中產品 UI
services/api/           FastAPI、資料模型、生成、檢索、匯出與測試
prompts/                版本化 prompt templates
templates/              PDF／DOCX 樣式與模板
evals/                  24 組 synthetic cases 與 runner
e2e/                    Playwright 核心流程與無障礙驗收
scripts/                seed、demo-check、E2E 隔離 server
infra/                  web／API Dockerfile
docs/                   架構、API、部署、排錯、Demo 與測試報告
artifacts/               本機可再生上傳、匯出與 QA 輸出（不提交內容）
```

故障排除請先看 [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。
