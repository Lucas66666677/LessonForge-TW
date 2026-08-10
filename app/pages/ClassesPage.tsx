"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarDays,
  CirclePlus,
  GraduationCap,
  Target,
  UserPlus,
  Users,
} from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";
import { api, type ClassCreate, type StudentCreate } from "../lib/api";
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
  Textarea,
} from "../components/ui";

const classSchema = z.object({
  name: z.string().min(2, "請輸入至少 2 個字元"),
  grade: z.enum(["國一", "國二", "國三", "高一", "高二", "高三"]),
  material_name: z.string().min(1, "請輸入教材名稱"),
  weekly_schedule: z.string().min(1, "請輸入上課時間"),
  objectivesText: z.string().min(2, "請至少輸入一個目標"),
  overall_level: z.string().min(1),
  learned_content: z.string(),
  commonErrorsText: z.string(),
  teaching_preferences: z.string(),
  homework_days: z.coerce.number().min(1).max(7),
  homework_minutes: z.coerce.number().min(10).max(120),
  notes: z.string(),
});
type ClassForm = z.infer<typeof classSchema>;

export function ClassesPage({ token }: { token: string }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["classes"],
    queryFn: () => api.classes(token),
  });
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<z.input<typeof classSchema>, unknown, ClassForm>({
    resolver: zodResolver(classSchema),
    defaultValues: {
      grade: "國三",
      material_name: "自訂教材",
      weekly_schedule: "週三 19:00–21:00",
      objectivesText: "提升閱讀理解\n強化核心單字",
      overall_level: "中等",
      learned_content: "",
      commonErrorsText: "",
      teaching_preferences: "先示範再練習",
      homework_days: 4,
      homework_minutes: 30,
      notes: "",
    },
  });
  const mutation = useMutation({
    mutationFn: (payload: ClassCreate) => api.createClass(token, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["classes"] });
      setOpen(false);
      reset();
    },
    onError: (error) =>
      setError("root", {
        message: error instanceof Error ? error.message : "建立失敗",
      }),
  });
  const submit = handleSubmit((values) =>
    mutation.mutate({
      name: values.name,
      grade: values.grade,
      material_name: values.material_name,
      weekly_schedule: values.weekly_schedule,
      objectives: values.objectivesText
        .split(/\n|,/)
        .map((item) => item.trim())
        .filter(Boolean),
      overall_level: values.overall_level,
      learned_content: values.learned_content,
      common_errors: values.commonErrorsText
        .split(/\n|,/)
        .map((item) => item.trim())
        .filter(Boolean),
      teaching_preferences: values.teaching_preferences,
      homework_days: values.homework_days,
      homework_minutes: values.homework_minutes,
      notes: values.notes,
      students: [],
    }),
  );
  return (
    <div className="page-stack">
      <PageHeader
        title="班級"
        description="保存程度、弱點、進度與教學偏好，讓下一次生成延續班級脈絡。"
        actions={
          <Button onClick={() => setOpen(true)}>
            <CirclePlus />
            建立班級
          </Button>
        }
      />
      {query.isLoading ? (
        <LoadingState label="載入班級…" />
      ) : query.error ? (
        <ErrorState
          message={
            query.error instanceof Error ? query.error.message : "無法載入班級"
          }
          retry={() => void query.refetch()}
        />
      ) : !query.data?.length ? (
        <EmptyState
          title="還沒有班級"
          description="建立班級後即可上傳教材並產生第一份課程。"
          action={<Button onClick={() => setOpen(true)}>建立班級</Button>}
        />
      ) : (
        <div className="card-grid">
          {query.data.map((item) => (
            <Link
              className="class-card"
              to={`/classes/${item.id}`}
              key={item.id}
            >
              <div className="class-card-top">
                <div className="class-icon">
                  <GraduationCap />
                </div>
                <span className="grade-chip">{item.grade}</span>
              </div>
              <h2>{item.name}</h2>
              <p>{item.material_name}</p>
              <div className="class-meta">
                <span>
                  <Users />
                  {item.students.length} 位學生
                </span>
                <span>
                  <CalendarDays />
                  {item.weekly_schedule || "未設定"}
                </span>
              </div>
              <div className="class-goals">
                <Target />
                {item.objectives.slice(0, 2).join(" · ") || "尚未設定目標"}
              </div>
              <div className="card-link">
                查看班級脈絡 <ArrowRight />
              </div>
            </Link>
          ))}
        </div>
      )}
      <Modal
        open={open}
        onOpenChange={setOpen}
        title="建立班級"
        description="先填入可用資訊，之後仍可在班級詳情調整。"
      >
        <form className="modal-form" onSubmit={submit}>
          {errors.root?.message ? (
            <Notice kind="error">{errors.root.message}</Notice>
          ) : null}
          <div className="form-grid">
            <Field label="班級名稱" error={errors.name?.message}>
              <Input
                {...register("name")}
                placeholder="例：國三會考英文 A 班"
              />
            </Field>
            <Field label="年級" error={errors.grade?.message}>
              <select className="input" {...register("grade")}>
                <option>國一</option>
                <option>國二</option>
                <option>國三</option>
                <option>高一</option>
                <option>高二</option>
                <option>高三</option>
              </select>
            </Field>
            <Field label="教材版本／名稱">
              <Input {...register("material_name")} />
            </Field>
            <Field label="每週上課時間">
              <Input {...register("weekly_schedule")} />
            </Field>
            <Field label="整體程度">
              <Input {...register("overall_level")} />
            </Field>
            <Field label="作業天數">
              <Input type="number" {...register("homework_days")} />
            </Field>
            <Field label="每日作業分鐘">
              <Input type="number" {...register("homework_minutes")} />
            </Field>
          </div>
          <Field label="學習目標" hint="每行一個目標">
            <Textarea {...register("objectivesText")} />
          </Field>
          <Field label="已學內容">
            <Textarea {...register("learned_content")} />
          </Field>
          <Field label="常見錯誤" hint="每行一項">
            <Textarea {...register("commonErrorsText")} />
          </Field>
          <Field label="教學偏好">
            <Textarea {...register("teaching_preferences")} />
          </Field>
          <Field label="備註">
            <Textarea {...register("notes")} />
          </Field>
          <div className="modal-actions">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "建立中…" : "建立班級"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

export function ClassDetailPage({ token }: { token: string }) {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [studentOpen, setStudentOpen] = useState(false);
  const [studentAlias, setStudentAlias] = useState("");
  const [studentWeaknesses, setStudentWeaknesses] = useState<string[]>([]);
  const [studentNotes, setStudentNotes] = useState("");
  const [studentError, setStudentError] = useState("");
  const query = useQuery({
    queryKey: ["class", id],
    queryFn: () => api.class(token, id),
    enabled: Boolean(id),
  });
  const createStudent = useMutation({
    mutationFn: (payload: StudentCreate) =>
      api.createStudent(token, id, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["class", id] });
      setStudentOpen(false);
      setStudentAlias("");
      setStudentWeaknesses([]);
      setStudentNotes("");
    },
    onError: (error) =>
      setStudentError(error instanceof Error ? error.message : "無法新增學生"),
  });
  if (query.isLoading) return <LoadingState label="載入班級脈絡…" />;
  if (query.error || !query.data)
    return (
      <ErrorState
        message={
          query.error instanceof Error ? query.error.message : "找不到班級"
        }
        retry={() => void query.refetch()}
      />
    );
  const item = query.data;
  return (
    <div className="page-stack">
      <PageHeader
        title={item.name}
        description={`${item.grade} · ${item.material_name}`}
        actions={
          <div className="button-row">
            <Button variant="secondary" onClick={() => setStudentOpen(true)}>
              <UserPlus />
              新增匿名學生
            </Button>
            <Link
              className="button button-primary"
              to={`/generate?class=${item.id}`}
            >
              為此班產生教材
            </Link>
          </div>
        }
      />
      <div className="detail-grid">
        <Card>
          <span className="eyebrow">班級設定</span>
          <h2>教學脈絡</h2>
          <dl className="detail-list">
            <div>
              <dt>每週上課</dt>
              <dd>{item.weekly_schedule || "未設定"}</dd>
            </div>
            <div>
              <dt>整體程度</dt>
              <dd>{item.overall_level}</dd>
            </div>
            <div>
              <dt>作業安排</dt>
              <dd>
                每週 {item.homework_days} 天，每天 {item.homework_minutes} 分鐘
              </dd>
            </div>
            <div>
              <dt>已學內容</dt>
              <dd>{item.learned_content || "尚未記錄"}</dd>
            </div>
            <div>
              <dt>教學偏好</dt>
              <dd>{item.teaching_preferences || "尚未記錄"}</dd>
            </div>
          </dl>
        </Card>
        <Card>
          <span className="eyebrow">學習焦點</span>
          <h2>目標與常見錯誤</h2>
          <div className="tag-cloud">
            {item.objectives.map((goal) => (
              <span className="tag" key={goal}>
                {goal}
              </span>
            ))}
          </div>
          <h3>常見錯誤</h3>
          <ul className="plain-list">
            {item.common_errors.length ? (
              item.common_errors.map((error) => <li key={error}>{error}</li>)
            ) : (
              <li>尚未記錄</li>
            )}
          </ul>
        </Card>
      </div>
      <Card>
        <div className="section-heading">
          <div>
            <span className="eyebrow">匿名資料</span>
            <h2>學生弱點</h2>
          </div>
          <span>{item.students.length} 位</span>
        </div>
        <div className="student-grid">
          {item.students.map((student) => (
            <article className="student-card" key={student.id}>
              <div className="user-avatar">{student.alias.slice(-1)}</div>
              <div>
                <strong>{student.alias}</strong>
                <div className="tag-cloud compact">
                  {student.weaknesses.map((weakness) => (
                    <span className="tag warm" key={weakness}>
                      {weakness}
                    </span>
                  ))}
                </div>
                <p>{student.notes || "無備註"}</p>
              </div>
            </article>
          ))}
        </div>
      </Card>
      <Modal
        open={studentOpen}
        onOpenChange={setStudentOpen}
        title="新增匿名學生"
        description="使用代號或暱稱即可，不需要輸入真實姓名。"
      >
        <form
          className="modal-form"
          onSubmit={(event) => {
            event.preventDefault();
            setStudentError("");
            if (!studentAlias.trim()) {
              setStudentError("請輸入學生代號或暱稱");
              return;
            }
            createStudent.mutate({
              alias: studentAlias,
              weaknesses: studentWeaknesses,
              notes: studentNotes,
            });
          }}
        >
          {studentError ? <Notice kind="error">{studentError}</Notice> : null}
          <Field label="學生代號或暱稱">
            <Input
              value={studentAlias}
              onChange={(event) => setStudentAlias(event.target.value)}
              placeholder="例：學生 C"
            />
          </Field>
          <fieldset className="checkbox-list">
            <legend>主要弱點（可複選）</legend>
            {[
              "單字",
              "文法",
              "克漏字",
              "閱讀理解",
              "翻譯",
              "寫作",
              "長句解析",
            ].map((weakness) => (
              <label key={weakness} htmlFor={`weakness-${weakness}`}>
                <input
                  id={`weakness-${weakness}`}
                  type="checkbox"
                  checked={studentWeaknesses.includes(weakness)}
                  onChange={(event) =>
                    setStudentWeaknesses((current) =>
                      event.target.checked
                        ? [...current, weakness]
                        : current.filter((item) => item !== weakness),
                    )
                  }
                />
                <span>{weakness}</span>
              </label>
            ))}
          </fieldset>
          <Field label="備註">
            <Textarea
              value={studentNotes}
              onChange={(event) => setStudentNotes(event.target.value)}
              placeholder="記錄可幫助教學的觀察，避免個資。"
            />
          </Field>
          <div className="modal-actions">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setStudentOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={createStudent.isPending}>
              {createStudent.isPending ? "新增中…" : "新增學生"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
