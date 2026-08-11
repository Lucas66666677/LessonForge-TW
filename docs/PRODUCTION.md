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
5. 驗證 `/health`、登入、tenant 404、Mock 或指定 provider 生成、學生／教師分版匯出。
6. 觀察 queue、錯誤率、匯出延遲與磁碟用量後再結束 rollout。

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
