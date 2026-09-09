# 正式部署指南

## 線上 Demo 拓樸

Repository 內的 `render.yaml` 會建立 Singapore 區域的 Render Web Service 與
PostgreSQL，API 容器啟動時自動執行 migration 與冪等 Demo seed。前端部署於
Sites，瀏覽器只呼叫同網域 `/api/*`，由 Worker 透過託管的 `API_BASE_URL`
代理至 FastAPI，因此後端位址與 CORS 不會寫死在前端 bundle。

免費 Render Web Service 閒置後會休眠，首次請求可能需要約一分鐘喚醒；免費
PostgreSQL 會在建立 30 天後到期，僅適合公開 Demo，不是商用正式環境。

本文件描述最低可接受的 production shape。根目錄 Compose 適合單機驗收與內部部署起點，不等同完整高可用平台。

## 必要拓樸

- Web：Vinext production server，唯讀映像。
- API：至少一個 FastAPI instance。
- Worker：至少一個 `python -m lessonforge.worker`，與 API 使用同版 image。
- PostgreSQL 17 + pgvector；執行 Alembic migration。
- Redis 8 queue；API 設 `IN_PROCESS_JOBS=false`。
- 持久檔案／object storage，必須做 tenant prefix、加密、備份與生命週期管理。
- TLS reverse proxy 或受管 ingress；外部只公開 443，API 與資料服務留在私網。

## 環境設定

以下值不得沿用 Demo：

```dotenv
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:5432/<database>
REDIS_URL=redis://<host>:6379/0
JWT_SECRET=<至少 32 字元、由 secrets manager 產生>
CORS_ORIGINS=https://lessonforge.example.tw
PUBLIC_APP_URL=https://lessonforge.example.tw
VITE_API_BASE_URL=https://api.lessonforge.example.tw
IN_PROCESS_JOBS=false
LOG_RAW_AI_CONTENT=false
```

`LLM_API_KEY`、資料庫密碼與 JWT secret 只放 secrets manager，不進 image、Git、log 或前端 build。每個環境使用不同 secret；輪替 JWT secret 會使現有 token 失效，應排定維護窗口。

## 發佈順序

1. 以 commit SHA 建置不可變 web/API image，執行 CI 與 E2E。
2. 備份資料庫並先在 staging 執行 `alembic upgrade head`。
3. 正式 DB 執行 migration；同一時間只允許一個 migration job。
4. 先更新 worker，再更新 API，最後更新 web；或在不相容 schema 變更時採 expand/migrate/contract。
5. 先以 `/version` 確認線上跑的是這次要發佈的 commit，再驗證 `/health`、登入、tenant 404、Mock 或指定 provider 生成、學生／教師分版匯出。
6. 觀察 queue、錯誤率、匯出延遲與磁碟用量後再結束 rollout。

## 確認線上跑的是哪一版

`GET /version` 回報目前 process 由哪一個 commit 建置：

```bash
curl -fsS https://lessonforge-tw-api-lucas.onrender.com/version
```

```json
{ "revision": "33539b0c7a1e4d82f6b95c0e3a7d418be2f0c95d" }
```

三種回應，各自代表不同的事：

| 回應 | 線上實際部署的版本 |
| --- | --- |
| `404` | 比加入此路由的 commit 更舊的 build，代表 merge 尚未真正上線 |
| `{"revision": null}` | 此 build 或更新，但 `RENDER_GIT_COMMIT` 未設定或不是 commit SHA |
| `{"revision": "<sha>"}` | 就是該 commit |

與 `git rev-parse origin/main` 比對即可判斷。**部署後請先看這一項**：其餘檢查都是由「當下正在跑的 image」回答的，若跑的是舊 build，全部通過也不構成新版本的證據。

`/health` 的 `version` 欄位不能用來做這件事，且刻意保持原樣。它是 `lessonforge/__init__.py` 內寫死的套件版本 `0.1.0`，每次發佈都相同——看起來像版本識別但其實不是，比沒有更容易誤導：跨版本比對兩次 `/health` 會看到一致，因而誤判部署已生效。該欄位是 Render deploy gate（`render.yaml` 的 `healthCheckPath`）所輪詢的 payload，因此不做修改，改以獨立路由回答這個問題。測試會逐位元組（byte-for-byte）鎖定 `/health` 的回應內容。

`RENDER_GIT_COMMIT` 由 Render 於每次部署自動注入（build 與 runtime 皆有），不需設定，**也不應手動設定**：寫進服務環境變數的固定值會讓 `/version` 永遠回報當初輸入時的 commit，變成一個「有自信但錯誤」的答案，比沒有答案更糟。

此路由與 `/health` 一樣不連資料庫，因此在依賴故障時仍可回應——那正是需要問這個問題的時候；同樣被排除在 rate limiter 之外，因為 rollout 期間反覆輪詢卻開始收到 429 的探針無法作為判斷依據。

路由未經驗證即可存取，因此可公開的內容由 `lessonforge/revision.py` 決定：僅接受錨定的 7–40 位十六進位字元並轉為小寫，其餘一律回 `null`。即使該變數被填入資料庫連線字串、JWT secret 或整行貼上的 `.env`，也只會回報 `null` 而不會回傳其內容；被拒絕的值同樣不寫入 log——拒絕它的理由正是它可能是機密，寫進 log 只是換個地方外洩。

## 建立第一位管理員（首位擁有者）

正式環境的登入是「先有帳號才能登入」，而在此腳本之前**沒有任何途徑能建立第一個帳號**，形成死結：

