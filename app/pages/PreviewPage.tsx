"use client";

import * as Tabs from "@radix-ui/react-tabs";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText, Printer } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { downloadExport, fetchPreview } from "../lib/api";
import {
  Button,
  ErrorState,
  LoadingState,
  Notice,
  PageHeader,
} from "../components/ui";

const variants = [
  { value: "student", label: "學生版" },
  { value: "teacher", label: "教師版" },
  { value: "homework", label: "作業版" },
  { value: "quiz", label: "週考版" },
  { value: "parent", label: "家長回報" },
];

export function PreviewPage({ token }: { token: string }) {
  const { id = "" } = useParams();
  const [variant, setVariant] = useState("student");
  const [format, setFormat] = useState("pdf");
  const [message, setMessage] = useState("");
  const [downloading, setDownloading] = useState(false);
  const query = useQuery({
    queryKey: ["preview", id, variant],
    queryFn: () => fetchPreview(token, id, variant),
    enabled: Boolean(id),
  });
  const download = async () => {
    setDownloading(true);
    setMessage("");
    try {
      await downloadExport(token, id, variant, format);
      setMessage(
        `${variants.find((item) => item.value === variant)?.label} ${format.toUpperCase()} 已下載。`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "匯出失敗");
    } finally {
      setDownloading(false);
    }
  };
  return (
    <div className="page-stack">
      <PageHeader
        title="教材預覽"
        description="學生版與教師版內容分離；列印模板使用 A4 版面與繁中字型。"
        actions={
          <>
            <select
              className="input format-select"
              value={format}
              onChange={(event) => setFormat(event.target.value)}
              aria-label="輸出格式"
            >
              <option value="pdf">PDF</option>
              <option value="docx">DOCX</option>
            </select>
            <Button onClick={download} disabled={downloading}>
              <Download />
              {downloading ? "產生中…" : "下載此版本"}
            </Button>
          </>
        }
      />
      {message ? (
        <Notice kind={message.includes("已下載") ? "success" : "error"}>
          {message}
        </Notice>
      ) : null}
      <Tabs.Root value={variant} onValueChange={setVariant}>
        <Tabs.List className="preview-tabs" aria-label="教材版本">
          {variants.map((item) => (
            <Tabs.Trigger value={item.value} key={item.value}>
              {item.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        {variants.map((item) => (
          <Tabs.Content value={item.value} key={item.value}>
            {query.isLoading ? (
              <LoadingState label={`產生${item.label}預覽…`} />
            ) : query.error ? (
              <ErrorState
                message={
                  query.error instanceof Error
                    ? query.error.message
                    : "預覽失敗"
                }
                retry={() => void query.refetch()}
              />
            ) : (
              <div className="preview-frame-wrap">
                <div className="preview-toolbar">
                  <span>
                    <Printer />
                    A4 列印預覽
                  </span>
                  <span>
                    <FileText />
                    {item.label}
                  </span>
                </div>
                <iframe
                  title={`${item.label}預覽`}
                  className="preview-frame"
                  srcDoc={query.data}
                />
              </div>
            )}
          </Tabs.Content>
        ))}
      </Tabs.Root>
    </div>
  );
}
