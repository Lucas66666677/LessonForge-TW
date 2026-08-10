from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any, cast

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, TypeEngine

from .database import Base


def uuid4_str() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class VectorOrJSON(TypeDecorator[list[float]]):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return cast(TypeEngine[Any], dialect.type_descriptor(Vector(768)))
        return cast(TypeEngine[Any], dialect.type_descriptor(JSON()))


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    organization: Mapped[Organization] = relationship()
    user: Mapped[User] = relationship()


class ClassGroup(TimestampMixin, Base):
    __tablename__ = "classes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    grade: Mapped[str] = mapped_column(String(20))
    material_name: Mapped[str] = mapped_column(String(120), default="自訂教材")
    weekly_schedule: Mapped[str] = mapped_column(String(120), default="")
    objectives: Mapped[list[str]] = mapped_column(JSON, default=list)
    overall_level: Mapped[str] = mapped_column(String(30), default="中等")
    learned_content: Mapped[str] = mapped_column(Text, default="")
    common_errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    teaching_preferences: Mapped[str] = mapped_column(Text, default="")
    homework_days: Mapped[int] = mapped_column(Integer, default=4)
    homework_minutes: Mapped[int] = mapped_column(Integer, default=30)
    notes: Mapped[str] = mapped_column(Text, default="")


class StudentProfile(TimestampMixin, Base):
    __tablename__ = "student_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(50))
    weaknesses: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")


class SourceMaterial(TimestampMixin, Base):
    __tablename__ = "source_materials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    uploaded_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    display_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    media_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    grade: Mapped[str] = mapped_column(String(20), default="")
    chapter: Mapped[str] = mapped_column(String(120), default="")
    topic: Mapped[str] = mapped_column(String(120), default="")
    difficulty: Mapped[str] = mapped_column(String(30), default="中等")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    parse_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class MaterialChunk(TimestampMixin, Base):
    __tablename__ = "material_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    source_material_id: Mapped[str] = mapped_column(
        ForeignKey("source_materials.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paragraph_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chapter: Mapped[str] = mapped_column(String(120), default="")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(VectorOrJSON(), nullable=True)


class LessonTemplate(TimestampMixin, Base):
    __tablename__ = "lesson_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    structure: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class LessonPackage(TimestampMixin, Base):
    __tablename__ = "lesson_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    lesson_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    total_minutes: Mapped[int] = mapped_column(Integer, default=120)
    objectives: Mapped[list[str]] = mapped_column(JSON, default=list)
    homework_days: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    weekly_quiz: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    parent_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    generation_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LessonPackageVersion(TimestampMixin, Base):
    __tablename__ = "lesson_package_versions"
    __table_args__ = (UniqueConstraint("lesson_package_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    lesson_package_id: Mapped[str] = mapped_column(
        ForeignKey("lesson_packages.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(String(255))
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))


class LessonBlock(TimestampMixin, Base):
    __tablename__ = "lesson_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    lesson_package_id: Mapped[str] = mapped_column(
        ForeignKey("lesson_packages.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    block_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(180))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[str] = mapped_column(Text, default="")
    teacher_notes: Mapped[str] = mapped_column(Text, default="")
    student_content: Mapped[str] = mapped_column(Text, default="")
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)


class Question(TimestampMixin, Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    lesson_block_id: Mapped[str] = mapped_column(
        ForeignKey("lesson_blocks.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    question_type: Mapped[str] = mapped_column(String(40))
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON, default=list)
    answer: Mapped[str] = mapped_column(Text, default="")
    explanation: Mapped[str] = mapped_column(Text, default="")
    points: Mapped[int] = mapped_column(Integer, default=1)
    multiple_answers: Mapped[bool] = mapped_column(Boolean, default=False)
    reading_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)


class GenerationRun(TimestampMixin, Base):
    __tablename__ = "generation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    lesson_package_id: Mapped[str | None] = mapped_column(
        ForeignKey("lesson_packages.id", ondelete="SET NULL"), nullable=True
    )
    class_id: Mapped[str] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    requested_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(40))
    input_settings: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[str] = mapped_column(String(160), default="等待中")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    validation_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ValidationIssueRecord(TimestampMixin, Base):
    __tablename__ = "validation_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    lesson_package_id: Mapped[str] = mapped_column(
        ForeignKey("lesson_packages.id", ondelete="CASCADE"), index=True
    )
    block_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    code: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
