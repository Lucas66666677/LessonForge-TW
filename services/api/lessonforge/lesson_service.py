from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    LessonBlock as LessonBlockRecord,
)
from .models import (
    LessonPackage,
    LessonPackageVersion,
    ValidationIssueRecord,
)
from .models import (
    Question as QuestionRecord,
)
from .schemas import (
    HomeworkDay,
    LessonBlock,
    PackageView,
    ParentReport,
    Question,
    ValidationIssue,
    WeeklyQuiz,
)


async def get_package_record(
    session: AsyncSession, organization_id: str, package_id: str
) -> LessonPackage:
    record = await session.scalar(
        select(LessonPackage).where(
            LessonPackage.id == package_id,
            LessonPackage.organization_id == organization_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="找不到教材包")
    return record


async def load_blocks(
    session: AsyncSession, organization_id: str, package_id: str
) -> list[LessonBlock]:
    block_records = list(
        (
            await session.scalars(
                select(LessonBlockRecord)
                .where(
                    LessonBlockRecord.lesson_package_id == package_id,
                    LessonBlockRecord.organization_id == organization_id,
                )
                .order_by(LessonBlockRecord.position)
            )
        ).all()
    )
    question_records = list(
        (
            await session.scalars(
                select(QuestionRecord)
                .join(LessonBlockRecord, LessonBlockRecord.id == QuestionRecord.lesson_block_id)
                .where(
                    LessonBlockRecord.lesson_package_id == package_id,
                    QuestionRecord.organization_id == organization_id,
                )
                .order_by(QuestionRecord.lesson_block_id, QuestionRecord.position)
            )
        ).all()
    )
    questions_by_block: dict[str, list[Question]] = {}
    for question in question_records:
        questions_by_block.setdefault(question.lesson_block_id, []).append(
            Question(
                id=question.id,
                type=question.question_type,
                prompt=question.prompt,
                options=question.options,
                answer=question.answer,
                explanation=question.explanation,
                points=question.points,
                multiple_answers=question.multiple_answers,
                reading_reference=question.reading_reference,
            )
        )
    return [
        LessonBlock(
            id=block.id,
            type=block.block_type,
            title=block.title,
            duration_minutes=block.duration_minutes,
            instructions=block.instructions,
            teacher_notes=block.teacher_notes,
            student_content=block.student_content,
            questions=questions_by_block.get(block.id, []),
            source_references=block.source_references,
            locked=block.locked,
        )
        for block in block_records
    ]


async def load_issues(
    session: AsyncSession, organization_id: str, package_id: str
) -> list[ValidationIssue]:
    records = (
        await session.scalars(
            select(ValidationIssueRecord).where(
                ValidationIssueRecord.lesson_package_id == package_id,
                ValidationIssueRecord.organization_id == organization_id,
            )
        )
    ).all()
    return [
        ValidationIssue(
            code=item.code,
            severity=item.severity,
            message=item.message,
            block_id=item.block_id,
            details=item.details,
        )
        for item in records
    ]


async def package_view(session: AsyncSession, organization_id: str, package_id: str) -> PackageView:
    package = await get_package_record(session, organization_id, package_id)
    return PackageView(
        id=package.id,
        class_id=package.class_id,
        title=package.title,
        lesson_date=package.lesson_date,
        status=package.status,
        current_version=package.current_version,
        total_minutes=package.total_minutes,
        objectives=package.objectives,
        blocks=await load_blocks(session, organization_id, package_id),
        homework_days=[HomeworkDay.model_validate(day) for day in package.homework_days],
        weekly_quiz=WeeklyQuiz.model_validate(package.weekly_quiz) if package.weekly_quiz else None,
        parent_report=ParentReport.model_validate(package.parent_report)
        if package.parent_report
        else None,
        validation_issues=await load_issues(session, organization_id, package_id),
        created_at=package.created_at,
        updated_at=package.updated_at,
    )


async def replace_blocks(
    session: AsyncSession,
    *,
    organization_id: str,
    package_id: str,
    blocks: Iterable[LessonBlock],
) -> None:
    await session.execute(
        delete(QuestionRecord).where(
            QuestionRecord.lesson_block_id.in_(
                select(LessonBlockRecord.id).where(
                    LessonBlockRecord.lesson_package_id == package_id,
                    LessonBlockRecord.organization_id == organization_id,
                )
            )
        )
    )
    await session.execute(
        delete(LessonBlockRecord).where(
            LessonBlockRecord.lesson_package_id == package_id,
            LessonBlockRecord.organization_id == organization_id,
        )
    )
    for position, block in enumerate(blocks):
        block_record = LessonBlockRecord(
            id=block.id,
            organization_id=organization_id,
            lesson_package_id=package_id,
            position=position,
            block_type=block.type,
            title=block.title,
            duration_minutes=block.duration_minutes,
            instructions=block.instructions,
            teacher_notes=block.teacher_notes,
            student_content=block.student_content,
            source_references=[
                reference.model_dump(mode="json") for reference in block.source_references
            ],
            locked=block.locked,
        )
        session.add(block_record)
        await session.flush()
        for question_position, question in enumerate(block.questions):
            session.add(
                QuestionRecord(
                    id=question.id,
                    organization_id=organization_id,
                    lesson_block_id=block_record.id,
                    position=question_position,
                    question_type=question.type,
                    prompt=question.prompt,
                    options=question.options,
                    answer=question.answer,
                    explanation=question.explanation,
                    points=question.points,
                    multiple_answers=question.multiple_answers,
                    reading_reference=question.reading_reference,
                )
            )


async def replace_issues(
    session: AsyncSession,
    *,
    organization_id: str,
    package_id: str,
    issues: Iterable[ValidationIssue],
) -> None:
    await session.execute(
        delete(ValidationIssueRecord).where(
            ValidationIssueRecord.lesson_package_id == package_id,
            ValidationIssueRecord.organization_id == organization_id,
        )
    )
    for issue in issues:
        session.add(
            ValidationIssueRecord(
                organization_id=organization_id,
                lesson_package_id=package_id,
                block_id=issue.block_id,
                code=issue.code,
                severity=issue.severity,
                message=issue.message,
                details=issue.details,
            )
        )


async def create_version(
    session: AsyncSession,
    *,
    package: LessonPackage,
    organization_id: str,
    user_id: str,
    summary: str,
) -> LessonPackageVersion:
    view = await package_view(session, organization_id, package.id)
    package.current_version += 1
    version = LessonPackageVersion(
        organization_id=organization_id,
        lesson_package_id=package.id,
        version_number=package.current_version,
        snapshot=view.model_dump(mode="json"),
        change_summary=summary,
        created_by_id=user_id,
    )
    session.add(version)
    return version


async def save_initial_version(
    session: AsyncSession,
    *,
    package: LessonPackage,
    organization_id: str,
    user_id: str,
) -> None:
    view = await package_view(session, organization_id, package.id)
    session.add(
        LessonPackageVersion(
            organization_id=organization_id,
            lesson_package_id=package.id,
            version_number=1,
            snapshot=view.model_dump(mode="json"),
            change_summary="AI 產生初稿",
            created_by_id=user_id,
        )
    )


async def restore_snapshot(
    session: AsyncSession,
    *,
    package: LessonPackage,
    organization_id: str,
    user_id: str,
    snapshot: dict[str, Any],
) -> None:
    current = await package_view(session, organization_id, package.id)
    package.current_version += 1
    session.add(
        LessonPackageVersion(
            organization_id=organization_id,
            lesson_package_id=package.id,
            version_number=package.current_version,
            snapshot=current.model_dump(mode="json"),
            change_summary="還原前自動備份",
            created_by_id=user_id,
        )
    )
    restored = PackageView.model_validate(snapshot)
    package.title = restored.title
    package.status = "draft"
    package.total_minutes = restored.total_minutes
    package.objectives = restored.objectives
    package.homework_days = [day.model_dump(mode="json") for day in restored.homework_days]
    package.weekly_quiz = (
        restored.weekly_quiz.model_dump(mode="json") if restored.weekly_quiz else None
    )
    package.parent_report = (
        restored.parent_report.model_dump(mode="json") if restored.parent_report else None
    )
    package.updated_at = datetime.now(UTC)
    await replace_blocks(
        session, organization_id=organization_id, package_id=package.id, blocks=restored.blocks
    )
    await replace_issues(
        session,
        organization_id=organization_id,
        package_id=package.id,
        issues=restored.validation_issues,
    )
