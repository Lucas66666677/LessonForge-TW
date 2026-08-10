from __future__ import annotations

import argparse
import asyncio
import json
import sys
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from lessonforge.config import Settings  # noqa: E402
from lessonforge.exports import render_html  # noqa: E402
from lessonforge.providers import (  # noqa: E402
    MockLLMProvider,
    OllamaProvider,
    generate_validated,
)
from lessonforge.schemas import (  # noqa: E402
    LessonPackageDraft,
    PackageView,
    SourceReference,
)
from lessonforge.validators import (  # noqa: E402
    validate_lesson_draft,
    validate_locked_blocks,
)

CASES_PATH = Path(__file__).with_name("cases.json")
RESULTS_DIR = Path(__file__).with_name("results")
OBJECTIVE_TYPES = {"vocabulary", "multiple_choice", "cloze", "reading"}


def synthetic_reference(case_id: str) -> SourceReference:
    return SourceReference(
        source_material_id=f"material-{case_id}",
        material_name="LessonForge 合法合成教材.md",
        chunk_id=f"chunk-{case_id}",
        excerpt="Evidence supports a claim when the source is relevant and verifiable.",
        paragraph_number=1,
    )


async def build_draft(
    case: dict[str, Any], *, live: bool, settings: Settings
) -> LessonPackageDraft:
    reference = synthetic_reference(case["id"])
    if not live:
        provider = MockLLMProvider(settings)
        return provider.build_lesson(
            grade=case["grade"],
            objectives=case["objectives"],
            lesson_minutes=case["minutes"],
            modules=case["modules"],
            homework_days=case["homework_days"],
            include_quiz=case["quiz"],
            include_report=case["report"],
            references=[reference],
        )
    provider = OllamaProvider(settings)
    prompt = (
        "產生一份繁體中文英文教材 JSON。必須精確符合 schema，總時間為 "
        f"{case['minutes']} 分鐘，年級 {case['grade']}，區塊為 "
        f"{json.dumps(case['modules'], ensure_ascii=False)}。每個區塊都引用此來源："
        f"{reference.model_dump_json()}。"
    )
    draft, _ = await generate_validated(
        provider,
        prompt=prompt,
        model_type=LessonPackageDraft,
        repair_attempts=settings.schema_repair_attempts,
    )
    return draft


def package_for_render(draft: LessonPackageDraft, index: int) -> PackageView:
    now = datetime.now(UTC)
    return PackageView(
        id=f"eval-package-{index}",
        class_id=f"eval-class-{index}",
        title=draft.title,
        lesson_date=date(2026, 8, 15),
        status="draft",
        current_version=1,
        total_minutes=draft.total_minutes,
        objectives=draft.objectives,
        blocks=draft.blocks,
        homework_days=draft.homework_days,
        weekly_quiz=draft.weekly_quiz,
        parent_report=draft.parent_report,
        validation_issues=[],
        created_at=now,
        updated_at=now,
    )


def evaluate_case(case: dict[str, Any], draft: LessonPackageDraft, index: int) -> dict[str, Any]:
    reference = synthetic_reference(case["id"])
    issues = validate_lesson_draft(
        draft,
        expected_minutes=case["minutes"],
        allowed_material_ids={reference.source_material_id},
    )
    questions = [question for block in draft.blocks for question in block.questions]
    objective_questions = [q for q in questions if q.type in OBJECTIVE_TYPES]
    answer_valid = sum(
        bool(q.answer.strip())
        and (
            not q.options
            or q.answer.strip().lower() in {item.strip().lower() for item in q.options}
        )
        for q in objective_questions
    )
    required = bool(
        draft.title.strip()
        and draft.objectives
        and draft.blocks
        and all(block.title.strip() and block.instructions.strip() for block in draft.blocks)
        and len(draft.homework_days) == case["homework_days"]
        and (not case["quiz"] or draft.weekly_quiz is not None)
        and (not case["report"] or draft.parent_report is not None)
    )
    schema_valid = bool(LessonPackageDraft.model_validate(draft.model_dump()))
    student_html = render_html(
        package_for_render(draft, index),
        organization_name="Eval 補習班",
        class_name=f"{case['grade']} Eval 班",
        variant="student",
    )
    leak = any(marker in student_html for marker in ("答案：", "解析：", "教師備註"))

    previous = deepcopy(draft.blocks)
    for block_index, block in enumerate(previous):
        block.id = f"{case['id']}-block-{block_index}"
    previous[0].locked = True
    regenerated = deepcopy(previous)
    locked_preserved = not validate_locked_blocks(previous, regenerated)
    senior = case["grade"].startswith("高")
    combined = " ".join(
        [draft.title]
        + [block.student_content for block in draft.blocks]
        + [question.prompt for question in questions]
    ).lower()
    difficulty_distinct = (
        "counterargument" in combined or "論證與推論" in combined
        if senior
        else "context" in combined and "counterargument" not in combined
    )
    return {
        "id": case["id"],
        "grade": case["grade"],
        "schema_valid": schema_valid,
        "required_fields_complete": required,
        "time_total_correct": sum(block.duration_minutes for block in draft.blocks)
        == case["minutes"],
        "duplicate_questions": sum(issue.code == "duplicate_question" for issue in issues),
        "question_count": len(questions),
        "answer_valid_count": answer_valid,
        "objective_question_count": len(objective_questions),
        "source_blocks": sum(bool(block.source_references) for block in draft.blocks),
        "block_count": len(draft.blocks),
        "student_answer_leak": leak,
        "locked_block_preserved": locked_preserved,
        "difficulty_distinct": difficulty_distinct,
        "fatal_issues": [issue.code for issue in issues if issue.severity == "fatal"],
    }


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def summarize(results: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "schema_valid_rate": ratio(sum(item["schema_valid"] for item in results), len(results)),
        "required_fields_complete_rate": ratio(
            sum(item["required_fields_complete"] for item in results), len(results)
        ),
        "time_total_correct_rate": ratio(
            sum(item["time_total_correct"] for item in results), len(results)
        ),
        "duplicate_question_rate": ratio(
            sum(item["duplicate_questions"] for item in results),
            sum(item["question_count"] for item in results),
        ),
        "answer_valid_rate": ratio(
            sum(item["answer_valid_count"] for item in results),
            sum(item["objective_question_count"] for item in results),
        ),
        "source_reference_rate": ratio(
            sum(item["source_blocks"] for item in results),
            sum(item["block_count"] for item in results),
        ),
        "student_answer_leak_rate": ratio(
            sum(item["student_answer_leak"] for item in results), len(results)
        ),
        "locked_block_preservation_rate": ratio(
            sum(item["locked_block_preserved"] for item in results), len(results)
        ),
        "difficulty_distinction_rate": ratio(
            sum(item["difficulty_distinct"] for item in results), len(results)
        ),
    }


