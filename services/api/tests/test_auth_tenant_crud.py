from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def test_authentication_success_and_failure(client: TestClient, seeded: dict[str, Any]) -> None:
    del seeded
    success = client.post(
        "/api/auth/login", json={"email": "a@example.com", "password": "Password!123"}
    )
    assert success.status_code == 200
    assert success.json()["user"]["role"] == "owner"
    failure = client.post(
        "/api/auth/login", json={"email": "a@example.com", "password": "wrong-password"}
    )
    assert failure.status_code == 401
    assert "密碼" in failure.json()["detail"]


def test_role_authorization_blocks_teacher_member_creation(
    client: TestClient,
    teacher_a_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/organizations/current/members",
        headers=teacher_a_headers,
        json={
            "email": "new@example.com",
            "display_name": "New User",
            "password": "Password!123",
            "role": "teacher",
        },
    )
    assert response.status_code == 403


def test_cross_tenant_resources_cannot_be_read_modified_generated_or_downloaded(
    client: TestClient,
    owner_a_headers: dict[str, str],
    owner_b_headers: dict[str, str],
    seeded: dict[str, Any],
) -> None:
    package = client.get(
        f"/api/packages/{seeded['package_a']}", headers=owner_a_headers
    ).json()
    block_id = package["blocks"][0]["id"]

    assert (
        client.get(f"/api/classes/{seeded['class_a']}", headers=owner_b_headers).status_code == 404
    )
    assert (
        client.get(f"/api/materials/{seeded['material_a']}", headers=owner_b_headers).status_code
        == 404
    )
    assert (
        client.get(f"/api/packages/{seeded['package_a']}", headers=owner_b_headers).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/packages/{seeded['package_a']}/preview/student",
            headers=owner_b_headers,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/classes/{seeded['class_a']}",
            headers=owner_b_headers,
            json={"overall_level": "不應寫入"},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/materials/{seeded['material_a']}", headers=owner_b_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/generation",
            headers=owner_b_headers,
            json={
                "class_id": seeded["class_a"],
                "material_ids": [seeded["material_a"]],
                "lesson_date": "2026-08-20",
                "objectives": ["不應生成"],
            },
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/packages/{seeded['package_a']}/blocks/{block_id}",
            headers=owner_b_headers,
            json={"title": "不應寫入"},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/packages/{seeded['package_a']}/export/student.pdf",
            headers=owner_b_headers,
        ).status_code
        == 404
    )


def test_class_crud(client: TestClient, owner_a_headers: dict[str, str]) -> None:
    payload = {
        "name": "新班級",
        "grade": "高二",
        "material_name": "自訂教材",
        "weekly_schedule": "週五 19:00",
        "objectives": ["寫作"],
        "overall_level": "中等",
        "learned_content": "關係子句",
        "common_errors": ["時態"],
        "teaching_preferences": "範例後練習",
        "homework_days": 4,
        "homework_minutes": 30,
        "notes": "",
        "students": [{"alias": "S1", "weaknesses": ["寫作"], "notes": ""}],
    }
    created = client.post("/api/classes", headers=owner_a_headers, json=payload)
    assert created.status_code == 201, created.text
    class_id = created.json()["id"]
    assert created.json()["students"][0]["alias"] == "S1"
    updated = client.patch(
        f"/api/classes/{class_id}", headers=owner_a_headers, json={"overall_level": "中等偏強"}
    )
    assert updated.status_code == 200
    assert updated.json()["overall_level"] == "中等偏強"
    assert client.delete(f"/api/classes/{class_id}", headers=owner_a_headers).status_code == 204
    assert client.get(f"/api/classes/{class_id}", headers=owner_a_headers).status_code == 404
