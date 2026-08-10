"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, Download, FileCheck2, FileText } from "lucide-react";
import { useState } from "react";
import { api, downloadExport } from "../lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  PageHeader,
  StatusPill,
} from "../components/ui";

export function ExportsPage({ token }: { token: string }) {
  const query = useQuery({
    queryKey: ["packages"],
    queryFn: () => api.packages(token),
  });
  const [message, setMessage] = useState("");
  const [active, setActive] = useState("");
  const download = async (
    packageId: string,
    variant: string,
    format: string,
  ) => {
    const key = `${packageId}-${variant}-${format}`;
    setActive(key);
    setMessage("");
    try {
      await downloadExport(token, packageId, variant, format);
      setMessage("檔案已完成並開始下載。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "匯出失敗");
    } finally {
      setActive("");
    }
  };
  if (query.isLoading) return <LoadingState label="載入匯出中心…" />;
  if (query.error)
    return (
      <ErrorState
        message={
          query.error instanceof Error ? query.error.message : "無法載入教材包"
        }
      />
    );
  return (
    <div className="page-stack">
      <PageHeader
        title="匯出中心"
        description="將學生、教師、作業、週考與家長回報輸出為 PDF 或 DOCX。"
      />
      {message ? (
        <Notice kind={message.includes("完成") ? "success" : "error"}>
          {message}
        </Notice>
      ) : null}
      {!query.data?.length ? (
        <EmptyState
          title="沒有可匯出的教材包"
          description="產生教材後即可在這裡下載不同版本。"
        />
      ) : (
        query.data.map((item) => (
          <Card key={item.id} className="export-card">
            <div className="export-package">
              <div className="file-avatar">
                <BookOpen />
              </div>
              <div>
                <h2>{item.title}</h2>
                <span>
                  {item.lesson_date} · {item.total_minutes} 分鐘 · v
                  {item.current_version}
                </span>
              </div>
              <StatusPill value={item.status} />
            </div>
            <div className="export-grid">
              {[
                {
                  key: "student",
                  label: "學生版",
                  description: "無答案與教師備註",
                },
                {
                  key: "teacher",
                  label: "教師版",
                  description: "答案、解析、備註與引用",
                },
                {
                  key: "homework",
                  label: "作業版",
                  description: "每日作業與完整答案",
                },
                {
                  key: "quiz",
                  label: "週考版",
                  description: "題目卷與答案卷分頁",
                },
                {
                  key: "parent",
                  label: "家長回報",
                  description: "本週表現與下週重點",
                },
              ].map((variant) => (
                <div key={variant.key}>
                  <div>
                    <FileCheck2 />
                    <span>
                      <strong>{variant.label}</strong>
                      <small>{variant.description}</small>
                    </span>
                  </div>
                  <div className="button-row">
                    <Button
                      variant="secondary"
                      onClick={() => download(item.id, variant.key, "pdf")}
                      disabled={Boolean(active)}
                    >
                      <Download />
                      {active === `${item.id}-${variant.key}-pdf`
                        ? "產生中"
                        : "PDF"}
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => download(item.id, variant.key, "docx")}
                      disabled={Boolean(active)}
                    >
                      <FileText />
                      {active === `${item.id}-${variant.key}-docx`
                        ? "產生中"
                        : "DOCX"}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))
      )}
    </div>
  );
}
