from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, cast

from jinja2 import Template
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import SessionLocal
from .lesson_service import replace_blocks, replace_issues, save_initial_version
from .models import ClassGroup, GenerationRun, LessonPackage, SourceMaterial
from .providers import MockLLMProvider, ProviderError, generate_validated, get_provider
from .retrieval import retrieve_chunks
from .schemas import (
    GenerationRequest,
    HomeworkDay,
    LessonBlock,
    LessonPackageDraft,
    ParentReport,
    WeeklyQuiz,
)
from .validators import validate_lesson_draft

PROMPT_VERSION = "v1"
PROMPT_DIR = Path(__file__).resolve().parents[3] / "prompts"


class PlanBlock(BaseModel):
    type: str
    title: str
    duration_minutes: int = Field(gt=0)
    purpose: str


class LessonPlan(BaseModel):
    title: str
    grade_band: str
    objectives: list[str]
    blocks: list[PlanBlock]


class HomeworkBundle(BaseModel):
    days: list[HomeworkDay]


def render_prompt(name: str, **context: Any) -> str:
    template_path = PROMPT_DIR / f"{name}.{PROMPT_VERSION}.txt"
    return cast(str, Template(template_path.read_text(encoding="utf-8")).render(**context))


async def set_progress(
    session: AsyncSession,
    run: GenerationRun,
    *,
    status: str,
    progress: int,
    message: str,
) -> None:
    run.status = status
    run.progress = progress
    run.progress_message = message
    await session.commit()


async def _validate_scope(
    session: AsyncSession,
    run: GenerationRun,
    request: GenerationRequest,
) -> tuple[ClassGroup, list[SourceMaterial]]:
    class_group = await session.scalar(
        select(ClassGroup).where(
            ClassGroup.id == request.class_id,
            ClassGroup.organization_id == run.organization_id,
        )
    )
    if class_group is None:
        raise ProviderError("背景工作找不到同組織的班級")
    materials = list(
        (
            await session.scalars(
                select(SourceMaterial).where(
                    SourceMaterial.id.in_(request.material_ids),
                    SourceMaterial.organization_id == run.organization_id,
                    SourceMaterial.parse_status == "ready",
                )
            )
        ).all()
    )
    if len(materials) != len(set(request.material_ids)):
        raise ProviderError("部分教材不存在、尚未完成解析或不屬於目前組織")
    return class_group, materials


