"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  BookOpen,
  CheckCircle2,
  Clock3,
  Copy,
  Eye,
  FileWarning,
  History,
  Lock,
  LockOpen,
  RefreshCw,
  Save,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type LessonBlock, type PackageView } from "../lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
  Notice,
  PageHeader,
  StatusPill,
  Textarea,
} from "../components/ui";

export function PackagesPage({ token }: { token: string }) {
  const query = useQuery({
    queryKey: ["packages"],
    queryFn: () => api.packages(token),
  });
  if (query.isLoading) return <LoadingState label="載入教材包…" />;
  if (query.error)
    return (
      <ErrorState
        message={
          query.error instanceof Error ? query.error.message : "無法載入教材包"
        }
        retry={() => void query.refetch()}
      />
    );
  return (
    <div className="page-stack">
      <PageHeader
        title="教材包"
        description="追蹤草稿、待審核與已核准教材，並繼續編輯或預覽。"
        actions={
          <Link className="button button-primary" to="/generate">
            產生新教材
          </Link>
        }
      />
      {!query.data?.length ? (
        <EmptyState
          title="尚無教材包"
          description="完成生成精靈後，教材草稿會出現在這裡。"
        />
      ) : (
        <div className="card-grid package-grid">
          {query.data.map((item) => (
            <Link
              className="package-card"
              to={`/packages/${item.id}`}
              key={item.id}
            >
              <div className="package-card-top">
                <div className="file-avatar">
                  <BookOpen />
                </div>
                <StatusPill value={item.status} />
              </div>
              <h2>{item.title}</h2>
              <p>{item.objectives.slice(0, 2).join(" · ")}</p>
              <div className="class-meta">
                <span>
                  <Clock3 />
                  {item.total_minutes} 分鐘
                </span>
                <span>v{item.current_version}</span>
                <span>{item.lesson_date}</span>
              </div>
              {item.validation_issues.length ? (
                <div className="warning-line">
                  <FileWarning />
                  {item.validation_issues.length} 個驗證提醒
                </div>
              ) : (
                <div className="success-line">
                  <CheckCircle2 />
                  驗證通過
                </div>
              )}
              <div className="card-link">
                開啟編輯器 <ArrowRight />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function BlockEditor({
  token,
  packageId,
  block,
  index,
  count,
  onUpdated,
  onDirty,
}: {
  token: string;
  packageId: string;
  block: LessonBlock;
  index: number;
  count: number;
  onUpdated: (data: PackageView) => void;
  onDirty: (dirty: boolean) => void;
}) {
  const [draft, setDraft] = useState(block);
  const [error, setError] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setDraft(block), 0);
    return () => window.clearTimeout(timer);
  }, [block]);
  const mutation = useMutation({
    mutationFn: (operation: () => Promise<PackageView>) => operation(),
    onSuccess: (data) => {
      setError("");
      onDirty(false);
      onUpdated(data);
    },
    onError: (reason) =>
      setError(reason instanceof Error ? reason.message : "操作失敗"),
  });
  const change = <K extends keyof LessonBlock>(
    key: K,
    value: LessonBlock[K],
  ) => {
    setDraft((current) => ({ ...current, [key]: value }));
    onDirty(true);
  };
  const firstQuestion = draft.questions[0];
  const updateQuestion = (key: string, value: unknown) =>
    change(
      "questions",
      draft.questions.map((question, questionIndex) =>
        questionIndex === 0 ? { ...question, [key]: value } : question,
      ),
    );
  return (
    <article className={`editor-block ${block.locked ? "locked" : ""}`}>
      <header>
        <div className="block-index">{index + 1}</div>
        <div className="block-title">
          <Input
            value={draft.title}
            disabled={block.locked}
            onChange={(event) => change("title", event.target.value)}
            aria-label={`區塊 ${index + 1} 標題`}
          />
          <span>{draft.type}</span>
        </div>
        <label className="duration-input">
          <Clock3 />
          <Input
            type="number"
            value={draft.duration_minutes}
            disabled={block.locked}
            onChange={(event) =>
              change("duration_minutes", Number(event.target.value))
            }
            aria-label="預估分鐘"
          />
          <span>分</span>
        </label>
        <div className="block-actions">
          <button
            aria-label="上移區塊"
            disabled={index === 0 || mutation.isPending}
            onClick={() =>
              mutation.mutate(() =>
                api.moveBlock(token, packageId, block.id!, "up"),
              )
            }
          >
            <ArrowUp />
          </button>
          <button
            aria-label="下移區塊"
            disabled={index === count - 1 || mutation.isPending}
            onClick={() =>
              mutation.mutate(() =>
                api.moveBlock(token, packageId, block.id!, "down"),
              )
            }
          >
            <ArrowDown />
          </button>
          <button
            aria-label={block.locked ? "解鎖區塊" : "鎖定區塊"}
            onClick={() =>
              mutation.mutate(() =>
                api.blockAction(token, packageId, block.id!, "lock"),
              )
            }
          >
            {block.locked ? <Lock /> : <LockOpen />}
          </button>
        </div>
      </header>
      {error ? <Notice kind="error">{error}</Notice> : null}
      <div className="block-body">
        <label>
          <span>學生內容</span>
          <Textarea
            value={draft.student_content}
            onChange={(event) => change("student_content", event.target.value)}
            disabled={block.locked}
          />
        </label>
        <label>
          <span>教學說明</span>
          <Textarea
            value={draft.instructions}
            onChange={(event) => change("instructions", event.target.value)}
            disabled={block.locked}
          />
        </label>
        {firstQuestion ? (
          <div className="question-editor">
            <div className="question-label">題目 1 · {firstQuestion.type}</div>
            <label>
              <span>題目</span>
              <Textarea
                value={firstQuestion.prompt}
                onChange={(event) =>
                  updateQuestion("prompt", event.target.value)
                }
                disabled={block.locked}
              />
            </label>
            <label>
              <span>選項（每行一項）</span>
              <Textarea
                value={firstQuestion.options.join("\n")}
                onChange={(event) =>
                  updateQuestion(
                    "options",
                    event.target.value.split("\n").filter(Boolean),
                  )
                }
                disabled={block.locked}
              />
            </label>
            <div className="form-grid">
              <label>
                <span>答案</span>
                <Input
                  value={firstQuestion.answer}
                  onChange={(event) =>
                    updateQuestion("answer", event.target.value)
                  }
                  disabled={block.locked}
                />
              </label>
              <label>
                <span>解析</span>
                <Input
                  value={firstQuestion.explanation}
                  onChange={(event) =>
                    updateQuestion("explanation", event.target.value)
                  }
                  disabled={block.locked}
                />
              </label>
            </div>
          </div>
        ) : null}
        <label>
          <span>教師備註</span>
          <Textarea
            value={draft.teacher_notes}
            onChange={(event) => change("teacher_notes", event.target.value)}
            disabled={block.locked}
          />
        </label>
        {draft.source_references.length ? (
          <div className="source-list">
            <strong>來源引用</strong>
            {draft.source_references.map((source) => (
              <span key={source.chunk_id}>
                {source.material_name} ·{" "}
                {source.page_number
                  ? `第 ${source.page_number} 頁`
                  : `段落 ${source.paragraph_number}`}
              </span>
            ))}
          </div>
        ) : (
          <div className="warning-line">
            <FileWarning />
            此區塊沒有來源引用
          </div>
        )}
      </div>
      <footer>
        <div className="button-row">
          <Button
            variant="secondary"
            disabled={block.locked || mutation.isPending}
            onClick={() =>
              mutation.mutate(() =>
                api.blockAction(token, packageId, block.id!, "regenerate"),
              )
            }
          >
            <RefreshCw />
            單獨重生
          </Button>
          <Button
            variant="ghost"
            disabled={mutation.isPending}
            onClick={() =>
              mutation.mutate(() =>
                api.blockAction(token, packageId, block.id!, "copy"),
              )
            }
          >
            <Copy />
            複製
          </Button>
          <Button
            variant="ghost"
            disabled={mutation.isPending}
            onClick={() => {
              if (window.confirm("確定刪除此區塊？"))
                mutation.mutate(() =>
                  api.deleteBlock(token, packageId, block.id!),
                );
            }}
          >
            <Trash2 />
            刪除
          </Button>
        </div>
        <Button
          disabled={block.locked || mutation.isPending}
          onClick={() =>
            mutation.mutate(() =>
              api.updateBlock(token, packageId, block.id!, {
                title: draft.title,
                duration_minutes: draft.duration_minutes,
                instructions: draft.instructions,
                student_content: draft.student_content,
                teacher_notes: draft.teacher_notes,
                questions: draft.questions,
              }),
            )
          }
        >
          <Save />
          儲存區塊
        </Button>
      </footer>
    </article>
  );
}

export function EditorPage({ token }: { token: string }) {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState("");
  const query = useQuery({
    queryKey: ["package", id],
    queryFn: () => api.package(token, id),
    enabled: Boolean(id),
  });
  const versions = useQuery({
    queryKey: ["versions", id],
    queryFn: () => api.versions(token, id),
    enabled: Boolean(id),
  });
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
  const update = (data: PackageView) => {
    queryClient.setQueryData(["package", id], data);
    void queryClient.invalidateQueries({ queryKey: ["packages"] });
    void queryClient.invalidateQueries({ queryKey: ["versions", id] });
    setMessage("變更已儲存並建立新版本。 ");
  };
  const approve = useMutation({
    mutationFn: () => api.approve(token, id),
    onSuccess: update,
    onError: (reason) =>
      setMessage(reason instanceof Error ? reason.message : "無法核准"),
  });
  const submitReview = useMutation({
    mutationFn: () => api.submitReview(token, id),
    onSuccess: update,
    onError: (reason) =>
      setMessage(reason instanceof Error ? reason.message : "無法送審"),
  });
  const restore = useMutation({
    mutationFn: (versionId: string) => api.restore(token, id, versionId),
    onSuccess: update,
    onError: (reason) =>
      setMessage(reason instanceof Error ? reason.message : "無法還原"),
  });
  if (query.isLoading) return <LoadingState label="載入結構化編輯器…" />;
  if (query.error || !query.data)
    return (
      <ErrorState
        message={
          query.error instanceof Error ? query.error.message : "找不到教材包"
        }
        retry={() => void query.refetch()}
      />
    );
  const item = query.data;
  const fatal = item.validation_issues.filter(
    (issue) => issue.severity === "fatal",
  ).length;
  return (
    <div className="page-stack editor-page">
      <PageHeader
        title={item.title}
        description={`${item.lesson_date} · v${item.current_version}`}
        actions={
          <>
            <StatusPill value={item.status} />
            <Button
              variant="secondary"
              onClick={() => navigate(`/packages/${id}/preview`)}
            >
              <Eye />
              預覽
            </Button>
            {item.status === "draft" ? (
              <Button
                variant="secondary"
                onClick={() => submitReview.mutate()}
                disabled={Boolean(fatal) || submitReview.isPending}
              >
                <History />
                送交審核
              </Button>
            ) : null}
            <Button
              onClick={() => approve.mutate()}
              disabled={
                Boolean(fatal) ||
                item.status === "approved" ||
                approve.isPending
              }
            >
              <CheckCircle2 />
              {item.status === "approved" ? "已核准" : "核准教材"}
            </Button>
          </>
        }
      />
      {dirty ? (
        <Notice kind="error">尚有未儲存的區塊修改，離開頁面前請先儲存。</Notice>
      ) : null}
      {message ? (
        <Notice kind={message.includes("已儲存") ? "success" : "error"}>
          {message}
        </Notice>
      ) : null}
      <div className="editor-summary">
        <div>
          <Clock3 />
          <span>區塊合計</span>
          <strong>
            {item.blocks.reduce(
              (sum, block) => sum + block.duration_minutes,
              0,
            )}{" "}
            / {item.total_minutes} 分鐘
          </strong>
        </div>
        <div>
          <Lock />
          <span>已鎖定</span>
          <strong>
            {item.blocks.filter((block) => block.locked).length} /{" "}
            {item.blocks.length}
          </strong>
        </div>
        <div className={fatal ? "danger" : "success"}>
          <FileWarning />
          <span>驗證問題</span>
          <strong>
            {fatal} fatal · {item.validation_issues.length} total
          </strong>
        </div>
      </div>
      {item.validation_issues.length ? (
        <Card className="issues-card">
          <h2>驗證提醒</h2>
          {item.validation_issues.map((issue, index) => (
            <div
              key={`${issue.code}-${index}`}
              className={`issue ${issue.severity}`}
            >
              <FileWarning />
              <div>
                <strong>{issue.message}</strong>
                <span>{issue.code}</span>
              </div>
            </div>
          ))}
        </Card>
      ) : null}
      <div className="editor-layout">
        <div className="blocks-column">
          {item.blocks.map((block, index) => (
            <BlockEditor
              key={block.id}
              token={token}
              packageId={id}
              block={block}
              index={index}
              count={item.blocks.length}
              onUpdated={update}
              onDirty={setDirty}
            />
          ))}
        </div>
        <aside className="history-panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">版本歷史</span>
              <h2>
                <History />
                變更紀錄
              </h2>
            </div>
          </div>
          {versions.isLoading ? (
            <LoadingState label="載入版本…" />
          ) : (
            versions.data?.map((version) => (
              <button
                key={version.id}
                onClick={() => {
                  if (
                    window.confirm(
                      `還原至 v${version.version_number}？目前內容會先備份。`,
                    )
                  )
                    restore.mutate(version.id);
                }}
              >
                <span>v{version.version_number}</span>
                <div>
                  <strong>{version.change_summary}</strong>
                  <small>
                    {new Date(version.created_at).toLocaleString("zh-TW")}
                  </small>
                </div>
              </button>
            ))
          )}
        </aside>
      </div>
    </div>
  );
}
