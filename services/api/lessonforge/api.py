from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_session
from .dependencies import get_current_user, require_roles
from .document_parser import (
    DocumentParseError,
    chunk_segments,
    detect_media_type,
    parse_document,
    sanitize_display_name,
    sha256_hex,
)
from .exports import ExportError, export_document, render_html
from .generation import PROMPT_VERSION, enqueue_generation
from .lesson_service import (
    create_version,
    get_package_record,
    load_blocks,
    package_view,
    replace_blocks,
    replace_issues,
    restore_snapshot,
)
from .models import (
    AuditLog,
    ClassGroup,
    GenerationRun,
    LessonPackage,
    LessonPackageVersion,
    MaterialChunk,
    Membership,
    Organization,
    SourceMaterial,
    StudentProfile,
    User,
)
from .providers import MockLLMProvider, generate_validated, get_provider
from .schemas import (
    BlockMove,
    BlockUpdate,
    ClassCreate,
    ClassUpdate,
    ClassView,
    CurrentUser,
    GenerationRequest,
    GenerationRunView,
    LessonBlock,
    LoginRequest,
    MaterialChunkView,
    MaterialMetadata,
    MaterialView,
    MemberCreate,
    MemberView,
    OrganizationCreate,
    PackageView,
    Role,
    StudentCreate,
    StudentView,
    TokenResponse,
    VersionView,
)
from .security import create_access_token, hash_password, verify_password
from .validators import validate_lesson_draft

router = APIRouter(prefix="/api")
SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserDep = Annotated[CurrentUser, Depends(get_current_user)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base or "lessonforge-org"


async def audit(
    session: AsyncSession,
    *,
    user: CurrentUser,
    action: str,
    resource_type: str,
    resource_id: str | None,
) -> None:
    session.add(
        AuditLog(
            organization_id=user.organization_id,
            actor_user_id=user.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    user = await session.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email 或密碼不正確")
    statement = (
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user.id)
        .order_by(Membership.created_at)
    )
    if payload.organization_id:
        statement = statement.where(Membership.organization_id == payload.organization_id)
    row = (await session.execute(statement)).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="帳號不屬於任何可用組織")
    membership, organization = row
    current = CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        organization_id=organization.id,
        organization_name=organization.name,
        role=Role(membership.role),
    )
    return TokenResponse(
        access_token=create_access_token(
            user_id=user.id, organization_id=organization.id, role=membership.role
        ),
        user=current,
    )


@router.get("/auth/me", response_model=CurrentUser)
async def me(user: UserDep) -> CurrentUser:
    return user


@router.post("/organizations", response_model=TokenResponse, status_code=201)
async def create_organization(
    payload: OrganizationCreate, session: SessionDep, user: UserDep
) -> TokenResponse:
    base = slugify(payload.name)
    count = await session.scalar(
        select(func.count()).select_from(Organization).where(Organization.slug.like(f"{base}%"))
    )
    organization = Organization(
        name=payload.name, slug=base if not count else f"{base}-{count + 1}"
    )
    session.add(organization)
    await session.flush()
    session.add(Membership(organization_id=organization.id, user_id=user.id, role=Role.owner.value))
    await session.commit()
    await session.refresh(organization)
    switched_user = CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        organization_id=organization.id,
        organization_name=organization.name,
        role=Role.owner,
    )
    return TokenResponse(
        access_token=create_access_token(
            user_id=user.id,
            organization_id=organization.id,
            role=Role.owner.value,
        ),
        user=switched_user,
    )


@router.get("/organizations/current/members", response_model=list[MemberView])
async def list_members(session: SessionDep, user: UserDep) -> list[MemberView]:
    rows = (
        await session.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == user.organization_id)
            .order_by(User.display_name)
        )
    ).all()
    return [
        MemberView(
            id=member.id, email=member.email, display_name=member.display_name, role=Role(link.role)
        )
        for member, link in rows
    ]