def passed(metrics: dict[str, float]) -> bool:
    return (
        metrics["schema_valid_rate"] == 1
        and metrics["required_fields_complete_rate"] == 1
        and metrics["time_total_correct_rate"] >= 0.95
        and metrics["duplicate_question_rate"] <= 0.05
        and metrics["answer_valid_rate"] >= 0.99
        and metrics["source_reference_rate"] >= 0.95
        and metrics["student_answer_leak_rate"] == 0
        and metrics["locked_block_preservation_rate"] == 1
        and metrics["difficulty_distinction_rate"] >= 0.95
    )


def write_reports(
    *, mode: str, results: list[dict[str, Any]], metrics: dict[str, float], success: bool
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": mode,
        "generated_at": datetime.now(UTC).isoformat(),
        "case_count": len(results),
        "passed": success,
        "metrics": metrics,
        "cases": results,
    }
    (RESULTS_DIR / f"{mode}-latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = [
        "# LessonForge TW AI Eval",
        "",
        f"- Mode: `{mode}`",
        f"- Cases: {len(results)}",
        f"- Result: **{'PASS' if success else 'FAIL'}**",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    rows.extend(f"| {name} | {value:.2%} |" for name, value in metrics.items())
    rows.extend(
        ["", "## Case results", "", "| Case | Grade | Fatal | Result |", "|---|---|---|---|"]
    )
    for item in results:
        case_ok = not item["fatal_issues"] and all(
            item[key]
            for key in (
                "schema_valid",
                "required_fields_complete",
                "time_total_correct",
                "locked_block_preserved",
                "difficulty_distinct",
            )
        )
        rows.append(
            f"| {item['id']} | {item['grade']} | {', '.join(item['fatal_issues']) or '-'} | "
            f"{'PASS' if case_ok else 'FAIL'} |"
        )
    (RESULTS_DIR / f"{mode}-latest.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


async def main() -> int:
    parser = argparse.ArgumentParser(description="LessonForge TW synthetic AI eval")
    parser.add_argument("--live", action="store_true", help="Use the configured local Ollama")
    parser.add_argument("--limit", type=int, default=0, help="Optional case limit")
    args = parser.parse_args()
    cases: list[dict[str, Any]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if args.live and not args.limit:
        cases = [
            case
            for case in cases
            if case["id"] in {"junior-02", "junior-08", "senior-02", "senior-08"}
        ]
    elif args.limit:
        cases = cases[: args.limit]
    settings = Settings(
        llm_provider="ollama" if args.live else "mock",
        llm_model="qwen3:8b" if args.live else "mock-lesson-v1",
    )
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        draft = await build_draft(case, live=args.live, settings=settings)
        results.append(evaluate_case(case, draft, index))
    metrics = summarize(results)
    success = passed(metrics)
    mode = "live" if args.live else "mock"
    write_reports(mode=mode, results=results, metrics=metrics, success=success)
    print(json.dumps({"mode": mode, "cases": len(results), "passed": success, **metrics}, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
