from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import select

from lessonforge.config import get_settings
from lessonforge.database import SessionLocal
from lessonforge.exports import build_docx, render_html
from lessonforge.generation import recover_stuck_runs, run_generation
from lessonforge.lesson_service import package_view
from lessonforge.models import GenerationRun
from lessonforge.schemas import GenerationRequest


def test_update_block_preserves_nested_question_models(
    client: TestClient,
    owner_a_headers: dict[str, str],
    seeded: dict[str, Any],
) -> None:
    package = client.get(f"/api/packages/{seeded['package_a']}", headers=owner_a_headers).json()
    block = package["blocks"][0]
    block["questions"][0]["prompt"] = "Which sentence is the evidence?"

    response = client.patch(
        f"/api/packages/{seeded['package_a']}/blocks/{block['id']}",
        headers=owner_a_headers,
        json={
            "student_content": f"{block['student_content']}\nTeacher revision.",
            "questions": block["questions"],
        },
    )

    assert response.status_code == 200
    updated = response.json()["blocks"][0]
    assert updated["student_content"].endswith("Teacher revision.")
    assert updated["questions"][0]["prompt"] == "Which sentence is the evidence?"


def test_lock_blocks_regeneration_and_version_restore(
    client: TestClient,
    owner_a_headers: dict[str, str],
    seeded: dict[str, Any],
) -> None:
    package = client.get(f"/api/packages/{seeded['package_a']}", headers=owner_a_headers).json()
    block_id = package["blocks"][0]["id"]
    locked = client.post(
        f"/api/packages/{seeded['package_a']}/blocks/{block_id}/lock",
        headers=owner_a_headers,
    )
    assert locked.status_code == 200
    assert locked.json()["blocks"][0]["locked"] is True
    denied = client.post(
        f"/api/packages/{seeded['package_a']}/blocks/{block_id}/regenerate",
        headers=owner_a_headers,
    )
    assert denied.status_code == 409
    versions = client.get(
        f"/api/packages/{seeded['package_a']}/versions",
        headers=owner_a_headers,
    ).json()
    assert versions
    restored = client.post(
        f"/api/packages/{seeded['package_a']}/versions/{versions[-1]['id']}/restore",
        headers=owner_a_headers,
    )
    assert restored.status_code == 200


@pytest.mark.asyncio
async def test_student_teacher_export_separation_and_docx(seeded: dict[str, Any]) -> None:
    async with SessionLocal() as session:
        package = await package_view(session, seeded["org_a"], seeded["package_a"])
    student = render_html(
        package, organization_name="A 補習班", class_name="A 班", variant="student"
    )
    teacher = render_html(
        package, organization_name="A 補習班", class_name="A 班", variant="teacher"
    )
    assert "答案：" not in student and "教師備註" not in student
    assert "答案：Evidence" in teacher and "解析：" in teacher
    student_docx = build_docx(
        package, organization_name="A 補習班", class_name="A 班", variant="student"
    )
    document = Document(BytesIO(student_docx))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "答案：" not in text


@pytest.mark.asyncio
async def test_background_failure_is_persisted_and_retryable(seeded: dict[str, Any]) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        request = GenerationRequest(
            class_id="missing-class",
            material_ids=[seeded["material_a"]],
            lesson_date=date(2026, 8, 20),
            objectives=["Test"],
        )
        run = GenerationRun(
            organization_id=seeded["org_a"],
            class_id=seeded["class_a"],
            requested_by_id=seeded["owner_a"],
            provider=settings.llm_provider,
            model=settings.llm_model,
            prompt_version="v1",
            input_settings=request.model_dump(mode="json"),
        )
        session.add(run)
        await session.commit()
        run_id = run.id
    await run_generation(run_id)
    async with SessionLocal() as session:
        saved = await session.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
        assert saved is not None
        assert saved.status == "failed"
        assert saved.attempt_count == 1
        assert saved.failure_reason
        assert saved.duration_ms is not None


@pytest.mark.asyncio
async def test_recover_stuck_runs_fails_and_makes_retryable(seeded: dict[str, Any]) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        request = GenerationRequest(
            class_id=seeded["class_a"],
            material_ids=[seeded["material_a"]],
            lesson_date=date(2026, 8, 20),
            objectives=["Test"],
        )
        run = GenerationRun(
            organization_id=seeded["org_a"],
            class_id=seeded["class_a"],
            requested_by_id=seeded["owner_a"],
            provider=settings.llm_provider,
            model=settings.llm_model,
            prompt_version="v1",
            input_settings=request.model_dump(mode="json"),
            status="generating_blocks",
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    recovered = await recover_stuck_runs()
    assert recovered >= 1

    async with SessionLocal() as session:
        saved = await session.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
        assert saved is not None
        assert saved.status == "failed"
        assert saved.failure_reason

    # Already-terminal runs must not be touched by a second recovery pass.
    async with SessionLocal() as session:
        saved = await session.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
        saved.failure_reason = "distinct-marker"
        await session.commit()
    await recover_stuck_runs()
    async with SessionLocal() as session:
        saved = await session.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
        assert saved.failure_reason == "distinct-marker"


@pytest.mark.asyncio
async def test_successful_generation_persists_audit_metrics(seeded: dict[str, Any]) -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        request = GenerationRequest(
            class_id=seeded["class_a"],
            material_ids=[seeded["material_a"]],
            lesson_date=date(2026, 8, 20),
            objectives=["辨認主張與證據"],
        )
        run = GenerationRun(
            organization_id=seeded["org_a"],
            class_id=seeded["class_a"],
            requested_by_id=seeded["owner_a"],
            provider=settings.llm_provider,
            model=settings.llm_model,
            prompt_version="v1",
            input_settings=request.model_dump(mode="json"),
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    await run_generation(run_id)

    async with SessionLocal() as session:
        saved = await session.scalar(select(GenerationRun).where(GenerationRun.id == run_id))
        assert saved is not None
        assert saved.status == "completed"
        assert saved.lesson_package_id
        assert saved.duration_ms is not None
        assert saved.duration_ms >= 0
        assert saved.token_usage == {"total_tokens": 0}
        assert saved.validation_summary is not None
        assert saved.validation_summary["fatal"] == 0
        assert saved.validation_summary["retrieval_mode"] == "full_text"
