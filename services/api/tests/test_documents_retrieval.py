from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient

from lessonforge.config import get_settings
from lessonforge.database import SessionLocal
from lessonforge.document_parser import DocumentParseError, detect_media_type, parse_document
from lessonforge.retrieval import retrieve_chunks


def docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph("第一段 English content.")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_document_detection_and_parsing() -> None:
    data = docx_bytes()
    media_type = detect_media_type(
        data,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "lesson.docx",
    )
    parsed = parse_document(data, media_type)
    assert parsed.segments[0].paragraph_number == 1
    assert "English" in parsed.text
    markdown = parse_document(b"# Title\n\nEvidence supports claims.", "text/markdown")
    assert len(markdown.segments) == 2


def test_mime_and_extension_mismatch_rejected() -> None:
    with pytest.raises(DocumentParseError, match="副檔名"):
        detect_media_type(b"plain text", "text/plain", "malware.pdf")


def test_upload_validates_content_and_returns_chunks(
    client: TestClient,
    owner_a_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/materials",
        headers=owner_a_headers,
        files={"file": ("lesson.md", b"# Lesson\n\nEvidence matters.", "text/markdown")},
        data={"grade": "國三", "chapter": "Unit 3", "topic": "Evidence", "tags": "閱讀,證據"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["parse_status"] == "ready"
    assert response.json()["chunks"]
    mismatch = client.post(
        "/api/materials",
        headers=owner_a_headers,
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    assert mismatch.status_code == 415


@pytest.mark.asyncio
async def test_retrieval_filters_tenant_and_material(seeded: dict[str, Any]) -> None:
    settings = get_settings().model_copy(update={"embedding_provider": "disabled"})
    async with SessionLocal() as session:
        result = await retrieve_chunks(
            session,
            settings=settings,
            organization_id=seeded["org_a"],
            material_ids=[seeded["material_a"]],
            query="evidence claim context",
            grade="國三",
        )
    assert result.mode == "full_text"
    assert result.references
    assert {item.source_material_id for item in result.references} == {seeded["material_a"]}
