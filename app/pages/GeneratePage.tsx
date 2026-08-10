"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Check,
  CircleAlert,
  Clock3,
  GripVertical,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, type GenerationRequest } from "../lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingState,
  Notice,
  PageHeader,
  ProgressBar,
  Textarea,
} from "../components/ui";

const defaultModules = [
  "作業與錯題檢查",
  "快速單字回想",
  "引導式克漏字",
  "獨立克漏字",
  "閱讀理解",
  "綜合挑戰",
  "長句拆解",
  "錯題訂正與總結",
];

export function GeneratePage({ token }: { token: string }) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const classes = useQuery({
    queryKey: ["classes"],
    queryFn: () => api.classes(token),
  });
  const materials = useQuery({
    queryKey: ["materials"],
    queryFn: () => api.materials(token),
  });
  const [step, setStep] = useState(1);
  const [error, setError] = useState("");
  const [classId, setClassId] = useState(params.get("class") ?? "");
  const [materialIds, setMaterialIds] = useState<string[]>([]);
  const [date, setDate] = useState("2026-08-12");
  const [minutes, setMinutes] = useState(120);
  const [objectives, setObjectives] = useState(
    "辨認文章主張與證據\n使用上下文理解核心單字",
  );
  const [basic, setBasic] = useState(40);
  const [medium, setMedium] = useState(40);
  const [advanced, setAdvanced] = useState(20);
  const [homeworkDays, setHomeworkDays] = useState(4);
  const [quiz, setQuiz] = useState(true);
  const [report, setReport] = useState(true);
  const [instructions, setInstructions] = useState("");
  const [modules, setModules] = useState(defaultModules);
  const selectedClass = classes.data?.find((item) => item.id === classId);
  const selectedMaterials =
    materials.data?.filter((item) => materialIds.includes(item.id)) ?? [];
  const mutation = useMutation({
    mutationFn: (payload: GenerationRequest) =>
      api.createGeneration(token, payload),
    onSuccess: (run) => navigate(`/generation/${run.id}`),
    onError: (reason) =>
      setError(reason instanceof Error ? reason.message : "無法建立生成任務"),
  });
  const moveModule = (index: number, offset: number) =>
    setModules((current) => {
      const next = [...current];
      const destination = index + offset;
      if (destination < 0 || destination >= next.length) return current;
      [next[index], next[destination]] = [next[destination], next[index]];
      return next;
    });
  const canContinue = useMemo(
    () =>
      step === 1
        ? Boolean(classId && materialIds.length)
        : step === 2
          ? Boolean(date && minutes >= 30 && objectives.trim())
          : step === 3
            ? basic + medium + advanced === 100 && modules.length > 0
            : true,
    [
      advanced,
      basic,
      classId,
      date,
      materialIds.length,
      medium,
      minutes,
      modules.length,
      objectives,
      step,
    ],
  );
  const submit = () =>
    mutation.mutate({
      class_id: classId,
      material_ids: materialIds,
      lesson_date: date,
      lesson_minutes: minutes,
      objectives: objectives
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
      difficulty_ratio: { 基礎: basic, 中等: medium, 進階: advanced },
      question_types: { vocabulary: 8, cloze: 6, reading: 4 },
      homework_days: homeworkDays,
      include_weekly_quiz: quiz,
      include_parent_report: report,
      teacher_instructions: instructions,
      modules,
    });
  if (classes.isLoading || materials.isLoading)
    return <LoadingState label="準備生成精靈…" />;
  if (classes.error || materials.error)
    return <ErrorState message="無法載入班級或教材" />;
  if (
    !classes.data?.length ||
    !materials.data?.some((item) => item.parse_status === "ready")
  )
    return (
      <EmptyState
        title="生成前還需要一些資料"
        description="至少需要一個班級與一份解析完成的教材。"
        action={
          <div className="button-row">
            <Button variant="secondary" onClick={() => navigate("/classes")}>
              建立班級
            </Button>
            <Button onClick={() => navigate("/materials")}>上傳教材</Button>
          </div>
        }
      />
    );
  return (
    <div className="page-stack">
      <PageHeader
        title="產生教材包"
        description="四個步驟設定班級、課程結構與輸出需求；生成會在背景執行。"
      />
      <div className="wizard-steps" aria-label="生成步驟">
        {["班級與教材", "課程設定", "結構與難度", "確認生成"].map(
          (label, index) => (
            <div key={label} className={index + 1 <= step ? "active" : ""}>
              <span>{index + 1 < step ? <Check /> : index + 1}</span>
              <strong>{label}</strong>
            </div>
          ),
        )}
      </div>
      {error ? <Notice kind="error">{error}</Notice> : null}
      <Card className="wizard-card">
        {step === 1 ? (
          <div className="wizard-content">
            <div>
              <span className="eyebrow">Step 1</span>
              <h2>選擇班級與教材</h2>
              <p>檢索只會使用目前組織與本次選取的教材。</p>
            </div>
            <Field label="班級">
              <select
                className="input"
                value={classId}
                onChange={(event) => setClassId(event.target.value)}
              >
                <option value="">請選擇班級</option>
                {classes.data.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · {item.grade}
                  </option>
                ))}
              </select>
            </Field>
            {selectedClass ? (
              <div className="context-preview">
                <strong>{selectedClass.name}</strong>
                <span>
                  {selectedClass.overall_level} ·{" "}
                  {selectedClass.students.length} 位學生
                </span>
                <p>
                  常見錯誤：{selectedClass.common_errors.join("、") || "未設定"}
                </p>
              </div>
            ) : null}
            <fieldset className="checkbox-list">
              <legend>教材（可複選）</legend>
              {materials.data
                .filter((item) => item.parse_status === "ready")
                .map((item) => (
                  <label key={item.id} htmlFor={`material-${item.id}`}>
                    <input
                      id={`material-${item.id}`}
                      aria-label={`選擇教材 ${item.display_name}`}
                      type="checkbox"
                      checked={materialIds.includes(item.id)}
                      onChange={(event) =>
                        setMaterialIds((current) =>
                          event.target.checked
                            ? [...current, item.id]
                            : current.filter((id) => id !== item.id),
                        )
                      }
                    />
                    <span>
                      <strong>{item.display_name}</strong>
                      <small>
                        {item.grade || "不限年級"} ·{" "}
                        {item.chapter || "未設定章節"}
                      </small>
                    </span>
                  </label>
                ))}
            </fieldset>
          </div>
        ) : null}
        {step === 2 ? (
          <div className="wizard-content">
            <div>
              <span className="eyebrow">Step 2</span>
              <h2>設定本次課程</h2>
              <p>預設為 120 分鐘，可依實際課表調整。</p>
            </div>
            <div className="form-grid">
              <Field label="課程日期">
                <Input
                  type="date"
                  value={date}
                  onChange={(event) => setDate(event.target.value)}
                />
              </Field>
              <Field label="課堂分鐘數">
                <Input
                  type="number"
                  min={30}
                  max={360}
                  value={minutes}
                  onChange={(event) => setMinutes(Number(event.target.value))}
                />
              </Field>
              <Field label="作業天數">
                <Input
                  type="number"
                  min={1}
                  max={7}
                  value={homeworkDays}
                  onChange={(event) =>
                    setHomeworkDays(Number(event.target.value))
                  }
                />
              </Field>
            </div>
            <Field label="本次學習目標" hint="每行一個目標">
              <Textarea
                value={objectives}
                onChange={(event) => setObjectives(event.target.value)}
              />
            </Field>
            <Field label="額外教師指示">
              <Textarea
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                placeholder="例：增加拼字辨識，閱讀題先示範定位線索。"
              />
            </Field>
            <div className="toggle-row">
              <label>
                <input
                  type="checkbox"
                  checked={quiz}
                  onChange={(event) => setQuiz(event.target.checked)}
                />
                <span>產出週考</span>
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={report}
                  onChange={(event) => setReport(event.target.checked)}
                />
                <span>產出家長回報</span>
              </label>
            </div>
          </div>
        ) : null}
        {step === 3 ? (
          <div className="wizard-content">
            <div>
              <span className="eyebrow">Step 3</span>
              <h2>調整難度與課程結構</h2>
              <p>可取消、增加或用按鈕重新排序模組。</p>
            </div>
            <div className="ratio-grid">
              <Field label="基礎 %">
                <Input
                  type="number"
                  value={basic}
                  onChange={(event) => setBasic(Number(event.target.value))}
                />
              </Field>
              <Field label="中等 %">
                <Input
                  type="number"
                  value={medium}
                  onChange={(event) => setMedium(Number(event.target.value))}
                />
              </Field>
              <Field label="進階 %">
                <Input
                  type="number"
                  value={advanced}
                  onChange={(event) => setAdvanced(Number(event.target.value))}
                />
              </Field>
            </div>
            {basic + medium + advanced !== 100 ? (
              <Notice kind="error">
                <CircleAlert />
                難度比例總和必須為 100%。
              </Notice>
            ) : null}
            <div className="module-list">
              {modules.map((module, index) => (
                <div key={`${module}-${index}`}>
                  <GripVertical aria-hidden="true" />
                  <span>{index + 1}</span>
                  <Input
                    aria-label={`模組 ${index + 1} 名稱`}
                    value={module}
                    onChange={(event) =>
                      setModules((current) =>
                        current.map((item, itemIndex) =>
                          itemIndex === index ? event.target.value : item,
                        ),
                      )
                    }
                  />
                  <button
                    aria-label="上移"
                    onClick={() => moveModule(index, -1)}
                    disabled={index === 0}
                  >
                    <ArrowUp />
                  </button>
                  <button
                    aria-label="下移"
                    onClick={() => moveModule(index, 1)}
                    disabled={index === modules.length - 1}
                  >
                    <ArrowDown />
                  </button>
                  <button
                    className="remove-module"
                    onClick={() =>
                      setModules((current) =>
                        current.filter((_, itemIndex) => itemIndex !== index),
                      )
                    }
                  >
                    移除
                  </button>
                </div>
              ))}
            </div>
            <Button
              variant="secondary"
              onClick={() =>
                setModules((current) => [...current, "新增教學模組"])
              }
            >
              <CircleAlert />
              增加模組
            </Button>
          </div>
        ) : null}
        {step === 4 ? (
          <div className="wizard-content">
            <div>
              <span className="eyebrow">Step 4</span>
              <h2>確認後開始背景生成</h2>
              <p>AI 產出一律為草稿；完成後仍需老師檢查與核准。</p>
            </div>
            <div className="summary-grid">
              <div>
                <span>班級</span>
                <strong>{selectedClass?.name}</strong>
              </div>
              <div>
                <span>教材</span>
                <strong>
                  {selectedMaterials
                    .map((item) => item.display_name)
                    .join("、")}
                </strong>
              </div>
              <div>
                <span>日期與時間</span>
                <strong>
                  {date} · {minutes} 分鐘
                </strong>
              </div>
              <div>
                <span>難度</span>
                <strong>
                  基礎 {basic}% · 中等 {medium}% · 進階 {advanced}%
                </strong>
              </div>
              <div>
                <span>教材模組</span>
                <strong>{modules.length} 個</strong>
              </div>
              <div>
                <span>附加內容</span>
                <strong>
                  {quiz ? "週考" : "不含週考"} ·{" "}
                  {report ? "家長回報" : "不含回報"}
                </strong>
              </div>
            </div>
            <Notice>
              <Sparkles />
              使用 Mock Provider 時會產出固定且符合 schema 的完整教材；切換
              Ollama 後會使用本機模型。
            </Notice>
          </div>
        ) : null}
        <div className="wizard-actions">
          <Button
            variant="ghost"
            disabled={step === 1 || mutation.isPending}
            onClick={() => setStep((current) => current - 1)}
          >
            <ArrowLeft />
            上一步
          </Button>
          {step < 4 ? (
            <Button
              disabled={!canContinue}
              onClick={() => setStep((current) => current + 1)}
            >
              下一步
              <ArrowRight />
            </Button>
          ) : (
            <Button disabled={mutation.isPending} onClick={submit}>
              <Sparkles />
              {mutation.isPending ? "建立任務中…" : "開始產生教材"}
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}

export function GenerationProgressPage({ token }: { token: string }) {
  const navigate = useNavigate();
  const { id = "" } = useParams();
  const query = useQuery({
    queryKey: ["generation", id],
    queryFn: () => api.generation(token, id),
    enabled: Boolean(id),
    refetchInterval: (state) =>
      ["completed", "failed"].includes(state.state.data?.status ?? "")
        ? false
        : 800,
  });
  const retry = useMutation({
    mutationFn: () => api.retryGeneration(token, id),
    onSuccess: () => void query.refetch(),
  });
  if (query.isLoading) return <LoadingState label="連線至生成工作…" />;
  if (query.error || !query.data)
    return (
      <ErrorState
        message={
          query.error instanceof Error ? query.error.message : "找不到生成工作"
        }
        retry={() => void query.refetch()}
      />
    );
  const run = query.data;
  const stages = [
    "等待中",
    "整理班級與生成設定",
    "檢索教材",
    "規劃課程",
    "生成教學區塊",
    "生成每日作業",
    "生成週考",
    "生成家長回報",
    "驗證教材內容",
    "完成",
  ];
  return (
    <div className="centered-page">
      <Card className="generation-card">
        <div className={`generation-orb ${run.status}`}>
          <Sparkles />
        </div>
        <span className="eyebrow">背景生成任務</span>
        <h1>
          {run.status === "completed"
            ? "教材包已產生"
            : run.status === "failed"
              ? "生成未完成"
              : "正在鍛造下一堂課"}
        </h1>
        <p>{run.progress_message}</p>
        <ProgressBar value={run.progress} label={run.progress_message} />
        <div className="stage-list">
          {stages.map((stage, index) => {
            const threshold = index * 11;
            return (
              <div
                key={stage}
                className={
                  run.progress >= threshold
                    ? "done"
                    : run.progress_message === stage
                      ? "current"
                      : ""
                }
              >
                <span>{run.progress >= threshold ? <Check /> : index + 1}</span>
                {stage}
              </div>
            );
          })}
        </div>
        {run.status === "failed" ? (
          <>
            <Notice kind="error">
              {run.failure_reason ?? "生成失敗，請檢查系統設定後重試。"}
            </Notice>
            <Button onClick={() => retry.mutate()} disabled={retry.isPending}>
              {retry.isPending ? "重試中…" : "重新執行"}
            </Button>
          </>
        ) : run.status === "completed" && run.lesson_package_id ? (
          <Button
            onClick={() => navigate(`/packages/${run.lesson_package_id}`)}
          >
            開啟教材編輯器 <ArrowRight />
          </Button>
        ) : (
          <p className="muted-copy">
            <Clock3 />
            可以離開此頁；工作會在背景繼續執行。
          </p>
        )}
      </Card>
    </div>
  );
}
