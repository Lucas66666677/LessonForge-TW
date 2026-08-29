from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Signing keys that are written down in this repository, and are therefore
#: public. A process that signs access tokens with one of these is not
#: authenticating anybody: any reader of the repo can mint a token for any user
#: in any tenant, and `verify_token` will accept it. Every one of them is longer
#: than 32 characters, so the length rule below passes them -- which is exactly
#: why length is not a sufficient check.
#:
#: Append to this tuple whenever another placeholder appears anywhere in the
#: repo. `test_production_auth_contract.py` re-derives the list from the files
#: that carry them and fails if one is missing here.
PUBLIC_JWT_SECRETS: tuple[str, ...] = (
    # services/api/lessonforge/config.py -- the default below
    "local-demo-secret-change-before-production-32-chars",
    # .env.example
    "change-this-to-at-least-32-random-characters",
    # scripts/e2e_server.py
    "e2e-only-secret-change-before-production-32chars",
    # services/api/tests/conftest.py
    "pytest-secret-that-is-longer-than-32-characters",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    api_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "sqlite+aiosqlite:///./lessonforge.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "local-demo-secret-change-before-production-32-chars"
    access_token_minutes: int = 480
    upload_max_mb: int = 20
    upload_dir: Path = Path("artifacts/uploads")
    export_dir: Path = Path("artifacts/exports")
    rate_limit_per_minute: int = 120

    llm_provider: Literal["mock", "ollama", "openai_compatible", "gemini"] = "mock"
    llm_model: str = "qwen3:8b"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: str = ""
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    log_raw_ai_content: bool = False
    schema_repair_attempts: int = 2
    in_process_jobs: bool = True

    demo_owner_email: str = "owner@demo.lessonforge.tw"
    demo_owner_password: str = ""
    demo_teacher_email: str = "teacher@demo.lessonforge.tw"
    demo_teacher_password: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @field_validator("jwt_secret")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET 必須至少 32 個字元")
        return value

    @model_validator(mode="after")
    def validate_production_sign_in(self) -> Settings:
        """Refuse to start production on a sign-in path anyone can use.

        Nothing here was checked before. `jwt_secret` was validated for length
        alone, and every placeholder in the repository is long enough to pass,
        so a production container that never received `JWT_SECRET` would boot
        on the default above, answer `/health` with `{"status": "ok"}`, and
        issue access tokens signed with a key published on GitHub.

        The demo passwords are the same failure from the other direction: they
        default to empty, and `scripts/seed.py` only creates those accounts
        when they are set. Setting them in production restores a shared
        credential that no user owns and nobody rotates -- the incident
        `scripts/check_demo_credentials.py` exists because of. That checker
        scans the repository; this one covers the environment, which it
        cannot see.

        Neither message repeats the value it rejected.
        """
        if self.app_env != "production":
            return self
        if self.jwt_secret in PUBLIC_JWT_SECRETS:
            raise ValueError(
                "JWT_SECRET is a placeholder published in this repository, so "
                "the tokens it signs are forgeable by anyone. Production must "
                "set a unique secret -- note that leaving JWT_SECRET unset "
                "selects the development default rather than failing."
            )
        if self.demo_owner_password or self.demo_teacher_password:
            raise ValueError(
                "DEMO_OWNER_PASSWORD and DEMO_TEACHER_PASSWORD must be empty "
                "in production: a seeded account with a shared password is a "
                "sign-in path no user owns and nobody rotates."
            )
        return self

    @property
    def upload_max_bytes(self) -> int:
        return self.upload_max_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def ensure_directories(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