* `POST /auth/login` 找到使用者後仍要求 membership，沒有時回 `403 帳號不屬於任何可用組織`——只有 user 資料列無法登入。
* `POST /organizations` 會一併建立組織與 owner membership，但它需要 `UserDep`，也就是必須先登入。
* `POST /organizations/current/members` 需要既有的 owner 或 admin。
* `scripts/seed.py` 在 `APP_ENV=production` 時直接拒絕執行（正確：它建立的是共用密碼的示範帳號）。

`scripts/bootstrap_owner.py` 補上且僅補上這一步：一個 user、一個 organization、一個 owner membership。

### 先確認現況，不要假設

```bash
python scripts/bootstrap_owner.py --status
```

「沒有任何程式碼會植入帳號」與「資料庫裡沒有帳號」是**兩件不同的事**。前者可以從 `seed.py` 的防護讀出來；後者是線上資料庫的事實，光讀原始碼永遠無法確定——維運者可能手動插入過資料列，較早的版本也可能在防護加入前就植入過。`--status` 就是用來回答後者，而不是用猜的。

它只回報數量，不輸出 email、顯示名稱或雜湊，因此輸出可以安全貼進 issue：

```text
users:             0
organizations:     0
owner memberships: 0

The database holds no accounts. --create will create the first owner.
```

三種狀態各自代表不同的事：**沒有任何帳號**、**有 user 但沒有 owner**（這些帳號存在卻無法登入，因為登入需要 membership）、**已有 owner**（此時 `--create` 會拒絕）。

### 建立

```bash
BOOTSTRAP_OWNER_PASSWORD='<你自己選的密碼>'   python scripts/bootstrap_owner.py --create     --email owner@your-domain.example     --organization "你的補習班名稱"
```

密碼只從 `BOOTSTRAP_OWNER_PASSWORD` 讀取；腳本不會產生、不會有預設值、不會印出或寫進 log，資料庫中只留 Argon2 雜湊。若不想讓密碼留在 shell 歷史，可加 `--prompt` 在終端機輸入。

**預設路徑永遠不會停住等待輸入。** 這是刻意的：`getpass` 在部分平台會直接讀主控台，即使把 stdin 導向 `/dev/null` 也不會失敗——開發此腳本時實測就這樣卡住直到被強制結束，且完全沒有輸出。會無聲卡住部署步驟的工具，比直接拒絕更糟，所以互動輸入改為 `--prompt` 明示啟用。

腳本另外會拒絕：本專案曾公開過的密碼（與 `scripts/check_demo_credentials.py` 同一份清單）、少於 12 字元的密碼、已存在 owner membership 時的再次執行、以及 email 已被既有 user 使用的情況。

它**不會**執行 migration，也不會建立上述三筆以外的任何資料。請在 schema 已就緒後再執行。

### 建立之後

在公開網站以該帳號登入即可驗證；後續帳號請改用 `POST /organizations/current/members`（會留下稽核紀錄）。

## 資料保護

- 學生使用代號，不收集姓名、電話、地址、學校學號等不必要個資。
- 原始教材、抽取文字、prompt 與模型輸出都視為敏感內容；`LOG_RAW_AI_CONTENT` 保持 `false`。
- 設定組織層級的教材／匯出保留期與刪除流程；備份也要遵守到期刪除。
- DB、檔案、備份使用傳輸中與靜態加密；服務帳號最小權限。
- 上傳前端已有格式與 signature 防線，production 仍應在隔離服務加入惡意程式掃描與內容解壓限制。
- 至少每季做備份還原演練，記錄 RPO/RTO。

## 網路與濫用防護

程式內 rate limiter 是單程序 Demo 保護，不適合多 instance。Production 在 ingress/WAF 或 Redis 實作 user/IP/API-key 維度的分散式限制，並設定 request body、header、連線與 upstream timeout。只允許 web origin 進 CORS；資料庫、Redis 與 Ollama 不公開到網際網路。

設定 CSP、HSTS、`X-Content-Type-Options: nosniff`、frame policy 與安全 cookie policy 應由 ingress 統一處理。目前 JWT 存在 sessionStorage，因此 XSS 防護尤其重要；避免 `dangerouslySetInnerHTML`，升級依賴後重跑 axe/E2E 與 audit。

## Provider 選擇

- `mock`：Demo/CI；不可用於正式教學內容。
- `ollama`：教材留在自管環境；需規劃 GPU/CPU、模型容量、併發與 timeout。
- `openai_compatible`／`gemini`：先完成供應商 DPA、資料保留、區域、模型授權與跨境傳輸審查。

無論 provider 為何，所有輸出都需 Pydantic 與 validator 通過，且由教師核准後才匯出。Live eval 應針對實際模型、量化版本與 prompt version 留存結果。

## 監控與告警

最低指標：API latency/error/429、DB pool、Redis queue depth、generation duration/failure/repair、provider timeout、PDF/DOCX export failure、磁碟／object storage、登入失敗率。Audit log 不應放 raw content。告警 runbook 至少涵蓋 DB 不可用、queue 堆積、provider 不可用、儲存空間不足與疑似跨 tenant 存取。

## 授權與升級

部署 Redis 8 時需在其 tri-license 中選擇並遵守一種授權；本專案建議由組織法務確認 AGPLv3 是否符合部署模式。Ollama 與每個模型的授權彼此獨立。完整盤點見 `THIRD_PARTY_NOTICES.md`。

Vinext 目前為 beta 且有一項無上游修補的 build-time image parser 告警。升級 Vinext/Vite/Cloudflare stack 必須在 branch 完成 build、SSR 200、核心 E2E、axe 與匯出回歸後才能佈署。
