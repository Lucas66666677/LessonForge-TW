from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings
from .schemas import (
    HomeworkDay,
    LessonBlock,
    LessonPackageDraft,
    ParentReport,
    Question,
    SourceReference,
    WeeklyQuiz,
)

TModel = TypeVar("TModel", bound=BaseModel)


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderResponse:
    content: dict[str, Any]
    token_usage: dict[str, int] | None = None


class LLMProvider(ABC):
    name: str

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = settings.llm_model

    @abstractmethod
    async def generate_json(self, *, prompt: str, schema: dict[str, Any]) -> ProviderResponse:
        raise NotImplementedError

    async def repair_json(
        self, *, invalid_content: Any, validation_error: str, schema: dict[str, Any]
    ) -> ProviderResponse:
        repair_prompt = (
            "你是 JSON 修復器。只輸出符合 JSON Schema 的 JSON，不得省略或偷偷丟棄欄位。\n"
            f"驗證錯誤：{validation_error}\nJSON Schema：{json.dumps(schema, ensure_ascii=False)}\n"
            f"原始輸出：{json.dumps(invalid_content, ensure_ascii=False)}"
        )
        return await self.generate_json(prompt=repair_prompt, schema=schema)


class MockLLMProvider(LLMProvider):
    name = "mock"

    async def generate_json(self, *, prompt: str, schema: dict[str, Any]) -> ProviderResponse:
        del schema
        return ProviderResponse(
            content={"mock": True, "prompt_digest": prompt[:40]}, token_usage={"total_tokens": 0}
        )

    def build_lesson(
        self,
        *,
        grade: str,
        objectives: list[str],
        lesson_minutes: int,
        modules: list[str],
        homework_days: int,
        include_quiz: bool,
        include_report: bool,
        references: list[SourceReference],
    ) -> LessonPackageDraft:
        durations = allocate_minutes(lesson_minutes, len(modules))
        source = references[:2]
        senior = grade.startswith("高")
        vocabulary = (
            ["hypothesis", "correlation", "implication", "counterargument", "synthesize"]
            if senior
            else ["context", "evidence", "interpret", "contrast", "conclusion"]
        )
        blocks: list[LessonBlock] = []
        for index, (title, duration) in enumerate(zip(modules, durations, strict=True)):
            question_type = "cloze" if "克漏字" in title else "multiple_choice"
            if "閱讀" in title:
                question_type = "reading"
            if "長句" in title:
                question_type = "analysis"
            thinking_action = "分析論證與推論" if senior else "依據課文脈絡"
            prompt = (
                f"第 {index + 1} 題（{title}）：{thinking_action}，"
                f"以「{vocabulary[index % len(vocabulary)]}」完成此模組的判讀任務。"
            )
            questions = [
                Question(
                    type=question_type,
                    prompt=prompt,
                    options=[
                        vocabulary[index % 5],
                        vocabulary[(index + 1) % 5],
                        vocabulary[(index + 2) % 5],
                    ],
                    answer=vocabulary[index % 5],
                    explanation=(
                        "答案需結合論點、證據與反方論述推論。"
                        if senior
                        else "答案可由上下文線索與詞性判斷。"
                    ),
                    reading_reference=source[0].chunk_id
                    if question_type == "reading" and source
                    else None,
                )
            ]
            blocks.append(
                LessonBlock(
                    type=f"module_{index + 1}",
                    title=title,
                    duration_minutes=duration,
                    instructions="先個別作答，再由老師引導比較線索與策略。",
                    teacher_notes=(
                        "引導學生檢驗證據與推論之間的邏輯距離。"
                        if senior
                        else "留意學生是否能說明理由；答錯時回到原文定位。"
                    ),
                    student_content=(
                        "閱讀教材節錄，分析主張、證據、反驚與言外之意。"
                        if senior
                        else "閱讀以下教材節錄並完成題目。"
                    )
                    + (f"\n{source[0].excerpt}" if source else ""),
                    questions=questions,
                    source_references=source,
                )
            )

        homework = [
            HomeworkDay(
                day=day,
                title=f"Day {day}｜單字與閱讀複習",
                estimated_minutes=30,
                vocabulary=vocabulary[:4],
                questions=[
                    Question(
                        type="vocabulary",
                        prompt=f"請用 {vocabulary[0]} 寫出第 {day} 個例句。",
                        answer=(f"Day {day} sample answer uses {vocabulary[0]} correctly."),
                        explanation="例句需有完整主詞與動詞，並符合單字語意。",
                    )
                ],
                review_note="完成後用 3 分鐘口頭回想今天的四個單字。",
            )
            for day in range(1, homework_days + 1)
        ]
        quiz = None
        if include_quiz:
            quiz_questions = [
                Question(
                    type="vocabulary",
                    prompt="選出 evidence 的正確中文意思。",
                    options=["證據", "情境", "結論"],
                    answer="證據",
                    explanation="evidence 表示支持主張的證據。",
                    points=10,
                ),
                Question(
                    type="cloze",
                    prompt="The writer uses data as ____ for the claim.",
                    options=["evidence", "contrast", "context"],
                    answer="evidence",
                    explanation="資料用來支持主張。",
                    points=10,
                ),
                Question(
                    type="reading",
                    prompt="What is the writer's main conclusion?",
                    options=["Practice helps", "Sleep is optional", "Evidence is useless"],
                    answer="Practice helps",
                    explanation="結尾句重申練習的重要性。",
                    points=10,
                    reading_reference=source[0].chunk_id if source else "mock-reading",
                ),
            ]
            quiz = WeeklyQuiz(
                title="本週英文能力檢核",
                suggested_minutes=25,
                total_points=30,
                questions=quiz_questions,
            )
        report = None
        if include_report:
            report = ParentReport(
                homework_completion="待老師於課後填寫",
                quiz_performance="待本週測驗後填寫",
                progress="能逐步使用上下文判斷單字與句意。",
                main_weaknesses=["拼字準確度", "閱讀細節定位"],
                next_week_focus=["核心單字複習", "閱讀證據定位"],
                teacher_notes="本內容為 AI 草稿，請老師依實際學習表現調整。",
            )
        return LessonPackageDraft(
            title=f"{grade}英文｜脈絡閱讀與應用",
            grade_band=grade,
            objectives=objectives,
            total_minutes=lesson_minutes,
            blocks=blocks,
            homework_days=homework,
            weekly_quiz=quiz,
            parent_report=report,
        )


