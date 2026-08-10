"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { BookCheck, FileOutput, LockKeyhole, Sparkles } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api } from "../lib/api";
import { Button, Field, Input, Notice } from "../components/ui";

const schema = z.object({
  email: z.email("請輸入有效 Email"),
  password: z.string().min(8, "密碼至少 8 個字元"),
});
type LoginValues = z.infer<typeof schema>;

export function LoginPage({ onLogin }: { onLogin: (token: string) => void }) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: "owner@demo.lessonforge.tw",
      password: "LessonForgeDemo!2026",
    },
  });
  const submit = handleSubmit(async (values) => {
    try {
      const result = await api.login(values.email, values.password);
      onLogin(result.access_token);
    } catch (error) {
      setError("root", {
        message: error instanceof Error ? error.message : "登入失敗",
      });
    }
  });
  return (
    <main className="login-page">
      <section className="login-story">
        <div className="login-brand">
          <div className="brand-mark large">
            <Sparkles />
          </div>
          <span>LessonForge TW</span>
        </div>
        <div>
          <span className="eyebrow light">補習班 AI 教材工作台</span>
          <h1>把班級脈絡與自有教材，鍛造成下一堂完整課程。</h1>
          <p>
            從課堂內容、每日作業到週考與家長回報，在同一處生成、修改、核准與輸出。
          </p>
        </div>
        <div className="feature-list">
          <div>
            <BookCheck />
            <span>
              <strong>依班級弱點生成</strong>記住已學內容與常見錯誤
            </span>
          </div>
          <div>
            <LockKeyhole />
            <span>
              <strong>老師掌握最後決定</strong>區塊可鎖定、重生與版本還原
            </span>
          </div>
          <div>
            <FileOutput />
            <span>
              <strong>直接印成教材</strong>學生、教師、作業與週考分版輸出
            </span>
          </div>
        </div>
      </section>
      <section className="login-panel" aria-labelledby="login-title">
        <form className="login-card" onSubmit={submit} noValidate>
          <div>
            <span className="eyebrow">本機 Demo</span>
            <h2 id="login-title">登入工作台</h2>
            <p>帳號已預先填入，無需外部身分服務或付費 API。</p>
          </div>
          {errors.root?.message ? (
            <Notice kind="error">{errors.root.message}</Notice>
          ) : null}
          <Field label="Email" error={errors.email?.message}>
            <Input
              type="email"
              autoComplete="username"
              {...register("email")}
            />
          </Field>
          <Field label="密碼" error={errors.password?.message}>
            <Input
              type="password"
              autoComplete="current-password"
              {...register("password")}
            />
          </Field>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "登入中…" : "進入 LessonForge"}
          </Button>
          <div className="demo-accounts">
            <strong>Demo 帳號</strong>
            <span>Owner：owner@demo.lessonforge.tw</span>
            <span>Teacher：teacher@demo.lessonforge.tw</span>
            <span>密碼：LessonForgeDemo!2026</span>
          </div>
        </form>
      </section>
    </main>
  );
}
