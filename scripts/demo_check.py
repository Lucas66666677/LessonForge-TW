from __future__ import annotations

import argparse
import json
import os
import secrets
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "demo_material.md"


def require(response: httpx.Response, expected: int | tuple[int, ...]) -> httpx.Response:
    accepted = (expected,) if isinstance(expected, int) else expected
    if response.status_code not in accepted:
        try:
            body = json.dumps(response.json(), ensure_ascii=False)
        except ValueError:
            body = response.text[:500]
        raise RuntimeError(
            f"{response.request.method} {response.request.url} -> "
            f"{response.status_code}, expected {accepted}: {body}"
        )
    return response


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)


def run(base_url: str, output_dir: Path) -> dict[str, Any]:
    owner_email = os.getenv("DEMO_OWNER_EMAIL", "owner@demo.lessonforge.tw")
    owner_password = os.getenv("DEMO_OWNER_PASSWORD", "")
    if not owner_password:
        raise RuntimeError("DEMO_OWNER_PASSWORD must be set for the local Demo check")
    api = f"{base_url.rstrip('/')}/api"
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    output_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120.0) as client:
        login = require(
            client.post(
                f"{api}/auth/login",
                json={
                    "email": owner_email,
                    "password": owner_password,
                },
            ),
            200,
        ).json()
        original_token = login["access_token"]

        organization = require(
            client.post(
                f"{api}/organizations",
                headers=auth(original_token),
                json={"name": f"Demo Check 補習班 {stamp}"},
            ),
            201,
        ).json()
        token = organization["access_token"]
        headers = auth(token)

        member = require(
            client.post(
                f"{api}/organizations/current/members",
                headers=headers,
                json={
                    "email": f"teacher-{stamp}@demo.lessonforge.tw",
                    "display_name": "Demo Check 老師",
                    "password": secrets.token_urlsafe(24),
                    "role": "teacher",
                },
            ),
            201,
        ).json()

        class_group = require(
            client.post(
                f"{api}/classes",
                headers=headers,
                json={
                    "name": f"核心流程驗收班 {stamp[-6:]}",
                    "grade": "國三",
                    "material_name": "自製英文教材",
                    "weekly_schedule": "週三 19:00–21:00",
                    "objectives": ["掌握上下文線索", "說明閱讀推論"],
                    "overall_level": "中等",
                    "learned_content": "已學過基礎五大句型與過去式。",
                    "common_errors": ["單字拼寫", "閱讀細節定位"],
                    "teaching_preferences": "先獨立作答，再引導說明證據。",
                    "homework_days": 4,
                    "homework_minutes": 30,
                    "notes": "僅使用匿名學生代號。",
                    "students": [
                        {"alias": "A-01", "weaknesses": ["單字", "文法"], "notes": "拼寫易混淆"},
                        {
                            "alias": "B-02",
                            "weaknesses": ["閱讀理解", "長句解析"],
                            "notes": "需加強證據定位",
                        },
                    ],
                },
            ),
            201,
        ).json()

        cross_tenant = client.get(
            f"{api}/classes/{class_group['id']}", headers=auth(original_token)
        )
        require(cross_tenant, 404)

        material = require(
            client.post(
                f"{api}/materials",
                headers=headers,
                files={"file": ("demo_material.md", FIXTURE.read_bytes(), "text/markdown")},
                data={
                    "grade": "國三",
                    "chapter": "Evidence in Everyday Decisions",
                    "topic": "Context and evidence",
                    "difficulty": "中等",
                    "tags": "reading,evidence,demo-check",
                },
            ),
            201,
        ).json()
        if material["parse_status"] != "ready" or not material["chunks"]:
            raise RuntimeError("教材未完成解析或沒有 chunks")

        generation = require(
            client.post(
                f"{api}/generation",
                headers=headers,
                json={
                    "class_id": class_group["id"],
                    "material_ids": [material["id"]],
                    "lesson_date": "2026-08-20",
                    "lesson_minutes": 120,
                    "objectives": ["辨認主張與證據", "運用上下文判斷詞義"],
                    "difficulty_ratio": {"基礎": 40, "中等": 40, "進階": 20},
                    "question_types": {"vocabulary": 8, "cloze": 6, "reading": 4},
                    "homework_days": 4,
                    "include_weekly_quiz": True,
                    "include_parent_report": True,
                    "teacher_instructions": "答錯時要引導回到原文定位。",
                    "modules": [
                        "作業與錯題檢查",
                        "快速單字回想",
                        "引導式克漏字",
                        "獨立克漏字",
                        "閱讀理解",
                        "綜合挑戰",
                        "長句拆解",
                        "錯題訂正與總結",
                    ],
                },
            ),
            202,
        ).json()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            state = require(
                client.get(f"{api}/generation/{generation['id']}", headers=headers), 200
            ).json()
            if state["status"] == "completed":
                break
            if state["status"] == "failed":
                raise RuntimeError(f"生成失敗：{state['failure_reason']}")
            time.sleep(0.25)
        else:
            raise RuntimeError("等待生成任務逾時")

        package_id = state["lesson_package_id"]
        package = require(client.get(f"{api}/packages/{package_id}", headers=headers), 200).json()
        if len(package["blocks"]) < 2:
            raise RuntimeError("生成的教材區塊不足")
        locked_id = package["blocks"][0]["id"]
        other_id = package["blocks"][1]["id"]
        edited_content = package["blocks"][0]["student_content"] + "\n老師已完成 Demo 人工編輯。"
        package = require(
            client.patch(
                f"{api}/packages/{package_id}/blocks/{locked_id}",
                headers=headers,
                json={"student_content": edited_content},
            ),
            200,
        ).json()
        package = require(
            client.post(f"{api}/packages/{package_id}/blocks/{locked_id}/lock", headers=headers),
            200,
        ).json()
        locked_snapshot = next(block for block in package["blocks"] if block["id"] == locked_id)
        require(
            client.post(
                f"{api}/packages/{package_id}/blocks/{other_id}/regenerate", headers=headers
            ),
            200,
        )
        package = require(client.get(f"{api}/packages/{package_id}", headers=headers), 200).json()
        locked_after = next(block for block in package["blocks"] if block["id"] == locked_id)
        if locked_after != locked_snapshot:
            raise RuntimeError("重新生成其他區塊時，鎖定區塊被修改")
        locked_regen = client.post(
            f"{api}/packages/{package_id}/blocks/{locked_id}/regenerate", headers=headers
        )
        require(locked_regen, 409)

        approved = require(
            client.post(f"{api}/packages/{package_id}/approve", headers=headers), 200
        ).json()
        if approved["status"] != "approved":
            raise RuntimeError("教材包未正確核准")

        exports: dict[str, int] = {}
        pdf_contents: dict[str, bytes] = {}
        for variant in ("student", "teacher"):
            for file_format in ("pdf", "docx"):
                response = require(
                    client.get(
                        f"{api}/packages/{package_id}/export/{variant}.{file_format}",
                        headers=headers,
                    ),
                    200,
                )
                destination = output_dir / f"demo-check-{variant}.{file_format}"
                destination.write_bytes(response.content)
                exports[destination.name] = len(response.content)
                if file_format == "pdf":
                    pdf_contents[variant] = response.content

        student_text = pdf_text(pdf_contents["student"])
        teacher_text = pdf_text(pdf_contents["teacher"])
        for marker in ("答案：", "解析：", "教師備註："):
            if marker in student_text:
                raise RuntimeError(f"學生版 PDF 洩漏了 {marker}")
            if marker not in teacher_text:
                raise RuntimeError(f"教師版 PDF 缺少 {marker}")

        return {
            "organization": organization["user"]["organization_name"],
            "teacher_member": member["email"],
            "class_id": class_group["id"],
            "material_id": material["id"],
            "generation_id": generation["id"],
            "package_id": package_id,
            "locked_block_preserved": True,
            "cross_tenant_denied": True,
            "student_answer_leak": False,
            "teacher_answers_present": True,
            "exports": exports,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the LessonForge TW local core-flow check")
    parser.add_argument(
        "--base-url",
        default=os.getenv("LESSONFORGE_API_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "exports")
    args = parser.parse_args()
    result = run(args.base_url, args.output_dir)
    print(json.dumps({"status": "PASS", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