async def generate_draft(
    session: AsyncSession,
    *,
    run: GenerationRun,
    request: GenerationRequest,
    settings: Settings,
) -> tuple[LessonPackageDraft, str, dict[str, int] | None]:
    class_group, materials = await _validate_scope(session, run, request)
    await set_progress(session, run, status="retrieving", progress=15, message="檢索教材")
    query = " ".join(
        request.objectives + [request.teacher_instructions, class_group.learned_content]
    )
    retrieval = await retrieve_chunks(
        session,
        settings=settings,
        organization_id=run.organization_id,
        material_ids=request.material_ids,
        query=query,
        grade=class_group.grade,
        limit=8,
    )
    references = retrieval.references
    provider = get_provider(settings)

    await set_progress(session, run, status="planning", progress=28, message="規劃課程")
    if isinstance(provider, MockLLMProvider):
        await asyncio.sleep(0)
        await set_progress(
            session, run, status="generating_blocks", progress=45, message="生成教學區塊"
        )
        draft = provider.build_lesson(
            grade=class_group.grade,
            objectives=request.objectives,
            lesson_minutes=request.lesson_minutes,
            modules=request.modules,
            homework_days=request.homework_days,
            include_quiz=request.include_weekly_quiz,
            include_report=request.include_parent_report,
            references=references,
        )
        await set_progress(
            session, run, status="generating_homework", progress=65, message="生成每日作業"
        )
        await set_progress(session, run, status="generating_quiz", progress=74, message="生成週考")
        await set_progress(
            session, run, status="generating_report", progress=82, message="生成家長回報"
        )
        return draft, retrieval.mode, {"total_tokens": 0}

    normalized_input = {
        "class": {
            "grade": class_group.grade,
            "level": class_group.overall_level,
            "learned_content": class_group.learned_content,
            "common_errors": class_group.common_errors,
            "preferences": class_group.teaching_preferences,
        },
        "request": request.model_dump(mode="json"),
    }
    plan, token_usage = await generate_validated(
        provider,
        prompt=render_prompt(
            "lesson_plan",
            normalized_input=json.dumps(normalized_input, ensure_ascii=False),
            references=json.dumps([item.model_dump() for item in references], ensure_ascii=False),
        ),
        model_type=LessonPlan,
        repair_attempts=settings.schema_repair_attempts,
    )
    await set_progress(
        session, run, status="generating_blocks", progress=42, message="生成教學區塊"
    )
    blocks: list[LessonBlock] = []
    for index, block_plan in enumerate(plan.blocks):
        block, usage = await generate_validated(
            provider,
            prompt=render_prompt(
                "lesson_block",
                plan=plan.model_dump_json(),
                block_plan=block_plan.model_dump_json(),
                references=json.dumps(
                    [item.model_dump() for item in references], ensure_ascii=False
                ),
                teacher_instructions=request.teacher_instructions,
            ),
            model_type=LessonBlock,
            repair_attempts=settings.schema_repair_attempts,
        )
        blocks.append(block)
        token_usage = merge_usage(token_usage, usage)
        progress = 42 + int(18 * (index + 1) / max(1, len(plan.blocks)))
        await set_progress(
            session,
            run,
            status="generating_blocks",
            progress=progress,
            message=f"生成區塊 {index + 1}/{len(plan.blocks)}",
        )

    await set_progress(
        session, run, status="generating_homework", progress=66, message="生成每日作業"
    )
    homework, usage = await generate_validated(
        provider,
        prompt=render_prompt(
            "homework", lesson_summary=plan.model_dump_json(), homework_days=request.homework_days
        ),
        model_type=HomeworkBundle,
        repair_attempts=settings.schema_repair_attempts,
    )
    token_usage = merge_usage(token_usage, usage)
    quiz = None
    if request.include_weekly_quiz:
        await set_progress(session, run, status="generating_quiz", progress=74, message="生成週考")
        quiz, usage = await generate_validated(
            provider,
            prompt=render_prompt(
                "weekly_quiz",
                lesson_summary=plan.model_dump_json(),
                references=json.dumps(
                    [item.model_dump() for item in references], ensure_ascii=False
                ),
            ),
            model_type=WeeklyQuiz,
            repair_attempts=settings.schema_repair_attempts,
        )
        token_usage = merge_usage(token_usage, usage)
    report = None
    if request.include_parent_report:
        await set_progress(
            session, run, status="generating_report", progress=82, message="生成家長回報"
        )
        report, usage = await generate_validated(
            provider,
            prompt=render_prompt("parent_report", lesson_summary=plan.model_dump_json()),
            model_type=ParentReport,
            repair_attempts=settings.schema_repair_attempts,
        )
        token_usage = merge_usage(token_usage, usage)
    return (
        LessonPackageDraft(
            title=plan.title,
            grade_band=plan.grade_band,
            objectives=plan.objectives,
            total_minutes=request.lesson_minutes,
            blocks=blocks,
            homework_days=homework.days,
            weekly_quiz=quiz,
            parent_report=report,
        ),
        retrieval.mode,
        token_usage,
    )


def merge_usage(left: dict[str, int] | None, right: dict[str, int] | None) -> dict[str, int] | None:
    if not left and not right:
        return None
    keys = set((left or {}).keys()) | set((right or {}).keys())
    return {key: (left or {}).get(key, 0) + (right or {}).get(key, 0) for key in keys}


