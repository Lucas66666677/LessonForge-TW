from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from lessonforge.config import Settings, get_settings
from lessonforge.providers import (
    LLMProvider,
    MockLLMProvider,
    ProviderResponse,
    generate_validated,
    get_provider,
)
from lessonforge.schemas import LessonBlock, LessonPackageDraft, Question, SourceReference
from lessonforge.validators import validate_lesson_draft, validate_locked_blocks


def test_render_postgres_url_uses_asyncpg_driver() -> None:
    settings = Settings(
        database_url="postgresql://lessonforge:secret@db.internal/lessonforge",
    )
    assert settings.database_url == (
        "postgresql+asyncpg://lessonforge:secret@db.internal/lessonforge"
    )


class TinySchema(BaseModel):
    value: int


class RepairingProvider(LLMProvider):
    name = "repair-test"

    def __init__(self) -> None:
        super().__init__(get_settings())
        self.repairs = 0

    async def generate_json(self, *, prompt: str, schema: dict[str, Any]) -> ProviderResponse:
        del prompt, schema
        return ProviderResponse(content={"value": "invalid"})

    async def repair_json(
        self, *, invalid_content: Any, validation_error: str, schema: dict[str, Any]
    ) -> ProviderResponse:
        del invalid_content, validation_error, schema
        self.repairs += 1
        return ProviderResponse(content={"value": 42})


@pytest.mark.asyncio
async def test_provider_contract_and_schema_repair() -> None:
    settings = get_settings().model_copy(update={"llm_provider": "mock"})
    assert isinstance(get_provider(settings), MockLLMProvider)
    provider = RepairingProvider()
    result, _ = await generate_validated(
        provider, prompt="test", model_type=TinySchema, repair_attempts=2
    )
    assert result.value == 42
    assert provider.repairs == 1


def valid_draft() -> LessonPackageDraft:
    reference = SourceReference(
        source_material_id="material-a",
        material_name="a.md",
        chunk_id="chunk-a",
        excerpt="Evidence supports a claim.",
        paragraph_number=1,
    )
    return LessonPackageDraft(
        title="Valid lesson",
        grade_band="國三",
        objectives=["閱讀理解"],
        total_minutes=120,
        blocks=[
            LessonBlock(
                id="block-a",
                type="reading",
                title="閱讀",
                duration_minutes=120,
                student_content="Text",
                questions=[
                    Question(
                        type="reading",
                        prompt="What is the evidence?",
                        options=["A", "B", "C"],
                        answer="A",
                        explanation="A is correct.",
                        reading_reference="chunk-a",
                    )
                ],
                source_references=[reference],
            )
        ],
    )


def test_deterministic_validators_cover_answer_options_time_and_source() -> None:
    draft = valid_draft()
    assert (
        validate_lesson_draft(draft, expected_minutes=120, allowed_material_ids={"material-a"})
        == []
    )
    draft.blocks[0].duration_minutes = 100
    draft.blocks[0].questions[0].options = ["A", "A"]
    draft.blocks[0].questions[0].answer = "D"
    draft.blocks[0].source_references[0].source_material_id = "foreign"
    codes = {
        issue.code
        for issue in validate_lesson_draft(
            draft, expected_minutes=120, allowed_material_ids={"material-a"}
        )
    }
    assert {
        "duration_mismatch",
        "insufficient_options",
        "duplicate_options",
        "answer_not_in_options",
        "foreign_source_reference",
    } <= codes


def test_locked_block_validator_detects_and_preserves() -> None:
    original = valid_draft().blocks
    original[0].locked = True
    same = [original[0].model_copy(deep=True)]
    assert validate_locked_blocks(original, same) == []
    same[0].title = "Changed"
    assert validate_locked_blocks(original, same)[0].code == "locked_block_modified"
