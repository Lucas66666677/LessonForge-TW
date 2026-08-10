# 故障排除

## 3000 或 8000 埠已被占用

PowerShell 找出精確程序：

```powershell
Get-NetTCPConnection -State Listen -LocalPort 3000,8000 |
  Select-Object LocalAddress,LocalPort,OwningProcess
Get-CimInstance Win32_Process -Filter "ProcessId = <PID>" |
  Select-Object ProcessId,ParentProcessId,Name,CommandLine
```

確認 command line 確實屬於此 workspace 後才停止該 PID。不要對整個 Node/Python 程序群做廣泛強制終止。

## 前端顯示 `Failed to fetch`

1. 開啟 `http://127.0.0.1:8000/health`。
2. 確認啟動前端的同一 terminal 有 `VITE_API_BASE_URL=http://127.0.0.1:8000`。
3. 確認 `CORS_ORIGINS` 包含瀏覽器實際 origin（`localhost` 與 `127.0.0.1` 是不同 origin）。
4. 修改 `.env` 後重啟 API；修改 Vite env 後重啟前端。

## `/login` 回傳 500，但 build 成功

Client-only router 或 browser API 若在 SSR render 階段執行會造成 Vinext 錯誤殼。LessonForge 使用 `useSyncExternalStore` 在 hydration 後才掛載 `BrowserRouter`；若改動根元件，請同時驗證：

```powershell
npm run build
npm start
curl.exe -I http://localhost:3000/login
```

應回傳 200，且 HTML 需包含 title 與 Open Graph metadata。

## PDF／DOCX 上傳失敗

- 只接受 `.pdf`、`.docx`、`.txt`、`.md`，預設上限 20 MB。
- 改副檔名不會繞過檢查；signature 與 MIME 不一致會被拒絕。
- 掃描型 PDF 沒有文字層時會顯示 OCR 不支援。請先用合法 OCR 工具建立文字層，再重新上傳。
- 密碼保護、損壞或超大壓縮內容可能無法解析；先在本機閱讀器確認檔案。

## PDF 匯出找不到 Chromium

Python export 使用 Playwright browser：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

Linux container 已安裝 Chromium 與 Noto CJK；自建 image 時需保留中文字型。若中文變方框，確認 `fc-list` 能找到 Noto Sans CJK TC。

## DOCX 視覺驗證工具失敗

`render_docx.py` 預設需要 LibreOffice。Windows 沒有 LibreOffice 時，可使用已安裝的 Microsoft Word 另存 PDF做人工 QA；這只是驗證替代，不影響 API 產生 DOCX。正式自動化建議在 CI image 安裝 LibreOffice。

## Ollama 連不上

```powershell
ollama list
curl.exe http://localhost:11434/api/tags
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

API 在 Docker、Ollama 在 host 時，`LLM_BASE_URL` 應為 `http://host.docker.internal:11434`；兩者都在 Compose 時可改成 `http://ollama:11434`。確認 model name 與 `ollama list` 完全一致。無法連線時先切回 `LLM_PROVIDER=mock` 驗證其餘流程。

## 生成工作卡住

- 本機：`IN_PROCESS_JOBS=true`，API 必須保持執行。
- 正式：`IN_PROCESS_JOBS=false`，確認 Redis 與 `python -m lessonforge.worker` 存活。
- 查 `/api/generation/{id}` 的 `progress_message`、`attempt_count`、`failure_reason`。
- 只有 `failed` 或 `completed` 工作可以 retry；running 工作重試會 409。

## E2E webServer timeout

先確認 3000/8100 沒有孤兒程序。Playwright 設定會啟動隔離 SQLite API（8100）與 Vinext（3000）；前端在此機器綁定 IPv6 localhost，因此 readiness URL 使用 `http://localhost:3000/login`，不要硬改為 `127.0.0.1`。

```powershell
npx playwright install chromium
npm run e2e
```

失敗時查看 `test-results/` screenshot、video、trace 與 `playwright-report/`。

## Migration 或 SQLite 鎖定

不要同時以多個 API 寫同一個 SQLite Demo DB。Production 使用 PostgreSQL。Alembic：

```powershell
.\.venv\Scripts\python.exe -m alembic -c services/api/alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c services/api/alembic.ini upgrade head
```

不要在未備份 production DB 上手動刪表或重建 schema。
