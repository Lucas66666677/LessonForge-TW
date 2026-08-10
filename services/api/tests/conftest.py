from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import date
from typing import Any

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./artifacts/pytest.db"
os.environ["JWT_SECRET"] = "pytest-secret-that-is-longer-than-32-characters"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "disabled"
os.environ["IN_PROCESS_JOBS"] = "true"
os.environ["UPLOAD_DIR"] = "artifacts/test-uploads"
os.environ["EXPORT_DIR"] = "artifacts/test-exports"

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from lessonforge.config import get_settings
from lessonforge.database import Base, SessionLocal, engine
from lessonforge.lesson_service import replace_blocks, replace_issues
from lessonforge.main import app
from lessonforge.models import (
    ClassGroup,
    LessonPackage,
    MaterialChunk,
    Membership,
    Organization,
    SourceMaterial,
    StudentProfile,
    User,
)
from lessonforge.schemas import LessonBlock, Question, SourceReference
from lessonforge.security import hash_password


@pytest_asyncio.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    get_settings.cache_clear()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def seeded() -> dict[str, Any]:
    async with SessionLocal() as session:
        org_a = Organization(name="A 補習班", slug="org-a")
        org_b = Organization(name="B 補習班", slug="org-b")
        session.add_all([org_a, org_b])
        await session.flush()
        owner_a = User(
            email="a@example.com",
            display_name="Owner A",
            password_hash=hash_password("Password!123"),
        )
        teacher_a = User(
            email="teacher-a@example.com",
            display_name="Teacher A",
            password_hash=hash_password("Password!123"),
        )
        owner_b = User(
            email="b@example.com",
            display_name="Owner B",
            password_hash=hash_password("Password!123"),
        )
        session.add_all([owner_a, teacher_a, owner_b])
        await session.flush()
        session.add_all(
            [
                Membership(organization_id=org_a.id, user_id=owner_a.id, role="owner"),
                Membership(organization_id=org_a.id, user_id=teacher_a.id, role="teacher"),
                Membership(organization_id=org_b.id, user_id=owner_b.id, role="owner"),
            ]
        )
        class_a = ClassGroup(
            organization_id=org_a.id,
            name="A 班",
            grade="國三",
            objectives=["閱讀理解"],
            common_errors=["忽略轉折詞"],
        )
        class_b = ClassGroup(
            organization_id=org_b.id, name="B 班", grade="高一", objectives=["寫作"]
        )
        session.add_all([class_a, class_b])
        await session.flush()
        session.add(
            StudentProfile(
                organization_id=org_a.id,
                class_id=class_a.id,
                alias="學生 A",
                weaknesses=["單字"],
            )
        )
        material_a = SourceMaterial(
            organization_id=org_a.id,
            uploaded_by_id=owner_a.id,
            display_name="a.md",
            storage_key=f"{org_a.id}/a.md",
            media_type="text/markdown",
            size_bytes=20,
            sha256="a" * 64,
            grade="國三",
            chapter="Unit 1",
            topic="Evidence",
            difficulty="中等",
            tags=["閱讀"],
            parse_status="ready",
            extracted_text="Evidence supports a claim.",
        )
        material_b = SourceMaterial(
            organization_id=org_b.id,
            uploaded_by_id=owner_b.id,
            display_name="b.md",
            storage_key=f"{org_b.id}/b.md",
            media_type="text/markdown",
            size_bytes=20,
            sha256="b" * 64,
            grade="高一",
            chapter="Unit 2",
            topic="Writing",
            difficulty="中等",
            tags=["寫作"],
            parse_status="ready",
            extracted_text="A paragraph needs a topic sentence.",
        )
        session.add_all([material_a, material_b])
        await session.flush()
        chunk_a = MaterialChunk(
            organization_id=org_a.id,
            source_material_id=material_a.id,
            sequence=0,
            text="Evidence supports a claim and context helps readers interpret it.",
            paragraph_number=1,
            chapter="Unit 1",
            tags=["閱讀"],
        )
        chunk_b = MaterialChunk(
            organization_id=org_b.id,
            source_material_id=material_b.id,
            sequence=0,
            text="A topic sentence guides a paragraph.",
            paragraph_number=1,
            chapter="Unit 2",
            tags=["寫作"],
        )
        session.add_all([chunk_a, chunk_b])
        await session.flush()
        package_a = LessonPackage(
            organization_id=org_a.id,
            class_id=class_a.id,
            title="A 班教材",
            lesson_date=date(2026, 8, 12),
            total_minutes=120,
            objectives=["閱讀理解"],
            generation_settings={"lesson_minutes": 120, "material_ids": [material_a.id]},
        )
        session.add(package_a)
        await session.flush()
        blocks = [
            LessonBlock(
                type="reading",
                title="閱讀理解",
                duration_minutes=120,
                student_content="Evidence supports a claim.",
                teacher_notes="請學生圈出證據。",
                questions=[
                    Question(
                        type="reading",
                        prompt="What supports a claim?",
                        options=["Evidence", "Noise", "Color"],
                        answer="Evidence",
                        explanation="Evidence supports a claim.",
                        reading_reference=chunk_a.id,
                    )
                ],
                source_references=[
                    SourceReference(
                        source_material_id=material_a.id,
                        material_name=material_a.display_name,
                        chunk_id=chunk_a.id,
                        excerpt=chunk_a.text,
                        paragraph_number=1,
                    )
                ],
            )
        ]
        await replace_blocks(
            session, organization_id=org_a.id, package_id=package_a.id, blocks=blocks
        )
        await replace_issues(session, organization_id=org_a.id, package_id=package_a.id, issues=[])
        await session.commit()
        return {
            "org_a": org_a.id,
            "org_b": org_b.id,
            "owner_a": owner_a.id,
            "teacher_a": teacher_a.id,
            "owner_b": owner_b.id,
            "class_a": class_a.id,
            "class_b": class_b.id,
            "material_a": material_a.id,
            "material_b": material_b.id,
            "chunk_a": chunk_a.id,
            "package_a": package_a.id,
        }


def login_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": "Password!123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def owner_a_headers(client: TestClient, seeded: dict[str, Any]) -> dict[str, str]:
    del seeded
    return login_headers(client, "a@example.com")


@pytest.fixture
def owner_b_headers(client: TestClient, seeded: dict[str, Any]) -> dict[str, str]:
    del seeded
    return login_headers(client, "b@example.com")


@pytest.fixture
def teacher_a_headers(client: TestClient, seeded: dict[str, Any]) -> dict[str, str]:
    del seeded
    return login_headers(client, "teacher-a@example.com")