def allocate_minutes(total: int, count: int) -> list[int]:
    if count <= 0:
        raise ValueError("至少需要一個教材模組")
    base, remainder = divmod(total, count)
    return [base + (1 if index < remainder else 0) for index in range(count)]


class OllamaProvider(LLMProvider):
    name = "ollama"

    async def generate_json(self, *, prompt: str, schema: dict[str, Any]) -> ProviderResponse:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.2},
        }
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.settings.llm_base_url.rstrip('/')}/api/chat", json=payload
                )
                response.raise_for_status()
                body = response.json()
                content = json.loads(body["message"]["content"])
                usage = {
                    "prompt_tokens": int(body.get("prompt_eval_count", 0)),
                    "completion_tokens": int(body.get("eval_count", 0)),
                }
                return ProviderResponse(content=content, token_usage=usage)
        except (httpx.HTTPError, KeyError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ProviderError(f"無法從 Ollama 取得有效結果：{error}") from error


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    async def generate_json(self, *, prompt: str, schema: dict[str, Any]) -> ProviderResponse:
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "lessonforge", "schema": schema},
            },
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.settings.llm_base_url.rstrip('/')}/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
                content = json.loads(body["choices"][0]["message"]["content"])
                return ProviderResponse(content=content, token_usage=body.get("usage"))
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, TypeError) as error:
            raise ProviderError(f"OpenAI 相容服務回傳失敗：{error}") from error


class GeminiProvider(LLMProvider):
    name = "gemini"

    async def generate_json(self, *, prompt: str, schema: dict[str, Any]) -> ProviderResponse:
        if not self.settings.llm_api_key:
            raise ProviderError("Gemini Provider 需要設定 LLM_API_KEY")
        url = f"{self.settings.llm_base_url.rstrip('/')}/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "temperature": 0.2,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    url, params={"key": self.settings.llm_api_key}, json=payload
                )
                response.raise_for_status()
                body = response.json()
                content = json.loads(body["candidates"][0]["content"]["parts"][0]["text"])
                return ProviderResponse(content=content, token_usage=body.get("usageMetadata"))
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, TypeError) as error:
            raise ProviderError(f"Gemini 回傳失敗：{error}") from error


def get_provider(settings: Settings) -> LLMProvider:
    providers: dict[str, type[LLMProvider]] = {
        "mock": MockLLMProvider,
        "ollama": OllamaProvider,
        "openai_compatible": OpenAICompatibleProvider,
        "gemini": GeminiProvider,
    }
    return providers[settings.llm_provider](settings)


async def generate_validated(
    provider: LLMProvider,
    *,
    prompt: str,
    model_type: type[TModel],
    repair_attempts: int,
) -> tuple[TModel, dict[str, int] | None]:
    schema = model_type.model_json_schema()
    response = await provider.generate_json(prompt=prompt, schema=schema)
    content: Any = response.content
    total_usage = response.token_usage
    for attempt in range(repair_attempts + 1):
        try:
            return model_type.model_validate(content), total_usage
        except ValidationError as error:
            if attempt >= repair_attempts:
                raise ProviderError(
                    f"模型輸出在 {repair_attempts + 1} 次驗證後仍不符合 schema：{error}"
                ) from error
            response = await provider.repair_json(
                invalid_content=content, validation_error=str(error), schema=schema
            )
            content = response.content
            if response.token_usage:
                total_usage = {
                    key: (total_usage or {}).get(key, 0) + value
                    for key, value in response.token_usage.items()
                }
    raise ProviderError("模型輸出驗證流程未能完成")
