# API 摘要

開發環境 Swagger UI：`http://127.0.0.1:8000/docs`；OpenAPI JSON：`/openapi.json`。除 `/health`、`/docs`、`/openapi.json` 與登入外，請求需帶：

```http
Authorization: Bearer <access_token>
```

JWT 包含 `sub`、`org`、`role`、`iat`、`nbf`、`exp`、`iss` 與 `aud`。API 仍會查 membership，不信任用戶自行提供的 organization ID。

## 端點

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/health` | 服務版本與健康狀態 |
| POST | `/api/auth/login` | Email／密碼登入 |
| GET | `/api/auth/me` | 目前使用者、組織與角色 |
| POST | `/api/organizations` | 建立新組織並取得 owner token |
| GET | `/api/organizations/current/members` | 成員清單 |
| POST | `/api/organizations/current/members` | Owner/Admin 建立成員 |
| GET/POST | `/api/classes` | 班級清單／建立班級 |
| GET/PATCH/DELETE | `/api/classes/{class_id}` | 班級讀取、修改、刪除 |
| POST | `/api/classes/{class_id}/students` | 新增匿名學生 profile |
| GET/POST | `/api/materials` | 教材清單／multipart 上傳 |
| GET/DELETE | `/api/materials/{material_id}` | 教材、chunks 與刪除 |
| POST | `/api/generation` | 建立背景生成工作，回傳 202 |
| GET | `/api/generation/{run_id}` | 輪詢進度與失敗原因 |
| POST | `/api/generation/{run_id}/retry` | 重試 completed/failed 工作 |
| GET | `/api/packages` | 教材包清單 |
| GET | `/api/packages/{package_id}` | 完整 package、blocks、issues |
| PATCH | `/api/packages/{package_id}/blocks/{block_id}` | 更新區塊與題目 |
| POST | `.../blocks/{block_id}/lock` | 鎖定／解鎖 |
| POST | `.../blocks/{block_id}/regenerate` | 局部重生，鎖定時 409 |
| POST | `.../blocks/{block_id}/copy` | 複製區塊 |
| POST | `.../blocks/{block_id}/move` | 上移／下移 |
| DELETE | `.../blocks/{block_id}` | 刪除區塊 |
| GET | `/api/packages/{package_id}/versions` | 版本清單 |
| POST | `/api/packages/{package_id}/versions/{version_id}/restore` | 還原並建立新版本 |
| POST | `/api/packages/{package_id}/submit-review` | Teacher 送審 |
| POST | `/api/packages/{package_id}/approve` | Owner/Admin 核准；fatal issue 時 409 |
| GET | `/api/packages/{package_id}/preview/{variant}` | HTML 預覽 |
| GET | `/api/packages/{package_id}/export/{variant}.{file_format}` | PDF／DOCX 下載 |
| GET | `/api/settings/ai` | Provider、model 與 fallback 狀態 |

`variant` 為 `student`、`teacher`、`homework`、`quiz`、`parent`；`file_format` 為 `pdf` 或 `docx`。

## 上傳範例

```bash
curl -X POST http://127.0.0.1:8000/api/materials \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@fixtures/demo_material.md;type=text/markdown" \
  -F "grade=國三" \
  -F "chapter=Reading Strategies" \
  -F "topic=Claim and Evidence" \
  -F "difficulty=中等" \
  -F "tags=閱讀,證據"
```

## 生成請求重點

`GenerationRequest` 必填 `class_id`、一個以上 `material_ids`、`lesson_date` 與一個以上 `objectives`。`lesson_minutes` 為 30–360；`difficulty_ratio` 總和必須 100；可設定題型數量、作業天數、是否包含週考／家長報告、教師指示與 module 清單。

建立工作後輪詢 `/api/generation/{id}`。狀態為 `queued`、`running`、`completed` 或 `failed`；完成時 `lesson_package_id` 有值。

## 錯誤語意

- `400/422`：輸入格式、MIME、signature、檔案內容或 Pydantic validation 失敗。
- `401`：缺少、過期或無效 JWT。
- `403`：目前 membership 角色不能執行動作。
- `404`：資源不存在或不屬於目前 tenant。
- `409`：鎖定衝突、狀態衝突、仍有 fatal issue 或工作不可重試。
- `413`：上傳超過 `UPLOAD_MAX_MB`。
- `429`：超過 rate limit。

錯誤通常為 `{"detail": "繁體中文訊息"}`。前端不得依賴英文 exception 文本做流程判斷。

## Contract 更新

新增或調整 endpoint 後，API 啟動於 8000 埠並執行：

```powershell
npm run generate:client
npm run typecheck
```

`app/lib/api-types.ts` 是由 OpenAPI 產生的 contract snapshot；手寫呼叫集中在 `app/lib/api.ts`。
