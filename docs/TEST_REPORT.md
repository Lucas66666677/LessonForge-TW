# LessonForge TW 最終測試報告

測試日期：2026-08-08
環境：Windows、Node.js 22、Python 3.11、Chromium；Mock Provider；SQLite/in-process jobs

## 結論

MVP 必要流程已通過自動化與人工驗收。Mock Provider 不需要付費 API key，即可完成登入、組織與成員、班級、教材上傳解析、背景生成、編輯、鎖定、局部重生、版本、核准、預覽與 PDF／DOCX 匯出。跨租戶存取、修改、生成與下載皆以 404 隱藏資源。

## 自動化結果

| 類別 | 指令 | 結果 |
|---|---|---|
| 乾淨安裝 | `npm ci` | 通過；依 lockfile 安裝 624 packages |
| Python 安裝 | `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` | 通過 |
| Fresh DB | `alembic upgrade head`（隔離空白 SQLite） | 通過；套用 `98de56af41b1` |
| Seed | `.\.venv\Scripts\python.exe scripts/seed.py` | 通過；兩個 Demo 帳號可用 |
| Web lint | `npm run lint` | 通過 |
| Web 型別 | `npm run typecheck` | 通過；TypeScript strict |
| Web unit | `npm run test:unit` | 4 files、6 tests 通過 |
| Production build | `npm run build` | 通過；Vinext/Vite 五階段 build 完成 |
| Python lint | `.\.venv\Scripts\python.exe -m ruff check services` | 通過 |
| Python 型別 | `.\.venv\Scripts\python.exe -m mypy services/api/lessonforge` | 通過；17 source files |
| API/integration | `.\.venv\Scripts\python.exe -m pytest` | 16 tests 通過 |
| Synthetic eval | `.\.venv\Scripts\python.exe evals/run_eval.py` | 24 cases，整體通過 |
| Browser E2E | `npm run e2e` | Chromium 2 tests 通過 |
| API Demo | `.\.venv\Scripts\python.exe scripts/demo_check.py` | PASS |
| Python CVE | `.\.venv\Scripts\python.exe -m pip_audit --local` | 已安裝第三方套件無已知漏洞 |

Pytest 唯一 warning 是 Starlette 對 TestClient/httpx 相容層的棄用通知，不影響測試或產品執行。

## E2E 覆蓋

- 真實 Chromium 完成 Demo 登入、建立班級、上傳 Markdown、等待背景生成。
- 編輯 nested questions、鎖定區塊、確認鎖定區塊拒絕重生、核准教材。
- 學生預覽不含答案／解析／教師備註；教師預覽包含答案與解析。
- 實際下載學生與教師 PDF，檢查下載檔名與內容。
- axe 掃描登入與工作台，WCAG A/AA 的 serious/critical violations 為 0。
- 鍵盤可使用 skip link 直接進入主要內容。

## Demo check 證據

隔離空白 SQLite 經 migration 與 seed 後，API 驗收結果：

- `locked_block_preserved: true`
- `cross_tenant_denied: true`
- `student_answer_leak: false`
- `teacher_answers_present: true`
- 學生 PDF／DOCX、教師 PDF／DOCX 均成功產出且非空。

## Eval 指標

| 指標 | 結果 |
|---|---:|
| Schema valid | 100% |
| 必填欄位完整 | 100% |
| 時間總和正確 | 100% |
| 題目重複率 | 1.49% |
| 答案有效 | 100% |
| 來源引用 | 100% |
| 學生版答案洩漏 | 0% |
| 鎖定區塊保留 | 100% |
| 難度可區分 | 100% |

## 匯出與視覺 QA

- 實際產出學生、教師、作業、週考、家長回報五種 PDF 與 DOCX。
- PDF 以 Poppler 逐頁 render 後檢查；中文字型、頁面邊界、題目與答案區段正常。
- 此機器沒有 LibreOffice；DOCX 改以已安裝的 Microsoft Word COM 轉成 PDF，再以 Poppler 逐頁檢查。DOCX 本身亦以 `python-docx` 解析驗證學生版無答案。
- 1440×900 桌面與 834×1112 平板皆檢查登入、工作台、班級、教材、生成、編輯器與預覽；無水平溢出，瀏覽器 console 無錯誤。
- QA 截圖保存在 `artifacts/screenshots/`。

## 安全與供應鏈

- `pip-audit`：第三方 Python dependencies 無已知漏洞；本地 editable package 因不在 PyPI 而略過是預期行為。
- secret／TODO 掃描：未發現密鑰、token、raw prompt、真正 TODO、FIXME 或未實作提示。
- `npm audit`：剩餘 2 個 high package findings，都是 Vinext 間接鎖定的 `image-size@2.0.2` ICNS/JXL/HEIF parser DoS。`npm audit fix --force` 會把 Vinext 降到不相容的 `0.0.45`，因此未採用破壞性降版。本產品上傳白名單只接受 PDF、DOCX、TXT、MD，使用者檔案不會進入 Vinext 的 build-time image parser；CI 仍以 critical 為阻擋門檻，並應持續追蹤 Vinext 上游更新。

## 未在本機執行

- Docker Desktop 未安裝，因此 PostgreSQL/pgvector、Redis、獨立 worker 的 Compose 拓樸未實際啟動；設定與 Dockerfile 已納入 repository。
- Ollama 未安裝，因此 live LLM eval 未宣稱通過；Mock 完整流程已通過。安裝、pull、serve 與 live eval 指令見 README。
- GNU Make 未安裝；所有 Make target 均有 README 中的 PowerShell/npm/Python 等效指令。
