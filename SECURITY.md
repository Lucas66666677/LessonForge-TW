# 安全政策與實作說明

## 回報方式

請使用 repository 所在平台的 private security advisory 或組織既有的私密安全通道，附上受影響版本、重現步驟、預期／實際結果與影響。不要在公開 issue 放 token、教材、學生資料、資料庫 dump 或可直接利用的 production 細節。

## 安全邊界

- API 不接受前端傳入 organization ID 作為授權依據；JWT identity 會再查 membership。
- 所有 tenant-owned SQL 查詢同時比對 resource ID 與 `organization_id`；foreign UUID 回傳 404。
- 密碼用 Argon2id；JWT 固定 issuer/audience、`iat`、`nbf`、`exp`，只接受 HS256。
- Owner/Admin/Teacher 的授權在 API 執行，前端隱藏按鈕只是 UX。
- 上傳限制格式與大小，檢查副檔名、MIME、signature、SHA-256，UUID 儲存且隔離 tenant 路徑。
- Jinja2 autoescape；學生匯出有獨立欄位 policy，不靠 CSS 隱藏答案。
- AI、教材、prompt 與 output 都是不可信資料，需經 Pydantic、有限 repair 與 validators；鎖定區塊做 exact preservation。
- Raw 教材／prompt／AI content 預設不寫 log；學生使用代號。

## 2026-08-08 依賴稽核

- `python -m pip_audit --local`：已知漏洞 0；本地 editable `lessonforge-tw` 因未發布到 PyPI 而跳過。建置工具 `setuptools` 已升到 83.0.0。
- `npm audit`：critical 0、moderate 0、low 0；剩餘 2 個 high package entries，為 `vinext` 與其固定的 `image-size@2.0.2`，來源是同一組 ICNS/JXL/HEIF parser 無限迴圈 DoS advisories。
- React RSC、Vite、Wrangler、Cloudflare plugin、Babel、Undici、ws、PostCSS、js-yaml 等可修告警已升級或以相容 override 清除。

Vinext 1.0.0-beta.5 目前仍固定 `image-size@2.0.2`，registry 無修補版；`npm audit fix --force` 只會降級到不相容的 Vinext 0.0.45，因此未採用。實際曝險受限於 Vinext build-time 解析 repository 圖片；LessonForge 上傳 API 不接受 ICNS/JXL/HEIF，也不會把 tenant upload 傳給 Vinext。控制措施：只有受信任 maintainer 能新增 build assets、CI 不建置 PR 產生的任意二進位 asset、持續追蹤上游並在修補版可用時升級。這是接受過的暫時 residual risk，不代表告警已消失。

CI 對 npm critical 漏洞與所有可稽核 Python 漏洞失敗。因上述有文件化控制的上游 residual，npm gate 暫設 `--audit-level=critical`；升級後應恢復更嚴格門檻。

## Production 必補控制

- Secrets manager、TLS、HSTS、CSP、`nosniff`、frame policy 與嚴格 CORS。
- Ingress/Redis 分散式 rate limit；目前記憶體 limiter 只適合單程序 Demo。
- 上傳惡意程式掃描、隔離解析、object storage IAM、加密與保留期。
- DB/檔案/備份還原演練、監控、告警、incident runbook。
- 登入失敗鎖定、密碼重設／邀請、MFA 或 SSO；Demo 帳密不得存在 production。
- 定期 DAST/SAST、dependency update、tenant isolation regression 與 provider data-flow review。

## 公開 Demo 帳密回歸防護

`#3` 移除了曾公開的 Demo 帳號與共用密碼。CI 在 `npm run build` 之後執行
`python scripts/check_demo_credentials.py --build-dir dist`，若下列任一情況出現就讓建置失敗：

- 已退役的密碼字串重新出現在原始碼、文件或 production bundle。
- `.env.example` 的 `DEMO_*_PASSWORD` 帶有值，或 `Settings` 的 demo 密碼預設值不是空字串。
- 登入表單重新預填 email／密碼，或瀏覽器端原始碼、production bundle 出現 Demo 帳號位址。
- `scripts/seed.py` 失去 `APP_ENV=production` 的 seeding 阻擋。

bundle 掃描涵蓋建置輸出中的每一個文字檔，包含 `_headers`、`BUILD_ID` 這類沒有副檔名的
檔案與 `.svg`；字型與圖片等二進位檔則以內容判斷後略過。

這個檢查只讀 repository 與建置輸出，不需要任何 secret。退役新的憑證時，把字串加進
`RETIRED_SECRETS`，門檻才會持續涵蓋每一次事件。

## 不支援的安全假設

- Mock Provider 不是內容品質或事實正確性保證。
- 本機 SQLite、in-process queue 與檔案儲存不是多 instance production 架構。
- 掃描 PDF 不會自動 OCR；無惡意程式掃描不代表檔案安全。
- 教師核准不取代機構對著作權、個資、AI 使用與教學內容的責任。
