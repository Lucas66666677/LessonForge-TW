from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import func, select

from lessonforge.config import get_settings
from lessonforge.database import SessionLocal, create_schema
from lessonforge.document_parser import chunk_segments, parse_document, sha256_hex
from lessonforge.generation import PROMPT_VERSION, run_generation
from lessonforge.models import (
    ClassGroup,
    GenerationRun,
    LessonPackage,
    LessonTemplate,
    MaterialChunk,
    Membership,
    Organization,
    SourceMaterial,
    StudentProfile,
    User,
)
from lessonforge.schemas import GenerationRequest
from lessonforge.security import hash_password

ROOT = Path(__file__).resolve().parents[1]


async def seed() -> None:
    settings = get_settings()
    settings.ensure_directories()
    await create_schema()
    async with SessionLocal() as session:
        organization = await session.scalar(
            select(Organization).where(Organization.slug == "demo-english-academy")
        )
        if organization is None:
            organization = Organization(name="晨光英文學苑", slug="demo-english-academy")
            session.add(organization)
            await session.flush()

        async def ensure_user(email: str, display_name: str, password: str, role: str) -> User:
            user = await session.scalar(select(User).where(func.lower(User.email) == email.lower()))
            if user is None:
                user = User(
                    email=email, display_name=display_name, password_hash=hash_password(password)
                )
                session.add(user)
                await session.flush()
            membership = await session.scalar(
                select(Membership).where(
                    Membership.organization_id == organization.id,
                    Membership.user_id == user.id,
                )
            )
            if membership is None:
                session.add(Membership(organization_id=organization.id, user_id=user.id, role=role))
            return user

        owner = await ensure_user(
            settings.demo_owner_email, "林教務主任", settings.demo_owner_password, "owner"
        )
        await ensure_user(
            settings.demo_teacher_email, "陳老師", settings.demo_teacher_password, "teacher"
        )

        class_group = await session.scalar(
            select(ClassGroup).where(
                ClassGroup.organization_id == organization.id,
                ClassGroup.name == "國高中混合英文班",
            )
        )
        if class_group is None:
            class_group = ClassGroup(
                organization_id=organization.id,
                name="國高中混合英文班",
                grade="國三",
                material_name="LessonForge 自製閱讀教材",
                weekly_schedule="週三、週六 19:00–21:00",
                objectives=["用上下文理解單字", "區分主張與證據", "提升閱讀細節定位"],
                overall_level="中等偏弱",
                learned_content="現在完成式、基礎連接詞、短篇閱讀",
                common_errors=["拼字字母順序混淆", "忽略轉折詞後的重要資訊"],
                teaching_preferences="先引導示範，再獨立作答；每 25 分鐘安排短回顧。",
                homework_days=4,
                homework_minutes=30,
                notes="Demo 班級，學生僅使用代號。",
            )
            session.add(class_group)
            await session.flush()
            session.add_all(
                [
                    StudentProfile(
                        organization_id=organization.id,
                        class_id=class_group.id,
                        alias="學生 A",
                        weaknesses=["單字"],
                        notes="單字基礎弱，拼字容易混淆。",
                    ),
                    StudentProfile(
                        organization_id=organization.id,
                        class_id=class_group.id,
                        alias="學生 B",
                        weaknesses=["閱讀理解"],
                        notes="單字稍好，閱讀理解與細節定位較弱。",
                    ),
                ]
            )

        template = await session.scalar(
            select(LessonTemplate).where(
                LessonTemplate.organization_id == organization.id,
                LessonTemplate.is_default.is_(True),
            )
        )
        if template is None:
            session.add(
                LessonTemplate(
                    organization_id=organization.id,
                    name="兩小時英文核心課",
                    is_default=True,
                    structure=[
                        {"title": title, "enabled": True}
                        for title in [
                            "作業與錯題檢查",
                            "快速單字回想",
                            "引導式克漏字",
                            "獨立克漏字",
                            "閱讀理解",
                            "綜合挑戰",
                            "長句拆解",
                            "錯題訂正與總結",
                        ]
                    ],
                )
            )

        material = await session.scalar(
            select(SourceMaterial).where(
                SourceMaterial.organization_id == organization.id,
                SourceMaterial.display_name == "Evidence in Everyday Decisions.md",
            )
        )
        if material is None:
            data = (ROOT / "fixtures" / "demo_material.md").read_bytes()
            material = SourceMaterial(
                organization_id=organization.id,
                uploaded_by_id=owner.id,
                display_name="Evidence in Everyday Decisions.md",
                storage_key="pending",
                media_type="text/markdown",
                size_bytes=len(data),
                sha256=sha256_hex(data),
                grade="國三",
                chapter="Reading Strategies",
                topic="Claim and Evidence",
                difficulty="中等",
                tags=["閱讀", "證據", "單字"],
                parse_status="ready",
            )
            session.add(material)
            await session.flush()
            key = Path(organization.id) / f"{material.id}.md"
            material.storage_key = key.as_posix()
            storage = settings.upload_dir / key
            storage.parent.mkdir(parents=True, exist_ok=True)
            storage.write_bytes(data)
            parsed = parse_document(data, "text/markdown")
            material.extracted_text = parsed.text
            for index, chunk in enumerate(chunk_segments(parsed.segments)):
                session.add(
                    MaterialChunk(
                        organization_id=organization.id,
                        source_material_id=material.id,
                        sequence=index,
                        text=chunk.text,
                        paragraph_number=chunk.paragraph_number,
                        chapter=material.chapter,
                        tags=material.tags,
                    )
                )
        await session.commit()

        existing_packages = list(
            (
                await session.scalars(
                    select(LessonPackage).where(LessonPackage.organization_id == organization.id)
                )
            ).all()
        )
        needed = max(0, 2 - len(existing_packages))
        for index in range(needed):
            request = GenerationRequest(
                class_id=class_group.id,
                material_ids=[material.id],
                lesson_date=date(2026, 8, 12 + index),
                lesson_minutes=120,
                objectives=["辨認文章主張與證據", "使用上下文理解核心單字"],
                question_types={"vocabulary": 8, "cloze": 6, "reading": 4},
                homework_days=4,
                include_weekly_quiz=True,
                include_parent_report=True,
                teacher_instructions="照顧拼字較弱與閱讀定位較弱的學生。",
            )
            run = GenerationRun(
                organization_id=organization.id,
                class_id=class_group.id,
                requested_by_id=owner.id,
                provider=settings.llm_provider,
                model=settings.llm_model,
                prompt_version=PROMPT_VERSION,
                input_settings=request.model_dump(mode="json"),
            )
            session.add(run)
            await session.commit()
            await run_generation(run.id)

        packages = list(
            (
                await session.scalars(
                    select(LessonPackage)
                    .where(LessonPackage.organization_id == organization.id)
                    .order_by(LessonPackage.created_at)
                )
            ).all()
        )
        if len(packages) >= 2:
            packages[1].status = "approved"
            packages[1].approved_by_id = owner.id
            packages[1].approved_at = datetime.now(UTC)
            await session.commit()

    print("Seed complete")
    print(f"Owner: {settings.demo_owner_email} / {settings.demo_owner_password}")
    print(f"Teacher: {settings.demo_teacher_email} / {settings.demo_teacher_password}")


if __name__ == "__main__":
    asyncio.run(seed())