@router.post("/organizations/current/members", response_model=MemberView, status_code=201)
async def create_member(
    payload: MemberCreate,
    session: SessionDep,
    user: Annotated[CurrentUser, Depends(require_roles(Role.owner, Role.admin))],
) -> MemberView:
    existing = await session.scalar(
        select(User).where(func.lower(User.email) == payload.email.lower())
    )
    if existing is None:
        existing = User(
            email=payload.email.lower(),
            display_name=payload.display_name,
            password_hash=hash_password(payload.password),
        )
        session.add(existing)
        await session.flush()
    duplicate = await session.scalar(
        select(Membership).where(
            Membership.organization_id == user.organization_id,
            Membership.user_id == existing.id,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="此帳號已是組織成員")
    membership = Membership(
        organization_id=user.organization_id, user_id=existing.id, role=payload.role.value
    )
    session.add(membership)
    await audit(
        session,
        user=user,
        action="member.create",
        resource_type="membership",
        resource_id=membership.id,
    )
    await session.commit()
    return MemberView(
        id=existing.id, email=existing.email, display_name=existing.display_name, role=payload.role
    )


async def class_view(
    session: AsyncSession, organization_id: str, class_group: ClassGroup
) -> ClassView:
    students = list(
        (
            await session.scalars(
                select(StudentProfile).where(
                    StudentProfile.class_id == class_group.id,
                    StudentProfile.organization_id == organization_id,
                )
            )
        ).all()
    )
    return ClassView(
        **{
            column: getattr(class_group, column)
            for column in ClassView.model_fields
            if column not in {"students"}
        },
        students=[StudentView.model_validate(item) for item in students],
    )


@router.get("/classes", response_model=list[ClassView])
async def list_classes(session: SessionDep, user: UserDep) -> list[ClassView]:
    records = list(
        (
            await session.scalars(
                select(ClassGroup)
                .where(ClassGroup.organization_id == user.organization_id)
                .order_by(ClassGroup.name)
            )
        ).all()
    )
    return [await class_view(session, user.organization_id, item) for item in records]


@router.post("/classes", response_model=ClassView, status_code=201)
async def create_class(payload: ClassCreate, session: SessionDep, user: UserDep) -> ClassView:
    data = payload.model_dump(exclude={"students"})
    record = ClassGroup(organization_id=user.organization_id, **data)
    session.add(record)
    await session.flush()
    for student in payload.students:
        session.add(
            StudentProfile(
                organization_id=user.organization_id, class_id=record.id, **student.model_dump()
            )
        )
    await audit(
        session, user=user, action="class.create", resource_type="class", resource_id=record.id
    )
    await session.commit()
    await session.refresh(record)
    return await class_view(session, user.organization_id, record)


async def scoped_class(session: AsyncSession, user: CurrentUser, class_id: str) -> ClassGroup:
    record = await session.scalar(
        select(ClassGroup).where(
            ClassGroup.id == class_id, ClassGroup.organization_id == user.organization_id
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="找不到班級")
    return record


@router.get("/classes/{class_id}", response_model=ClassView)
async def get_class(class_id: str, session: SessionDep, user: UserDep) -> ClassView:
    return await class_view(
        session, user.organization_id, await scoped_class(session, user, class_id)
    )


@router.patch("/classes/{class_id}", response_model=ClassView)
async def update_class(
    class_id: str, payload: ClassUpdate, session: SessionDep, user: UserDep
) -> ClassView:
    record = await scoped_class(session, user, class_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    await audit(
        session, user=user, action="class.update", resource_type="class", resource_id=record.id
    )
    await session.commit()
    await session.refresh(record)
    return await class_view(session, user.organization_id, record)


@router.post("/classes/{class_id}/students", response_model=StudentView, status_code=201)
async def create_student(
    class_id: str,
    payload: StudentCreate,
    session: SessionDep,
    user: UserDep,
) -> StudentProfile:
    await scoped_class(session, user, class_id)
    student = StudentProfile(
        organization_id=user.organization_id,
        class_id=class_id,
        **payload.model_dump(),
    )
    session.add(student)
    await session.flush()
    await audit(
        session,
        user=user,
        action="student.create",
        resource_type="student_profile",
        resource_id=student.id,
    )
    await session.commit()
    await session.refresh(student)
    return student


@router.delete("/classes/{class_id}", status_code=204)
async def delete_class(class_id: str, session: SessionDep, user: UserDep) -> None:
    record = await scoped_class(session, user, class_id)
    await session.delete(record)
    await audit(
        session, user=user, action="class.delete", resource_type="class", resource_id=class_id
    )
    await session.commit()


def material_view(
    record: SourceMaterial, chunks: list[MaterialChunk] | None = None
) -> MaterialView:
    return MaterialView(
        id=record.id,
        display_name=record.display_name,
        media_type=record.media_type,
        size_bytes=record.size_bytes,
        grade=record.grade,
        chapter=record.chapter,
        topic=record.topic,
        difficulty=record.difficulty,
        tags=record.tags,
        parse_status=record.parse_status,
        extracted_text=record.extracted_text,
        parse_error=record.parse_error,
        chunks=[MaterialChunkView.model_validate(item) for item in (chunks or [])],
        created_at=record.created_at,
    )


@router.get("/materials", response_model=list[MaterialView])
async def list_materials(session: SessionDep, user: UserDep) -> list[MaterialView]:
    records = (
        await session.scalars(
            select(SourceMaterial)
            .where(SourceMaterial.organization_id == user.organization_id)
            .order_by(SourceMaterial.created_at.desc())
        )
    ).all()
    return [material_view(item) for item in records]


@router.post("/materials", response_model=MaterialView, status_code=201)
async def upload_material(
    session: SessionDep,
    user: UserDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
    grade: str = Form(default=""),
    chapter: str = Form(default=""),
    topic: str = Form(default=""),
    difficulty: str = Form(default="中等"),
    tags: str = Form(default=""),
) -> MaterialView:
    data = await file.read(settings.upload_max_bytes + 1)
    if len(data) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail=f"檔案超過 {settings.upload_max_mb} MB 限制")
    if not data:
        raise HTTPException(status_code=400, detail="檔案內容為空")
    try:
        media_type = detect_media_type(
            data, file.content_type or "application/octet-stream", file.filename or ""
        )
    except DocumentParseError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error

    parsed_tags = [item.strip() for item in tags.split(",") if item.strip()][:20]
    metadata = MaterialMetadata(
        grade=grade, chapter=chapter, topic=topic, difficulty=difficulty, tags=parsed_tags
    )
    extension = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/plain": ".txt",
        "text/markdown": ".md",
    }[media_type]
    material = SourceMaterial(
        organization_id=user.organization_id,
        uploaded_by_id=user.id,
        display_name=sanitize_display_name(file.filename or "未命名教材"),
        storage_key="pending",
        media_type=media_type,
        size_bytes=len(data),
        sha256=sha256_hex(data),
        **metadata.model_dump(),
    )
    session.add(material)
    await session.flush()
    relative_key = Path(user.organization_id) / f"{material.id}{extension}"
    material.storage_key = relative_key.as_posix()
    storage_path = (settings.upload_dir / relative_key).resolve()
    upload_root = settings.upload_dir.resolve()
    if upload_root not in storage_path.parents:
        raise HTTPException(status_code=400, detail="無效的儲存路徑")
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(data)
    try:
        parsed = parse_document(data, media_type)
        material.extracted_text = parsed.text
        material.parse_status = "ready"
        for index, segment in enumerate(chunk_segments(parsed.segments)):
            session.add(
                MaterialChunk(
                    organization_id=user.organization_id,
                    source_material_id=material.id,
                    sequence=index,
                    text=segment.text,
                    page_number=segment.page_number,
                    paragraph_number=segment.paragraph_number,
                    chapter=metadata.chapter,
                    tags=metadata.tags,
                )
            )
    except DocumentParseError as error:
        material.parse_status = "failed"
        material.parse_error = str(error)
    await audit(
        session,
        user=user,
        action="material.upload",
        resource_type="source_material",
        resource_id=material.id,
    )
    await session.commit()
    await session.refresh(material)
    chunks = list(
        (
            await session.scalars(
                select(MaterialChunk)
                .where(
                    MaterialChunk.source_material_id == material.id,
                    MaterialChunk.organization_id == user.organization_id,
                )
                .order_by(MaterialChunk.sequence)
            )
        ).all()
    )
    return material_view(material, chunks)


async def scoped_material(
    session: AsyncSession, user: CurrentUser, material_id: str
) -> SourceMaterial:
    record = await session.scalar(
        select(SourceMaterial).where(
            SourceMaterial.id == material_id, SourceMaterial.organization_id == user.organization_id
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="找不到教材")
    return record


@router.get("/materials/{material_id}", response_model=MaterialView)
async def get_material(material_id: str, session: SessionDep, user: UserDep) -> MaterialView:
    record = await scoped_material(session, user, material_id)
    chunks = list(
        (
            await session.scalars(
                select(MaterialChunk)
                .where(
                    MaterialChunk.source_material_id == material_id,
                    MaterialChunk.organization_id == user.organization_id,
                )
                .order_by(MaterialChunk.sequence)
            )
        ).all()
    )
    return material_view(record, chunks)


@router.delete("/materials/{material_id}", status_code=204)
async def delete_material(
    material_id: str, session: SessionDep, user: UserDep, settings: SettingsDep
) -> None:
    record = await scoped_material(session, user, material_id)
    upload_root = settings.upload_dir.resolve()
    storage_path = (settings.upload_dir / record.storage_key).resolve()
    if upload_root in storage_path.parents and storage_path.exists():
        storage_path.unlink()
    await session.delete(record)
    await audit(
        session,
        user=user,
        action="material.delete",
        resource_type="source_material",
        resource_id=material_id,
    )
    await session.commit()


@router.post("/generation", response_model=GenerationRunView, status_code=202)
async def create_generation(
    payload: GenerationRequest, session: SessionDep, user: UserDep, settings: SettingsDep
) -> GenerationRun:
    await scoped_class(session, user, payload.class_id)
    count = await session.scalar(
        select(func.count())
        .select_from(SourceMaterial)
        .where(
            SourceMaterial.id.in_(payload.material_ids),
            SourceMaterial.organization_id == user.organization_id,
            SourceMaterial.parse_status == "ready",
        )
    )
    if count != len(set(payload.material_ids)):
        raise HTTPException(status_code=400, detail="部分教材不存在、尚未解析完成或無權存取")
    run = GenerationRun(
        organization_id=user.organization_id,
        class_id=payload.class_id,
        requested_by_id=user.id,
        provider=settings.llm_provider,
        model=settings.llm_model,
        prompt_version=PROMPT_VERSION,
        input_settings=payload.model_dump(mode="json"),
        status="queued",
        progress=0,
        progress_message="等待中",
    )
    session.add(run)
    await audit(
        session,
        user=user,
        action="generation.create",
        resource_type="generation_run",
        resource_id=run.id,
    )
    await session.commit()
    await session.refresh(run)
    await enqueue_generation(run.id, settings)
    return run


@router.get("/generation/{run_id}", response_model=GenerationRunView)
async def get_generation(run_id: str, session: SessionDep, user: UserDep) -> GenerationRun:
    run = await session.scalar(
        select(GenerationRun).where(
            GenerationRun.id == run_id, GenerationRun.organization_id == user.organization_id
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="找不到生成任務")
    return run


@router.post("/generation/{run_id}/retry", response_model=GenerationRunView, status_code=202)
async def retry_generation(
    run_id: str, session: SessionDep, user: UserDep, settings: SettingsDep
) -> GenerationRun:
    run = await session.scalar(
        select(GenerationRun).where(
            GenerationRun.id == run_id, GenerationRun.organization_id == user.organization_id
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="找不到生成任務")
    if run.status not in {"failed", "completed"}:
        raise HTTPException(status_code=409, detail="目前任務仍在執行中")
    run.status = "queued"
    run.progress = 0
    run.progress_message = "等待重試"
    run.failure_reason = None
    await session.commit()
    await enqueue_generation(run.id, settings)
    return run


@router.get("/packages", response_model=list[PackageView])
async def list_packages(session: SessionDep, user: UserDep) -> list[PackageView]:
    ids = (
        await session.scalars(
            select(LessonPackage.id)
            .where(LessonPackage.organization_id == user.organization_id)
            .order_by(LessonPackage.updated_at.desc())
        )
    ).all()
    return [await package_view(session, user.organization_id, item) for item in ids]


@router.get("/packages/{package_id}", response_model=PackageView)
async def get_package(package_id: str, session: SessionDep, user: UserDep) -> PackageView:
    return await package_view(session, user.organization_id, package_id)


async def mutate_blocks(
    session: AsyncSession,
    *,
    user: CurrentUser,
    package: LessonPackage,
    blocks: list[LessonBlock],
    summary: str,
) -> PackageView:
    await replace_blocks(
        session, organization_id=user.organization_id, package_id=package.id, blocks=blocks
    )
    package.status = "draft"
    package.total_minutes = sum(item.duration_minutes for item in blocks)
    package.updated_at = datetime.now(UTC)
    draft_view = await package_view(session, user.organization_id, package.id)
    draft = draft_view.model_dump(
        exclude={
            "id",
            "class_id",
            "lesson_date",
            "status",
            "current_version",
            "validation_issues",
            "created_at",
            "updated_at",
        }
    )
    draft["grade_band"] = ""
    issues = validate_lesson_draft(
        __import__(
            "lessonforge.schemas", fromlist=["LessonPackageDraft"]
        ).LessonPackageDraft.model_validate(draft),
        expected_minutes=package.generation_settings.get("lesson_minutes", package.total_minutes),
        allowed_material_ids=set(package.generation_settings.get("material_ids", [])),
    )
    await replace_issues(
        session, organization_id=user.organization_id, package_id=package.id, issues=issues
    )
    await session.flush()
    await create_version(
        session,
        package=package,
        organization_id=user.organization_id,
        user_id=user.id,
        summary=summary,
    )
    await audit(
        session,
        user=user,
        action="package.edit",
        resource_type="lesson_package",
        resource_id=package.id,
    )
    await session.commit()
    return await package_view(session, user.organization_id, package.id)


@router.patch("/packages/{package_id}/blocks/{block_id}", response_model=PackageView)
async def update_block(
    package_id: str, block_id: str, payload: BlockUpdate, session: SessionDep, user: UserDep
) -> PackageView:
    package = await get_package_record(session, user.organization_id, package_id)
    blocks = await load_blocks(session, user.organization_id, package_id)
    target = next((item for item in blocks if item.id == block_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="找不到教材區塊")
    # Preserve nested Pydantic models (notably Question) for replace_blocks.
    # model_dump() recursively turns them into dicts, which only fails later
    # when persistence reads question.id/question.type.
    for key in payload.model_fields_set:
        setattr(target, key, getattr(payload, key))
    return await mutate_blocks(
        session, user=user, package=package, blocks=blocks, summary=f"編輯區塊：{target.title}"
    )


@router.post("/packages/{package_id}/blocks/{block_id}/lock", response_model=PackageView)
async def toggle_block_lock(
    package_id: str, block_id: str, session: SessionDep, user: UserDep
) -> PackageView:
    package = await get_package_record(session, user.organization_id, package_id)
    blocks = await load_blocks(session, user.organization_id, package_id)
    target = next((item for item in blocks if item.id == block_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="找不到教材區塊")
    target.locked = not target.locked
    return await mutate_blocks(
        session,
        user=user,
        package=package,
        blocks=blocks,
        summary=f"{'鎖定' if target.locked else '解鎖'}區塊：{target.title}",
    )


@router.post("/packages/{package_id}/blocks/{block_id}/regenerate", response_model=PackageView)
async def regenerate_block(
    package_id: str, block_id: str, session: SessionDep, user: UserDep, settings: SettingsDep
) -> PackageView:
    package = await get_package_record(session, user.organization_id, package_id)
    blocks = await load_blocks(session, user.organization_id, package_id)
    target = next((item for item in blocks if item.id == block_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="找不到教材區塊")
    if target.locked:
        raise HTTPException(status_code=409, detail="請先解鎖此區塊才能重新生成")
    provider = get_provider(settings)
    if isinstance(provider, MockLLMProvider):
        target.student_content = (
            target.student_content.rstrip() + "\n（已依班級弱點重新整理練習順序。）"
        )
        for question in target.questions:
            question.prompt = question.prompt.rstrip("。") + "（重生版）。"
    else:
        target, _ = await generate_validated(
            provider,
            prompt=f"重新生成單一教學區塊，保留時間與來源，教師指示：{package.generation_settings.get('teacher_instructions', '')}\n原區塊：{target.model_dump_json()}",
            model_type=LessonBlock,
            repair_attempts=settings.schema_repair_attempts,
        )
        target.id = block_id
    blocks[blocks.index(next(item for item in blocks if item.id == block_id))] = target
    return await mutate_blocks(
        session, user=user, package=package, blocks=blocks, summary=f"重新生成區塊：{target.title}"
    )


@router.post("/packages/{package_id}/blocks/{block_id}/copy", response_model=PackageView)
async def copy_block(
    package_id: str, block_id: str, session: SessionDep, user: UserDep
) -> PackageView:
    package = await get_package_record(session, user.organization_id, package_id)
    blocks = await load_blocks(session, user.organization_id, package_id)
    index = next((i for i, item in enumerate(blocks) if item.id == block_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="找不到教材區塊")
    copied = blocks[index].model_copy(deep=True)
    copied.id = None
    copied.title = f"{copied.title}（副本）"
    copied.locked = False
    for question in copied.questions:
        question.id = None
    blocks.insert(index + 1, copied)
    return await mutate_blocks(
        session, user=user, package=package, blocks=blocks, summary=f"複製區塊：{copied.title}"
    )


@router.post("/packages/{package_id}/blocks/{block_id}/move", response_model=PackageView)
async def move_block(
    package_id: str, block_id: str, payload: BlockMove, session: SessionDep, user: UserDep
) -> PackageView:
    package = await get_package_record(session, user.organization_id, package_id)
    blocks = await load_blocks(session, user.organization_id, package_id)
    index = next((i for i, item in enumerate(blocks) if item.id == block_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="找不到教材區塊")
    destination = index - 1 if payload.direction == "up" else index + 1
    if 0 <= destination < len(blocks):
        blocks[index], blocks[destination] = blocks[destination], blocks[index]
    return await mutate_blocks(
        session, user=user, package=package, blocks=blocks, summary="調整區塊順序"
    )


@router.delete("/packages/{package_id}/blocks/{block_id}", response_model=PackageView)
async def delete_block(
    package_id: str, block_id: str, session: SessionDep, user: UserDep
) -> PackageView:
    package = await get_package_record(session, user.organization_id, package_id)
    blocks = await load_blocks(session, user.organization_id, package_id)
    if not any(item.id == block_id for item in blocks):
        raise HTTPException(status_code=404, detail="找不到教材區塊")
    remaining = [item for item in blocks if item.id != block_id]
    if not remaining:
        raise HTTPException(status_code=409, detail="教材包至少需要一個區塊")
    return await mutate_blocks(
        session, user=user, package=package, blocks=remaining, summary="刪除教材區塊"
    )


@router.get("/packages/{package_id}/versions", response_model=list[VersionView])
async def list_versions(
    package_id: str, session: SessionDep, user: UserDep
) -> list[LessonPackageVersion]:
    await get_package_record(session, user.organization_id, package_id)
    return list(
        (
            await session.scalars(
                select(LessonPackageVersion)
                .where(
                    LessonPackageVersion.lesson_package_id == package_id,
                    LessonPackageVersion.organization_id == user.organization_id,
                )
                .order_by(LessonPackageVersion.version_number.desc())
            )
        ).all()
    )


@router.post("/packages/{package_id}/versions/{version_id}/restore", response_model=PackageView)
async def restore_version(
    package_id: str, version_id: str, session: SessionDep, user: UserDep
) -> PackageView:
    package = await get_package_record(session, user.organization_id, package_id)
    version = await session.scalar(
        select(LessonPackageVersion).where(
            LessonPackageVersion.id == version_id,
            LessonPackageVersion.lesson_package_id == package_id,
            LessonPackageVersion.organization_id == user.organization_id,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="找不到版本")
    await restore_snapshot(
        session,
        package=package,
        organization_id=user.organization_id,
        user_id=user.id,
        snapshot=version.snapshot,
    )
    await audit(
        session,
        user=user,
        action="package.restore",
        resource_type="lesson_package",
        resource_id=package.id,
    )
    await session.commit()
    return await package_view(session, user.organization_id, package.id)


@router.post("/packages/{package_id}/approve", response_model=PackageView)
async def approve_package(package_id: str, session: SessionDep, user: UserDep) -> PackageView:
    package = await get_package_record(session, user.organization_id, package_id)
    view = await package_view(session, user.organization_id, package_id)
    fatal = [issue for issue in view.validation_issues if issue.severity == "fatal"]
    if fatal:
        raise HTTPException(status_code=409, detail=f"仍有 {len(fatal)} 個嚴重驗證問題，無法核准")
    package.status = "approved"
    package.approved_by_id = user.id
    package.approved_at = datetime.now(UTC)
    await create_version(
        session,
        package=package,
        organization_id=user.organization_id,
        user_id=user.id,
        summary="老師核准教材",
    )
    await audit(
        session,
        user=user,
        action="package.approve",
        resource_type="lesson_package",
        resource_id=package.id,
    )
    await session.commit()
    return await package_view(session, user.organization_id, package.id)


@router.post("/packages/{package_id}/submit-review", response_model=PackageView)
async def submit_package_review(
    package_id: str,
    session: SessionDep,
    user: UserDep,
) -> PackageView:
    package = await get_package_record(session, user.organization_id, package_id)
    package.status = "review"
    await create_version(
        session,
        package=package,
        organization_id=user.organization_id,
        user_id=user.id,
        summary="送交老師審核",
    )
    await audit(
        session,
        user=user,
        action="package.submit_review",
        resource_type="lesson_package",
        resource_id=package.id,
    )
    await session.commit()
    return await package_view(session, user.organization_id, package.id)


@router.get("/packages/{package_id}/preview/{variant}", response_class=HTMLResponse)
async def preview_package(
    package_id: str,
    variant: Literal["student", "teacher", "homework", "quiz", "parent"],
    session: SessionDep,
    user: UserDep,
) -> HTMLResponse:
    package = await package_view(session, user.organization_id, package_id)
    class_group = await scoped_class(session, user, package.class_id)
    return HTMLResponse(
        render_html(
            package,
            organization_name=user.organization_name,
            class_name=class_group.name,
            variant=variant,
        )
    )


@router.get("/packages/{package_id}/export/{variant}.{file_format}")
async def download_export(
    package_id: str,
    variant: Literal["student", "teacher", "homework", "quiz", "parent"],
    file_format: Literal["pdf", "docx"],
    session: SessionDep,
    user: UserDep,
    settings: SettingsDep,
) -> FileResponse:
    package = await package_view(session, user.organization_id, package_id)
    class_group = await scoped_class(session, user, package.class_id)
    try:
        path, media_type = await export_document(
            package,
            settings=settings,
            organization_name=user.organization_name,
            class_name=class_group.name,
            variant=variant,
            file_format=file_format,
        )
    except ExportError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    await audit(
        session,
        user=user,
        action="package.export",
        resource_type="lesson_package",
        resource_id=package.id,
    )
    await session.commit()
    return FileResponse(
        path=path, media_type=media_type, filename=f"lessonforge-{variant}.{file_format}"
    )


@router.get("/settings/ai")
async def ai_settings(settings: SettingsDep, user: UserDep) -> dict[str, object]:
    del user
    return {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "raw_content_logging": settings.log_raw_ai_content,
        "api_key_configured": bool(settings.llm_api_key),
    }
