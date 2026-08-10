"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, CheckCircle2, Database, HardDrive, Server } from "lucide-react";
import { api } from "../lib/api";
import {
  Card,
  ErrorState,
  LoadingState,
  Notice,
  PageHeader,
} from "../components/ui";

export function SettingsPage({ token }: { token: string }) {
  const query = useQuery({
    queryKey: ["ai-settings"],
    queryFn: () => api.aiSettings(token),
  });
  if (query.isLoading) return <LoadingState label="讀取系統設定…" />;
  if (query.error || !query.data)
    return (
      <ErrorState
        message={
          query.error instanceof Error ? query.error.message : "無法載入設定"
        }
      />
    );
  const data = query.data;
  return (
    <div className="page-stack">
      <PageHeader
        title="AI 與系統設定"
        description="目前為唯讀環境摘要；透過 .env 切換 Provider 與模型後重新啟動服務。"
      />
      <Notice>
        <CheckCircle2 />
        未設定任何付費 API Key 也可使用 Mock Provider 完成全部 Demo。
      </Notice>
      <div className="settings-grid">
        <Card>
          <div className="settings-icon">
            <Bot />
          </div>
          <span>LLM Provider</span>
          <h2>{String(data.provider)}</h2>
          <dl className="detail-list">
            <div>
              <dt>模型</dt>
              <dd>{String(data.model)}</dd>
            </div>
            <div>
              <dt>Base URL</dt>
              <dd>{String(data.base_url)}</dd>
            </div>
            <div>
              <dt>API Key</dt>
              <dd>
                {data.api_key_configured ? "已設定" : "未設定（目前不需要）"}
              </dd>
            </div>
          </dl>
        </Card>
        <Card>
          <div className="settings-icon">
            <Database />
          </div>
          <span>Embedding 與檢索</span>
          <h2>{String(data.embedding_provider)}</h2>
          <dl className="detail-list">
            <div>
              <dt>Embedding model</dt>
              <dd>{String(data.embedding_model)}</dd>
            </div>
            <div>
              <dt>Fallback</dt>
              <dd>PostgreSQL 全文／詞彙檢索</dd>
            </div>
          </dl>
        </Card>
        <Card>
          <div className="settings-icon">
            <HardDrive />
          </div>
          <span>隱私</span>
          <h2>本機優先</h2>
          <dl className="detail-list">
            <div>
              <dt>Raw AI content log</dt>
              <dd>{data.raw_content_logging ? "開啟" : "關閉"}</dd>
            </div>
            <div>
              <dt>學生資料</dt>
              <dd>以代號／暱稱為主</dd>
            </div>
          </dl>
        </Card>
      </div>
      <Card>
        <div className="section-heading">
          <div>
            <span className="eyebrow">Ollama</span>
            <h2>切換本機真實模型</h2>
          </div>
          <Server />
        </div>
        <ol className="setup-steps">
          <li>
            <span>1</span>
            <div>
              <strong>安裝並啟動 Ollama</strong>
              <code>ollama serve</code>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <strong>下載預設模型</strong>
              <code>ollama pull qwen3:8b</code>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <strong>更新 .env</strong>
              <code>LLM_PROVIDER=ollama</code>
            </div>
          </li>
          <li>
            <span>4</span>
            <div>
              <strong>測試連線</strong>
              <code>curl http://localhost:11434/api/tags</code>
            </div>
          </li>
        </ol>
      </Card>
    </div>
  );
}
