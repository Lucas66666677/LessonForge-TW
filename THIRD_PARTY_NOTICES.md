# 第三方軟體與模型授權摘要

更新日期：2026-08-08。此文件是工程盤點，不是法律意見；實際再散布時應保留各套件／映像／模型內的完整 LICENSE、NOTICE 與 attribution。此文件不授權 LessonForge TW 自身原始碼；repository owner 在對外散布前仍需選擇並加入專案 LICENSE。

## JavaScript runtime dependencies

| 套件 | 版本 | 授權 |
|---|---:|---|
| React / React DOM | 19.2.8 | MIT |
| React Router DOM | 7.18.2 | MIT |
| TanStack React Query | 5.101.4 | MIT |
| React Hook Form / resolvers | 7.85.0 / 5.2.2 | MIT |
| Radix Dialog / Dropdown / Progress / Select / Tabs | locked in `package-lock.json` | MIT |
| Zod | 4.4.3 | MIT |
| clsx | 2.1.1 | MIT |
| lucide-react | 1.30.0 | ISC |

主要 build/test tooling：Vinext、Vite、Vitest、Cloudflare Vite plugin、Wrangler、ESLint、Prettier、Tailwind、Testing Library 與 openapi-typescript 為 MIT 或 MIT/Apache-2.0；TypeScript、Playwright 與 React Server DOM 為 Apache-2.0 或 MIT；`@axe-core/playwright` 4.12.1 為 MPL-2.0。精確 transitive 清單與版本以 `package-lock.json` 及各 `node_modules/*/LICENSE` 為準。

## Python runtime dependencies

FastAPI、Starlette、Uvicorn、Pydantic、SQLAlchemy、Alembic、asyncpg、aiosqlite、pgvector-python、redis-py、PyJWT、argon2-cffi、python-multipart、email-validator、httpx、pypdf、python-docx、Jinja2、Playwright Python、ReportLab 與 SlowAPI 的版本固定於 `pyproject.toml`。其主要授權包含 MIT、BSD-2/3-Clause、Apache-2.0、PSF-compatible 與 Unlicense；完整條款以安裝 distribution 的 `*.dist-info/licenses`／metadata 與上游 LICENSE 為準。

ReportLab 為 BSD-style 授權；產生的 PDF 不因此被套用 ReportLab 授權。Noto CJK 字型由 container 套件提供，散布 image 時需保留其 SIL Open Font License notices。

## 基礎設施

| 元件 | 使用版本／映像 | 授權與注意事項 |
|---|---|---|
| PostgreSQL | 17 | PostgreSQL License，BSD/MIT 類 permissive |
| pgvector | `pgvector/pgvector:pg17` | PostgreSQL License |
| Redis Open Source | `redis:8-alpine` | 可選 RSALv2、SSPLv1 或 AGPLv3；本專案建議由部署者就其模式選擇並遵守 AGPLv3 |
| Ollama | optional `ollama/ollama` | CLI/server repository 為 MIT；個別模型另有獨立授權 |

Redis 的 Python client `redis-py` 為 MIT，與 Redis server 授權不同。Docker base images 與 OS packages 也各有其授權，production SBOM 應從實際 build image 產生。

## AI 模型

| 模型 | 用途 | 授權 |
|---|---|---|
| Qwen3-8B (`qwen3:8b`) | 預設 Ollama 教材生成 | Apache License 2.0 |
| Nomic Embed Text (`nomic-embed-text`) | optional embedding | Apache License 2.0 |
| Mock Provider | Demo/CI | repository 自製規則與 fixture，不下載模型 |

Ollama model tag 可能隨 registry 更新；production 應固定可重現 digest、保存模型 card/LICENSE，並針對量化來源重新審查。切換 OpenAI-compatible 或 Gemini 不會自動取得模型權利，部署者仍須遵守服務條款、資料處理條款與輸出使用限制。

參考上游：

- [Ollama LICENSE](https://github.com/ollama/ollama/blob/main/LICENSE)
- [Qwen3-8B LICENSE](https://huggingface.co/Qwen/Qwen3-8B/blob/main/LICENSE)
- [Nomic Embed Text model card](https://huggingface.co/nomic-ai/nomic-embed-text-v1)
- [Redis licensing](https://redis.io/legal/licenses/)
- [PostgreSQL license](https://www.postgresql.org/about/licence/)
- [pgvector metadata](https://github.com/pgvector/pgvector/blob/master/META.json)
- [Vinext repository and license](https://github.com/cloudflare/vinext)

## 內容與素材

- `fixtures/demo_material.md` 是本 repository 的自製 synthetic 教材，不擷取教科書或考題。
- `public/og.png` 為本專案以圖像生成工具建立的品牌社群預覽，不含第三方商標或教材內容。
- 使用者上傳教材的權利、合理使用範圍、學生資料與生成教材發布責任由部署機構管理；來源引用功能提供 traceability，不等同取得授權。
