# LessonForge TW 狀態

更新日期：2026-08-21

## 2026-08-21 Lucirel release candidate

- 導入 Lucirel Wave Gate v1.0 與公司共用的暖白、深墨、藍／青色視覺語言；登入頁、側欄與主要工作區已完成桌面及 390px 行動版檢查。
- 受保護路由改為按功能載入；登入與伺服器端使用者驗證仍是進入工作區前的必要安全閘門。
- Vinext 升級至已修補 `image-size` DoS 的 `1.0.0-beta.8`；隔離 Node 與 Python 環境的供應鏈稽核均為零已知漏洞。
- 本機驗證：lint、typecheck、build、5 files／7 unit tests、17 backend tests、24-case eval、2 個完整 Chromium E2E 與 Demo Check 全數通過。
- 桌面 1440×900 與行動 390×844 的登入／工作台均無水平溢位及瀏覽器 console error；核心 E2E 同時通過 WCAG A/AA serious/critical 掃描。

## 目前階段

M0–M7 已完成。LessonForge TW 已達到本機 Mock MVP 與公開線上 Demo 的交付標準；沒有會阻止核心流程的 TODO、假按鈕或未實作 API。

## 已完成

- 繁體中文 React 產品 UI：登入、工作台、班級、學生、教材、生成精靈、進度、教材包、編輯器、預覽、匯出、成員與設定。
- FastAPI、Pydantic、SQLAlchemy、Alembic、JWT/Argon2、Owner/Admin/Teacher 權限與 audit log。
- 所有 tenant-owned 查詢顯式帶入 `organization_id`；跨租戶讀取、修改、生成與下載測試通過。
- PDF／DOCX／TXT／MD 安全上傳、解析、chunk、metadata、全文 fallback 與 PostgreSQL/pgvector 路徑。
- Mock、Ollama、OpenAI-compatible、Gemini Provider；分階段背景生成、schema repair、驗證、重試與 generation audit metrics。
- 結構化區塊編輯、排序、複製、刪除、鎖定、局部重生、版本還原、送審與核准。
- 五種用途的 PDF／DOCX；學生版答案隔離與教師版答案／解析驗證。
- CI、24-case eval、單元／整合／E2E／a11y、桌面與平板視覺 QA、文件與 Demo script。

## 最終驗證結果

| 驗證 | 結果 |
|---|---|
| `npm ci` | 通過 |
| `npm run lint` | 通過 |
| `npm run typecheck` | 通過 |
| `npm run test:unit` | 4 files、6 tests 通過 |
| `npm run build` | 通過 |
| `python -m ruff check services` | 通過 |
| `python -m mypy services/api/lessonforge` | 17 source files 通過 |
| `python -m pytest` | 17 tests 通過；1 個非阻擋 deprecation warning |
| `python evals/run_eval.py` | 24 cases 通過 |
| `npm run e2e` | Chromium 2 tests 通過 |
| Fresh SQLite migration + seed | 通過 |
| `python scripts/demo_check.py` | PASS |
| `pip-audit --local` | 第三方套件無已知漏洞 |
| Render PostgreSQL + pgvector migration + seed | 通過；API revision `e9cb829` 為 Live |
| 線上 `/health` | `200 OK`，服務狀態 `ok` |
| 線上 Demo Owner 登入 + 班級查詢 | 通過；`owner` 角色、1 個 Demo 班級 |
| OpenAI Sites 公開正式部署 | version 2 發佈成功，已連接 Render API |

完整數字與風險說明見 `docs/TEST_REPORT.md`。

## 環境限制與已知風險

- 此機器沒有 Docker、Ollama 與 GNU Make；因此 Compose live topology 與 Ollama live generation 尚未在本機實跑，README 提供可直接執行的命令。
- Vinext／`image-size` 的歷史 high findings 已由 `vinext@1.0.0-beta.8` 解決；`npm audit` 目前為零。
- 此工作區早期開發用 SQLite 曾在沒有 Alembic version 的狀態下建表；未刪除該既有資料。最終 fresh-clone rehearsal 使用全新隔離 SQLite，migration 與 seed 均通過。
- DOCX 視覺 QA 因沒有 LibreOffice，改用 Microsoft Word COM 轉 PDF 後逐頁檢查，差異已如實記錄。
- 線上 Demo 使用 Render Free：閒置 15 分鐘後 API 會休眠，冷啟動可能超過 50 秒；免費 PostgreSQL 容量 1 GB、30 天到期且沒有備份。
- Render Free 的本機檔案系統為暫時性儲存；重啟後上傳原檔與匯出檔可能消失。線上 Demo 使用 Mock Provider，不會產生付費模型費用。
- OpenAI Sites 已開放匿名訪客使用 Demo；正式商用前仍需完成外部存取政策、濫用防護與正式基礎設施。

## 商用化下一步

1. 在實際部署環境啟動 PostgreSQL/pgvector、Redis、worker 與持久化物件儲存，做備份還原演練。
2. 安裝 Ollama，使用目標硬體與教材跑 live eval，建立 latency、品質與模型升級基準。
3. 導入 ingress/WAF 分散式 rate limit、惡意檔案掃描、監控、告警、TLS 與秘密管理。
4. 完成機構資料處理條款、教材授權、學生資料最小化、保留期與稽核政策。
5. 加入 SBOM 與持續供應鏈掃描，並持續追蹤 Vinext 穩定版。
