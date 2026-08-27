"""The Demo-account kill switch must actually deactivate, and must not write on a dry run.

Removing the credentials from the source and rebuilding the frontend stops
advertising them; it does not stop them working. `scripts/seed.py`'s
`ensure_user` never rewrites an existing `password_hash`, so the seeded rows
keep whatever hash they were created with. `is_active` is the thing both entry
points check (`lessonforge/api.py` login, `lessonforge/dependencies.py` session
lookup), which is why this script flips that and not the password.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from lessonforge.database import SessionLocal
from lessonforge.models import User
from lessonforge.security import hash_password

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_script():
    path = REPO_ROOT / "scripts" / "disable_demo_accounts.py"
    spec = importlib.util.spec_from_file_location("_lf_disable_demo_accounts", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


@pytest.fixture
async def demo_users() -> list[str]:
    emails = ["owner@demo.lessonforge.tw", "teacher@demo.lessonforge.tw"]
    async with SessionLocal() as session:
        for email in emails:
            session.add(
                User(
                    email=email,
                    display_name=email.split("@")[0],
                    password_hash=hash_password("a-local-password-not-the-public-one"),
                )
            )
        await session.commit()
    return emails


async def _is_active(email: str) -> bool:
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
    return user.is_active


async def test_dry_run_is_the_default_and_writes_nothing(demo_users) -> None:
    await script.run(script._parse_args([]))

    for email in demo_users:
        assert await _is_active(email) is True


async def test_apply_deactivates_every_demo_account(demo_users) -> None:
    await script.run(script._parse_args(["--apply"]))

    for email in demo_users:
        assert await _is_active(email) is False


async def test_reactivate_restores_access(demo_users) -> None:
    await script.run(script._parse_args(["--apply"]))
    await script.run(script._parse_args(["--apply", "--reactivate"]))

    for email in demo_users:
        assert await _is_active(email) is True


async def test_missing_account_is_not_an_error() -> None:
    exit_code = await script.run(script._parse_args(["--apply"]))

    assert exit_code == 0


async def test_explicit_email_overrides_the_configured_demo_addresses(demo_users) -> None:
    await script.run(script._parse_args(["--apply", "--email", "owner@demo.lessonforge.tw"]))

    assert await _is_active("owner@demo.lessonforge.tw") is False
    assert await _is_active("teacher@demo.lessonforge.tw") is True
