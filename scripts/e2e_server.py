from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = (
    f"sqlite+aiosqlite:///{(ROOT / 'artifacts' / f'e2e-{os.getpid()}.db').as_posix()}"
)
os.environ["UPLOAD_DIR"] = str(ROOT / "artifacts" / "e2e-uploads")
os.environ["EXPORT_DIR"] = str(ROOT / "artifacts" / "e2e-exports")
os.environ["JWT_SECRET"] = "e2e-only-secret-change-before-production-32chars"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_MODEL"] = "mock-lesson-v1"
os.environ["EMBEDDING_PROVIDER"] = "disabled"
os.environ["IN_PROCESS_JOBS"] = "true"

import uvicorn  # noqa: E402

from lessonforge.main import app  # noqa: E402
from seed import seed  # noqa: E402


def main() -> None:
    asyncio.run(seed())
    uvicorn.run(app, host="127.0.0.1", port=8100, log_level="warning")


if __name__ == "__main__":
    main()
