"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Plus, Trash2, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Modal,
  Notice,
  PageHeader,
  StatusPill,
} from "../components/ui";

export function MaterialsPage({ token }: { token: string }) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["materials"],
    queryFn: () => api.materials(token),
  });
  const upload = useMutation({
    mutationFn: (data: FormData) => api.uploadMaterial(token, data),
    onSuccess: async (item) => {
      await queryClient.invalidateQueries({ queryKey: ["materials"] });
      setMessage(
        item.parse_status === "ready"
          ? "教材已完成解析並可供檢索。"
          : (item.parse_error ?? "解析失敗"),
      );
      setOpen(false);
    },
    onError: (error) =>
      setMessage(error instanceof Error ? error.message : "上傳失敗"),
  });
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setMessage("請先選擇檔案");
      return;
    }
    const data = new FormData(form);
    data.set("file", file);
    upload.mutate(data);
  };
  return (
    <div className="page-stack">
      <PageHeader
        title="教材庫"
        description="上傳補習班自有教材，查看解析文字、來源位置與檢索狀態。"
        actions={
          <Button
            onClick={() => {
              setMessage("");
              setOpen(true);
            }}
          >
            <Plus />
            上傳教材
          </Button>
        }
      />
      {message ? (
        <Notice kind={message.includes("完成") ? "success" : "error"}>
          {message}
        </Notice>
      ) : null}
      {query.isLoading ? (
        <LoadingState label="載入教材庫…" />
      ) : query.error ? (
        <ErrorState
          message={
            query.error instanceof Error ? query.error.message : "無法載入教材"
          }
          retry={() => void query.refetch()}
        />
      ) : !query.data?.length ? (
        <EmptyState
          title="教材庫目前是空的"
          description="支援含文字層 PDF、DOCX、UTF-8 TXT 與 Markdown，單檔預設上限 20 MB。"
          action={
            <Button onClick={() => setOpen(true)}>
              <UploadCloud />
              上傳第一份教材
            </Button>
          }
        />
      ) : (
        <Card>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>教材</th>
                  <th>年級／章節</th>
                  <th>標籤</th>
                  <th>狀態</th>
                  <th>大小</th>
                </tr>
              </thead>
              <tbody>
                {query.data.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link
                        className="material-name"
                        to={`/materials/${item.id}`}
                      >
                        <span className="file-avatar">
                          <FileText />
                        </span>
                        <span>
                          <strong>{item.display_name}</strong>
                          <small>{item.topic || "未設定主題"}</small>
                        </span>
                      </Link>
                    </td>
                    <td>
                      {item.grade || "不限"}
                      <small>{item.chapter || "未設定章節"}</small>
                    </td>
                    <td>
                      <div className="tag-cloud compact">
                        {item.tags.slice(0, 3).map((tag) => (
                          <span className="tag" key={tag}>
                            {tag}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <StatusPill value={item.parse_status} />
                    </td>
                    <td>
                      {Math.max(1, Math.round(item.size_bytes / 1024))} KB
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      <Modal
        open={open}
        onOpenChange={setOpen}
        title="上傳教材"
        description="系統會檢查實際檔案內容，不只依賴副檔名。"
      >
        <form className="modal-form" onSubmit={submit}>
          {message ? <Notice kind="error">{message}</Notice> : null}
          <label className="upload-zone">
            <UploadCloud />
            <strong>選擇 PDF、DOCX、TXT 或 Markdown</strong>
            <span>單檔上限 20 MB；掃描 PDF 目前不支援 OCR</span>
            <input
              ref={fileRef}
              type="file"
              name="file"
              accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
              required
            />
          </label>
          <div className="form-grid">
            <Field label="年級">
              <select className="input" name="grade" defaultValue="國三">
                <option value="">不限</option>
                <option>國一</option>
                <option>國二</option>
                <option>國三</option>
                <option>高一</option>
                <option>高二</option>
                <option>高三</option>
              </select>
            </Field>
            <Field label="難度">
              <select className="input" name="difficulty" defaultValue="中等">
                <option>基礎</option>
                <option>中等</option>
                <option>進階</option>
              </select>
            </Field>
            <Field label="章節">
              <Input name="chapter" placeholder="例：Unit 3" />
            </Field>
            <Field label="主題">
              <Input name="topic" placeholder="例：Claim and Evidence" />
            </Field>
          </div>
          <Field label="標籤" hint="使用逗號分隔">
            <Input name="tags" placeholder="閱讀, 單字, 會考" />
          </Field>
          <div className="modal-actions">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={upload.isPending}>
              {upload.isPending ? "解析中…" : "上傳並解析"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export function MaterialDetailPage({ token }: { token: string }) {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["material", id],
    queryFn: () => api.material(token, id),
    enabled: Boolean(id),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteMaterial(token, id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["materials"] });
      window.location.assign("/materials");
    },
  });
  if (query.isLoading) return <LoadingState label="載入解析內容…" />;
  if (query.error || !query.data)
    return (
      <ErrorState
        message={
          query.error instanceof Error ? query.error.message : "找不到教材"
        }
        retry={() => void query.refetch()}
      />
    );
  const item = query.data;
  return (
    <div className="page-stack">
      <PageHeader
        title={item.display_name}
        description={`${item.grade || "不限年級"} · ${item.chapter || "未設定章節"} · ${item.topic || "未設定主題"}`}
        actions={
          <Button
            variant="danger"
            onClick={() => {
              if (window.confirm("確定刪除此教材與索引？")) remove.mutate();
            }}
            disabled={remove.isPending}
          >
            <Trash2 />
            刪除教材
          </Button>
        }
      />
      <div className="detail-grid">
        <Card>
          <span className="eyebrow">解析狀態</span>
          <h2>
            <StatusPill value={item.parse_status} />
          </h2>
          <dl className="detail-list">
            <div>
              <dt>MIME</dt>
              <dd>{item.media_type}</dd>
            </div>
            <div>
              <dt>檔案大小</dt>
              <dd>{Math.round(item.size_bytes / 1024)} KB</dd>
            </div>
            <div>
              <dt>內容片段</dt>
              <dd>{item.chunks.length} 段</dd>
            </div>
            <div>
              <dt>難度</dt>
              <dd>{item.difficulty}</dd>
            </div>
          </dl>
          {item.parse_error ? (
            <Notice kind="error">{item.parse_error}</Notice>
          ) : null}
        </Card>
        <Card>
          <span className="eyebrow">標籤</span>
          <h2>檢索篩選</h2>
          <div className="tag-cloud">
            {item.tags.map((tag) => (
              <span className="tag" key={tag}>
                {tag}
              </span>
            ))}
          </div>
          <p className="muted-copy">
            生成時會先依組織、年級、教材與標籤篩選，再進行語意或全文檢索。
          </p>
        </Card>
      </div>
      <Card>
        <div className="section-heading">
          <div>
            <span className="eyebrow">抽取文字</span>
            <h2>來源段落</h2>
          </div>
          <span>{item.chunks.length} 段</span>
        </div>
        <div className="chunk-list">
          {item.chunks.map((chunk) => (
            <article key={chunk.id}>
              <span>
                {chunk.page_number
                  ? `第 ${chunk.page_number} 頁`
                  : `段落 ${chunk.paragraph_number ?? chunk.sequence + 1}`}
              </span>
              <p>{chunk.text}</p>
            </article>
          ))}
        </div>
      </Card>
    </div>
  );
}
