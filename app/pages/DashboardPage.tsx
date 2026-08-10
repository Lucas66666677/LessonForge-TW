"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  CircleCheckBig,
  Clock3,
  GraduationCap,
  Library,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import {
  Card,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusPill,
} from "../components/ui";

export function DashboardPage({ token }: { token: string }) {
  const classes = useQuery({
    queryKey: ["classes"],
    queryFn: () => api.classes(token),
  });
  const materials = useQuery({
    queryKey: ["materials"],
    queryFn: () => api.materials(token),
  });
  const packages = useQuery({
    queryKey: ["packages"],
    queryFn: () => api.packages(token),
  });
  if (classes.isLoading || materials.isLoading || packages.isLoading)
    return <LoadingState label="整理今日工作台…" />;
  const error = classes.error || materials.error || packages.error;
  if (error)
    return (
      <ErrorState
        message={error instanceof Error ? error.message : "無法載入儀表板"}
        retry={() =>
          void Promise.all([
            classes.refetch(),
            materials.refetch(),
            packages.refetch(),
          ])
        }
      />
    );
  const approved =
    packages.data?.filter((item) => item.status === "approved").length ?? 0;
  const issues =
    packages.data?.reduce(
      (sum, item) =>
        sum +
        item.validation_issues.filter((issue) => issue.severity === "fatal")
          .length,
      0,
    ) ?? 0;
  const recent = packages.data?.slice(0, 4) ?? [];
  return (
    <div className="page-stack">
      <PageHeader
        title="今天要準備哪一堂課？"
        description="班級脈絡、教材、生成與核准進度都集中在這裡。"
        actions={
          <Link className="button button-primary" to="/generate">
            <Sparkles />
            產生新教材
          </Link>
        }
      />
      <section className="metric-grid" aria-label="工作台摘要">
        <Card className="metric-card">
          <div className="metric-icon teal">
            <GraduationCap />
          </div>
          <div>
            <span>進行中班級</span>
            <strong>{classes.data?.length ?? 0}</strong>
            <small>國高中英文</small>
          </div>
        </Card>
        <Card className="metric-card">
          <div className="metric-icon navy">
            <Library />
          </div>
          <div>
            <span>教材庫</span>
            <strong>{materials.data?.length ?? 0}</strong>
            <small>
              {materials.data?.filter((item) => item.parse_status === "ready")
                .length ?? 0}{" "}
              份可檢索
            </small>
          </div>
        </Card>
        <Card className="metric-card">
          <div className="metric-icon amber">
            <BookOpen />
          </div>
          <div>
            <span>教材包</span>
            <strong>{packages.data?.length ?? 0}</strong>
            <small>{approved} 份已核准</small>
          </div>
        </Card>
        <Card className="metric-card">
          <div className={`metric-icon ${issues ? "rose" : "green"}`}>
            {issues ? <TriangleAlert /> : <CircleCheckBig />}
          </div>
          <div>
            <span>需處理問題</span>
            <strong>{issues}</strong>
            <small>{issues ? "核准前需修正" : "目前沒有 fatal issue"}</small>
          </div>
        </Card>
      </section>
      <div className="dashboard-grid">
        <Card>
          <div className="section-heading">
            <div>
              <span className="eyebrow">最近更新</span>
              <h2>教材包進度</h2>
            </div>
            <Link to="/packages">
              查看全部 <ArrowRight />
            </Link>
          </div>
          <div className="data-list">
            {recent.map((item) => (
              <Link
                key={item.id}
                to={`/packages/${item.id}`}
                className="data-row"
              >
                <div className="file-avatar">
                  <BookOpen />
                </div>
                <div className="data-main">
                  <strong>{item.title}</strong>
                  <span>
                    {item.lesson_date} · {item.total_minutes} 分鐘 · v
                    {item.current_version}
                  </span>
                </div>
                <StatusPill value={item.status} />
                <ArrowRight className="row-arrow" />
              </Link>
            ))}
            {!recent.length ? (
              <p className="inline-empty">尚無教材包，從「產生新教材」開始。</p>
            ) : null}
          </div>
        </Card>
        <Card className="next-lesson">
          <span className="eyebrow">Demo 班級</span>
          <h2>{classes.data?.[0]?.name ?? "尚未建立班級"}</h2>
          {classes.data?.[0] ? (
            <>
              <div className="lesson-date">
                <div>
                  <span>下一堂</span>
                  <strong>8 月 12 日</strong>
                </div>
                <Clock3 />
                <span>19:00–21:00</span>
              </div>
              <div className="focus-list">
                <strong>本次建議重點</strong>
                {classes.data[0].objectives.slice(0, 3).map((item) => (
                  <span key={item}>
                    <CircleCheckBig />
                    {item}
                  </span>
                ))}
              </div>
              <Link
                className="button button-secondary full"
                to={`/classes/${classes.data[0].id}`}
              >
                查看班級脈絡
              </Link>
            </>
          ) : (
            <Link className="button button-secondary full" to="/classes">
              建立第一個班級
            </Link>
          )}
        </Card>
      </div>
    </div>
  );
}