async def run_generation(run_id: str) -> None:
    settings = get_settings()
    start = time.perf_counter()
    async with SessionLocal() as session:
        run = await session.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
        if run is None:
            return
        run.attempt_count += 1
        await set_progress(
            session, run, status="normalizing", progress=5, message="整理班級與生成設定"
        )
        try:
            request = GenerationRequest.model_validate(run.input_settings)
            draft, retrieval_mode, token_usage = await generate_draft(
                session,
                run=run,
                request=request,
                settings=settings,
            )
            await set_progress(
                session, run, status="validating", progress=88, message="驗證教材內容"
            )
            issues = validate_lesson_draft(
                draft,
                expected_minutes=request.lesson_minutes,
                allowed_material_ids=set(request.material_ids),
            )
            package = LessonPackage(
                organization_id=run.organization_id,
                class_id=request.class_id,
                title=draft.title,
                lesson_date=request.lesson_date,
                status="draft",
                current_version=1,
                total_minutes=request.lesson_minutes,
                objectives=draft.objectives,
                homework_days=[day.model_dump(mode="json") for day in draft.homework_days],
                weekly_quiz=draft.weekly_quiz.model_dump(mode="json")
                if draft.weekly_quiz
                else None,
                parent_report=draft.parent_report.model_dump(mode="json")
                if draft.parent_report
                else None,
                generation_settings={
                    **request.model_dump(mode="json"),
                    "retrieval_mode": retrieval_mode,
                },
            )
            session.add(package)
            await session.flush()
            await replace_blocks(
                session,
                organization_id=run.organization_id,
                package_id=package.id,
                blocks=draft.blocks,
            )
            await replace_issues(
                session, organization_id=run.organization_id, package_id=package.id, issues=issues
            )
            await session.flush()
            await save_initial_version(
                session,
                package=package,
                organization_id=run.organization_id,
                user_id=run.requested_by_id,
            )
            run.lesson_package_id = package.id
            run.status = "completed"
            run.progress = 100
            run.progress_message = "完成"
            run.duration_ms = int((time.perf_counter() - start) * 1000)
            run.token_usage = token_usage
            run.validation_summary = {
                "fatal": sum(issue.severity == "fatal" for issue in issues),
                "warning": sum(issue.severity == "warning" for issue in issues),
                "retrieval_mode": retrieval_mode,
            }
            await session.commit()
        except Exception as error:
            run.status = "failed"
            run.progress_message = "生成失敗"
            run.failure_reason = user_safe_generation_error(error)
            run.duration_ms = int((time.perf_counter() - start) * 1000)
            await session.commit()


def user_safe_generation_error(error: Exception) -> str:
    if isinstance(error, ProviderError):
        return str(error)[:1000]
    return "生成教材時發生未預期錯誤，請重試；若問題持續，請檢查模型與系統設定。"


async def enqueue_generation(run_id: str, settings: Settings | None = None) -> None:
    selected = settings or get_settings()
    if selected.in_process_jobs:
        asyncio.create_task(run_generation(run_id))
        return
    redis = Redis.from_url(selected.redis_url, decode_responses=True)
    try:
        await redis.lpush("lessonforge:generation", run_id)
    finally:
        await redis.aclose()


async def recover_stuck_runs() -> int:
    """Fail any run left in a non-terminal state by a worker that restarted mid-job.

    A restart (redeploy, OOM, crash) drops whatever was in the in-memory Redis
    BRPOP wait or mid-generation; without this, the run's row stays wedged at
    its last in-progress status forever with no error and no way to retry
    (the retry endpoint only accepts "failed"/"completed"). Runs left this way
    become retry-eligible instead of silently disappearing.
    """
    async with SessionLocal() as session:
        stuck = (
            await session.scalars(
                select(GenerationRun).where(GenerationRun.status.notin_(["completed", "failed"]))
            )
        ).all()
        for run in stuck:
            run.status = "failed"
            run.progress_message = "生成失敗"
            run.failure_reason = "工作因伺服器重新啟動而中斷，請重試"
        await session.commit()
        return len(stuck)


async def worker_loop() -> None:
    settings = get_settings()
    await recover_stuck_runs()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        while True:
            item = await redis.brpop("lessonforge:generation", timeout=5)
            if item:
                run_id = item[1].decode("utf-8") if isinstance(item[1], bytes) else item[1]
                await run_generation(run_id)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(worker_loop())
