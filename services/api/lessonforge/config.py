from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
