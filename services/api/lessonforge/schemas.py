from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class Role(StrEnum):
    owner = "owner"
    admin = "admin"
    teacher = "teacher"


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: CurrentUser


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    organization_id: str | None = None


class CurrentUser(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    organization_id: str
    organization_name: str
    role: Role


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class OrganizationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    slug: str
    created_at: datetime


class MemberCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=10, max_length=128)
    role: Role = Role.teacher


class MemberView(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    role: Role


ALLOWED_GRADES = {"國一", "國二", "國三", "高一", "高二", "高三"}
WEAKNESS_TYPES = {"單字", "文法", "克漏字", "閱讀理解", "翻譯", "寫作", "長句解析"}


class StudentCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=50)
    weaknesses: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)

    @field_validator("weaknesses")
    @classmethod
    def validate_weaknesses(cls, value: list[str]) -> list[str]:
        invalid = set(value) - WEAKNESS_TYPES
        if invalid:
            raise ValueError(f"不支援的弱點類型：{', '.join(sorted(invalid))}")
        return list(dict.fromkeys(value))


class StudentView(StudentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    class_id: str


class ClassCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    grade: str
    material_name: str = Field(default="自訂教材", max_length=120)
    weekly_schedule: str = Field(default="", max_length=120)
    objectives: list[str] = Field(default_factory=list, max_length=12)
    overall_level: str = Field(default="中等", max_length=30)
    learned_content: str = Field(default="", max_length=5000)
    common_errors: list[str] = Field(default_factory=list, max_length=20)
    teaching_preferences: str = Field(default="", max_length=3000)
    homework_days: int = Field(default=4, ge=1, le=7)
    homework_minutes: int = Field(default=30, ge=10, le=120)
    notes: str = Field(default="", max_length=3000)
    students: list[StudentCreate] = Field(default_factory=list, max_length=30)

    @field_validator("grade")
    @classmethod
    def validate_grade(cls, value: str) -> str:
        if value not in ALLOWED_GRADES:
            raise ValueError("年級必須為國一至高三")
        return value


class ClassUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    grade: str | None = None
    material_name: str | None = Field(default=None, max_length=120)
    weekly_schedule: str | None = Field(default=None, max_length=120)
    objectives: list[str] | None = None
    overall_level: str | None = Field(default=None, max_length=30)
    learned_content: str | None = Field(default=None, max_length=5000)
    common_errors: list[str] | None = None
    teaching_preferences: str | None = Field(default=None, max_length=3000)
    homework_days: int | None = Field(default=None, ge=1, le=7)
    homework_minutes: int | None = Field(default=None, ge=10, le=120)
    notes: str | None = Field(default=None, max_length=3000)

    @field_validator("grade")
    @classmethod
    def validate_grade(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_GRADES:
            raise ValueError("年級必須為國一至高三")
        return value


class ClassView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    grade: str
    material_name: str
    weekly_schedule: str
    objectives: list[str]
    overall_level: str
    learned_content: str
    common_errors: list[str]
    teaching_preferences: str
    homework_days: int
    homework_minutes: int
    notes: str
    students: list[StudentView] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MaterialMetadata(BaseModel):
    grade: str = Field(default="", max_length=20)
    chapter: str = Field(default="", max_length=120)
    topic: str = Field(default="", max_length=120)
    difficulty: str = Field(default="中等", max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=20)


class MaterialChunkView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    sequence: int
    text: str
    page_number: int | None
    paragraph_number: int | None


class MaterialView(MaterialMetadata):
    model_config = ConfigDict(from_attributes=True)
    id: str
    display_name: str
    media_type: str
    size_bytes: int
    parse_status: str
    extracted_text: str
    parse_error: str | None
    chunks: list[MaterialChunkView] = Field(default_factory=list)
    created_at: datetime


class SourceReference(BaseModel):
    source_material_id: str
    material_name: str
    chunk_id: str
    excerpt: str = Field(max_length=500)
    page_number: int | None = None
    paragraph_number: int | None = None


class Question(BaseModel):
    id: str | None = None
    type: Literal[
        "vocabulary", "multiple_choice", "cloze", "reading", "translation", "writing", "analysis"
    ]
    prompt: str = Field(min_length=1, max_length=5000)
    options: list[str] = Field(default_factory=list, max_length=10)
    answer: str = Field(default="", max_length=5000)
    explanation: str = Field(default="", max_length=5000)
    points: int = Field(default=1, ge=0, le=100)
    multiple_answers: bool = False
    reading_reference: str | None = None


class LessonBlock(BaseModel):
    id: str | None = None
    type: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=180)
    duration_minutes: int = Field(gt=0, le=180)
    instructions: str = Field(default="", max_length=5000)
    teacher_notes: str = Field(default="", max_length=5000)
    student_content: str = Field(default="", max_length=20000)
    questions: list[Question] = Field(default_factory=list, max_length=100)
    source_references: list[SourceReference] = Field(default_factory=list, max_length=20)
    locked: bool = False


class HomeworkDay(BaseModel):
    day: int = Field(ge=1, le=7)
    title: str
    estimated_minutes: int = Field(ge=5, le=120)
    vocabulary: list[str] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    review_note: str


class WeeklyQuiz(BaseModel):
    title: str
    suggested_minutes: int = Field(ge=10, le=120)
    total_points: int = Field(ge=1, le=200)
    questions: list[Question]


class ParentReport(BaseModel):
    homework_completion: str
    quiz_performance: str
    progress: str
    main_weaknesses: list[str]
    next_week_focus: list[str]
    teacher_notes: str


class ValidationIssue(BaseModel):
    code: str
    severity: Literal["info", "warning", "fatal"]
    message: str
    block_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class LessonPackageDraft(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    grade_band: str
    objectives: list[str] = Field(min_length=1, max_length=12)
    total_minutes: int = Field(gt=0, le=360)
    blocks: list[LessonBlock] = Field(min_length=1, max_length=20)
    homework_days: list[HomeworkDay] = Field(default_factory=list, max_length=7)
    weekly_quiz: WeeklyQuiz | None = None
    parent_report: ParentReport | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_declared_total_is_positive(self) -> LessonPackageDraft:
        if self.total_minutes <= 0:
            raise ValueError("總課堂時間必須大於零")
        return self


class GenerationRequest(BaseModel):
    class_id: str
    material_ids: list[str] = Field(min_length=1, max_length=20)
    lesson_date: date
    lesson_minutes: int = Field(default=120, ge=30, le=360)
    objectives: list[str] = Field(min_length=1, max_length=12)
    difficulty_ratio: dict[str, int] = Field(
        default_factory=lambda: {"基礎": 40, "中等": 40, "進階": 20}
    )
    question_types: dict[str, int] = Field(default_factory=dict)
    homework_days: int = Field(default=4, ge=1, le=7)
    include_weekly_quiz: bool = True
    include_parent_report: bool = True
    teacher_instructions: str = Field(default="", max_length=3000)
    modules: list[str] = Field(
        default_factory=lambda: [
            "作業與錯題檢查",
            "快速單字回想",
            "引導式克漏字",
            "獨立克漏字",
            "閱讀理解",
            "綜合挑戰",
            "長句拆解",
            "錯題訂正與總結",
        ],
        min_length=1,
        max_length=16,
    )

    @field_validator("difficulty_ratio")
    @classmethod
    def validate_ratio(cls, value: dict[str, int]) -> dict[str, int]:
        if sum(value.values()) != 100 or any(item < 0 for item in value.values()):
            raise ValueError("難度比例總和必須為 100")
        return value


class GenerationRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    lesson_package_id: str | None
    status: str
    progress: int
    progress_message: str
    attempt_count: int
    failure_reason: str | None
    provider: str
    model: str
    prompt_version: str
    duration_ms: int | None
    token_usage: dict[str, int] | None
    validation_summary: dict[str, Any] | None
    created_at: datetime


class BlockUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    duration_minutes: int | None = Field(default=None, gt=0, le=180)
    instructions: str | None = Field(default=None, max_length=5000)
    teacher_notes: str | None = Field(default=None, max_length=5000)
    student_content: str | None = Field(default=None, max_length=20000)
    questions: list[Question] | None = None


class BlockMove(BaseModel):
    direction: Literal["up", "down"]


class PackageView(BaseModel):
    id: str
    class_id: str
    title: str
    lesson_date: date
    status: str
    current_version: int
    total_minutes: int
    objectives: list[str]
    blocks: list[LessonBlock]
    homework_days: list[HomeworkDay]
    weekly_quiz: WeeklyQuiz | None
    parent_report: ParentReport | None
    validation_issues: list[ValidationIssue]
    created_at: datetime
    updated_at: datetime


class VersionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_number: int
    change_summary: str
    created_at: datetime
