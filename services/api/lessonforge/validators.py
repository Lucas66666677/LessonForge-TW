from __future__ import annotations

import re
from difflib import SequenceMatcher

from .schemas import LessonBlock, LessonPackageDraft, ValidationIssue

OBJECTIVE_TYPES = {"vocabulary", "multiple_choice", "cloze", "reading"}


def normalize_question(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text.lower())


def validate_lesson_draft(
    draft: LessonPackageDraft,
    *,
    expected_minutes: int,
    allowed_material_ids: set[str] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    actual_minutes = sum(block.duration_minutes for block in draft.blocks)
    if abs(actual_minutes - expected_minutes) > 5:
        issues.append(
            ValidationIssue(
                code="duration_mismatch",
                severity="fatal",
                message=f"區塊時間總和為 {actual_minutes} 分鐘，與指定 {expected_minutes} 分鐘相差超過 5 分鐘。",
                details={"expected": expected_minutes, "actual": actual_minutes},
            )
        )
    if draft.total_minutes != expected_minutes:
        issues.append(
            ValidationIssue(
                code="declared_duration_mismatch",
                severity="warning",
                message="教材宣告時間與生成設定不同。",
                details={"expected": expected_minutes, "declared": draft.total_minutes},
            )
        )

    normalized_questions: list[tuple[str, str | None]] = []
    for block in draft.blocks:
        block_key = block.id or block.title
        if block.duration_minutes <= 0:
            issues.append(
                ValidationIssue(
                    code="invalid_duration",
                    severity="fatal",
                    message="區塊時間必須為正數。",
                    block_id=block.id,
                )
            )
        for reference in block.source_references:
            if (
                allowed_material_ids is not None
                and reference.source_material_id not in allowed_material_ids
            ):
                issues.append(
                    ValidationIssue(
                        code="foreign_source_reference",
                        severity="fatal",
                        message="來源引用不屬於目前組織或本次選取教材。",
                        block_id=block.id,
                        details={"source_material_id": reference.source_material_id},
                    )
                )
        for question in block.questions:
            normalized = normalize_question(question.prompt)
            for previous, previous_block in normalized_questions:
                if normalized and SequenceMatcher(None, normalized, previous).ratio() >= 0.92:
                    issues.append(
                        ValidationIssue(
                            code="duplicate_question",
                            severity="warning",
                            message="偵測到高度重複的題目。",
                            block_id=block.id,
                            details={"other_block": previous_block},
                        )
                    )
                    break
            normalized_questions.append((normalized, block_key))

            if question.type in OBJECTIVE_TYPES and not question.answer.strip():
                issues.append(
                    ValidationIssue(
                        code="missing_answer",
                        severity="fatal",
                        message="客觀題缺少答案。",
                        block_id=block.id,
                    )
                )
            if question.type in {"multiple_choice", "cloze", "reading"}:
                if len(question.options) < 3:
                    issues.append(
                        ValidationIssue(
                            code="insufficient_options",
                            severity="fatal",
                            message="選擇題至少需要 3 個選項。",
                            block_id=block.id,
                        )
                    )
                normalized_options = [option.strip().lower() for option in question.options]
                if len(normalized_options) != len(set(normalized_options)):
                    issues.append(
                        ValidationIssue(
                            code="duplicate_options",
                            severity="fatal",
                            message="選項不得完全重複。",
                            block_id=block.id,
                        )
                    )
                if question.answer.strip() and question.answer.strip().lower() not in set(
                    normalized_options
                ):
                    issues.append(
                        ValidationIssue(
                            code="answer_not_in_options",
                            severity="fatal",
                            message="正確答案必須存在於選項中。",
                            block_id=block.id,
                        )
                    )
                if not question.multiple_answers and any(
                    separator in question.answer for separator in [",", "、", ";"]
                ):
                    issues.append(
                        ValidationIssue(
                            code="multiple_answers_not_allowed",
                            severity="fatal",
                            message="單選題只能有一個正確答案。",
                            block_id=block.id,
                        )
                    )
            if question.type == "cloze" and not question.answer.strip():
                issues.append(
                    ValidationIssue(
                        code="empty_cloze_answer",
                        severity="fatal",
                        message="克漏字答案不得為空。",
                        block_id=block.id,
                    )
                )
            if question.type == "reading" and not (
                question.reading_reference or block.source_references
            ):
                issues.append(
                    ValidationIssue(
                        code="reading_without_source",
                        severity="fatal",
                        message="閱讀題必須連結文章或來源片段。",
                        block_id=block.id,
                    )
                )
    return issues


def validate_locked_blocks(
    previous: list[LessonBlock], regenerated: list[LessonBlock]
) -> list[ValidationIssue]:
    current_by_id = {block.id: block for block in regenerated if block.id}
    issues: list[ValidationIssue] = []
    for block in previous:
        if not block.locked or not block.id:
            continue
        current = current_by_id.get(block.id)
        if current is None or current.model_dump() != block.model_dump():
            issues.append(
                ValidationIssue(
                    code="locked_block_modified",
                    severity="fatal",
                    message="鎖定區塊在重新生成時被修改。",
                    block_id=block.id,
                )
            )
    return issues


def validate_export_content(*, variant: str, html: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    markers = ["data-answer", "答案：", "解析：", "教師備註"]
    if variant == "student" and any(marker in html for marker in markers):
        issues.append(
            ValidationIssue(
                code="student_answer_leak", severity="fatal", message="學生版包含答案或教師資訊。"
            )
        )
    if variant == "teacher" and ("答案：" not in html or "解析：" not in html):
        issues.append(
            ValidationIssue(
                code="teacher_answer_missing", severity="fatal", message="教師版缺少答案或解析。"
            )
        )
    return issues
