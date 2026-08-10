from __future__ import annotations

import math
import re
from dataclasses import dataclass

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import MaterialChunk, SourceMaterial
from .schemas import SourceReference


@dataclass(frozen=True)
class RetrievalResult:
    references: list[SourceReference]
    mode: str


async def embed_text(text: str, settings: Settings) -> list[float] | None:
    if settings.embedding_provider != "ollama":
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/api/embed",
                json={"model": settings.embedding_model, "input": text[:8000]},
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings", [])
            return [float(item) for item in embeddings[0]] if embeddings else None
    except (httpx.HTTPError, ValueError, TypeError, IndexError):
        return None


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return -1.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else -1.0


async def retrieve_chunks(
    session: AsyncSession,
    *,
    settings: Settings,
    organization_id: str,
    material_ids: list[str],
    query: str,
    grade: str | None = None,
    chapter: str | None = None,
    tags: list[str] | None = None,
    limit: int = 8,
) -> RetrievalResult:
    statement = (
        select(MaterialChunk, SourceMaterial)
        .join(SourceMaterial, SourceMaterial.id == MaterialChunk.source_material_id)
        .where(
            MaterialChunk.organization_id == organization_id,
            SourceMaterial.organization_id == organization_id,
            MaterialChunk.source_material_id.in_(material_ids),
            SourceMaterial.parse_status == "ready",
        )
    )
    if grade:
        statement = statement.where(or_(SourceMaterial.grade == grade, SourceMaterial.grade == ""))
    if chapter:
        statement = statement.where(
            or_(MaterialChunk.chapter == chapter, SourceMaterial.chapter == chapter)
        )

    rows = [(chunk, material) for chunk, material in (await session.execute(statement)).all()]
    if tags:
        tag_set = set(tags)
        rows = [
            row
            for row in rows
            if tag_set.intersection(set(row[1].tags or []) | set(row[0].tags or []))
        ]

    query_embedding = await embed_text(query, settings)
    if query_embedding and any(chunk.embedding for chunk, _ in rows):
        ranked = sorted(
            rows,
            key=lambda row: cosine_similarity(query_embedding, row[0].embedding or []),
            reverse=True,
        )[:limit]
        mode = "semantic"
    else:
        terms = {term.lower() for term in re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,}", query)}

        def lexical_score(row: tuple[MaterialChunk, SourceMaterial]) -> tuple[int, int]:
            text = row[0].text.lower()
            return (sum(text.count(term) for term in terms), -row[0].sequence)

        ranked = sorted(rows, key=lexical_score, reverse=True)[:limit]
        mode = "full_text"

    references = [
        SourceReference(
            source_material_id=material.id,
            material_name=material.display_name,
            chunk_id=chunk.id,
            excerpt=chunk.text[:500],
            page_number=chunk.page_number,
            paragraph_number=chunk.paragraph_number,
        )
        for chunk, material in ranked
    ]
    return RetrievalResult(references=references, mode=mode)
