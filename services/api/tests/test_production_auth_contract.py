"""Production must refuse a sign-in path that anyone can walk through.

`Settings.jwt_secret` was checked for length and nothing else, and its default
-- `local-demo-secret-change-before-production-32-chars` -- is fifty characters
long, so the only validator in place passed it. A production container that
never received `JWT_SECRET` therefore booted on a signing key published in this
repository, answered the Render health gate with `{"status": "ok"}`, and issued
access tokens that any reader of the repo could forge. `verify_token` would
have accepted every one of them, for any user, in any tenant.

Nothing detected that. `/health` is a literal, so it says `ok` regardless;
`scripts/check_demo_credentials.py` scans repository files, not the environment
a container actually starts with; and `render.yaml` declaring
`JWT_SECRET: generateValue: true` is a declaration about a dashboard, not a
check the process performs.

These checks build `Settings` objects directly. No account is created, no
credential is used, no token is minted, and no network request is made. The
placeholder values they assert against are already public in this repository --
that is the entire reason they are rejected.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from lessonforge.config import PUBLIC_JWT_SECRETS, Settings


REPO_ROOT = Path(__file__).resolve().parents[3]

#: Long enough to satisfy the length rule, and not written down anywhere.
UNIQUE_SECRET = "f4c1" * 12

#: Where a placeholder signing key is allowed to appear, and the pattern that
#: finds it there. If a new one is added to a file not listed here, the tuple in
#: `config.py` can go stale without this test noticing -- so a new home for a
#: placeholder belongs in this map at the same time.
PLACEHOLDER_SOURCES: dict[str, str] = {
    ".env.example": r"^JWT_SECRET=(.+)$",
    "scripts/e2e_server.py": r'os\.environ\["JWT_SECRET"\]\s*=\s*"([^"]+)"',
    "services/api/tests/conftest.py": r'os\.environ\["JWT_SECRET"\]\s*=\s*"([^"]+)"',
    "services/api/lessonforge/config.py": r'^\s*jwt_secret:\s*str\s*=\s*"([^"]+)"',
}


def _production(**overrides: object) -> Settings:
    """A production settings object with everything else left at its default."""

    return Settings(app_env="production", jwt_secret=UNIQUE_SECRET, **overrides)


def _placeholders_written_in_the_repo() -> dict[str, str]:
    found: dict[str, str] = {}
    for relative, pattern in PLACEHOLDER_SOURCES.items():
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        match = re.search(pattern, text, re.MULTILINE)
        assert match, f"no JWT_SECRET literal found in {relative}"
        found[relative] = match.group(1).strip()
    return found


@pytest.mark.parametrize("secret", PUBLIC_JWT_SECRETS)
def test_production_refuses_a_published_signing_key(secret: str) -> None:
    """Fail on the way up, rather than issuing forgeable tokens."""

    with pytest.raises(ValidationError, match="placeholder published"):
        Settings(app_env="production", jwt_secret=secret)


def test_production_accepts_a_unique_secret() -> None:
    """Guards the guard: the rule has to be passable, not merely strict."""

    assert _production().app_env == "production"


def test_the_length_rule_alone_would_have_admitted_every_one_of_them() -> None:
    """Why this contract exists rather than a longer minimum length.

    Each published placeholder clears the 32-character floor comfortably. A
    stricter length rule would not have caught any of them.
    """

    assert all(len(secret) >= 32 for secret in PUBLIC_JWT_SECRETS)


def test_every_placeholder_written_in_the_repo_is_one_production_rejects() -> None:
    """The anti-drift check: a new placeholder must not slip past the tuple.

    `config.py` carries a hand-maintained list. This re-derives it from the
    files that actually contain the values, so adding a fifth placeholder
    somewhere and forgetting `PUBLIC_JWT_SECRETS` fails here rather than in
    production.
    """

    written = _placeholders_written_in_the_repo()
    missing = {
        source: value
        for source, value in written.items()
        if value not in PUBLIC_JWT_SECRETS
    }
    assert not missing, (
        f"placeholder signing keys not in PUBLIC_JWT_SECRETS: {sorted(missing)}"
    )


def test_the_placeholder_scan_reads_more_than_one_file() -> None:
    """Guards the guard: an empty scan would satisfy the check above vacuously."""

    written = _placeholders_written_in_the_repo()
    assert len(written) == len(PLACEHOLDER_SOURCES)
    assert len(set(written.values())) >= 4


@pytest.mark.parametrize(
    "overrides",
    [
        {"demo_owner_password": "any-non-empty-value"},
        {"demo_teacher_password": "any-non-empty-value"},
        {
            "demo_owner_password": "any-non-empty-value",
            "demo_teacher_password": "any-non-empty-value",
        },
    ],
)
def test_production_refuses_seeded_demo_credentials(overrides: dict[str, str]) -> None:
    """`scripts/seed.py` creates those accounts only when the passwords are set.

    Setting them in production restores exactly the shared credential that was
    removed in #3 -- an account no user owns and nobody rotates.
    """

    with pytest.raises(ValidationError, match="must be empty"):
        _production(**overrides)


def test_the_demo_passwords_default_to_empty() -> None:
    """Guards the guard: the rule above must not fire on an untouched config."""

    settings = _production()
    assert settings.demo_owner_password == ""
    assert settings.demo_teacher_password == ""


@pytest.mark.parametrize("app_env", ["development", "test"])
@pytest.mark.parametrize("secret", PUBLIC_JWT_SECRETS)
def test_non_production_environments_keep_their_placeholders(
    app_env: str, secret: str
) -> None:
    """This suite runs on one of them, and `scripts/e2e_server.py` on another.

    A rule about production must not make local development or CI unstartable.
    """

    assert Settings(app_env=app_env, jwt_secret=secret).jwt_secret == secret
