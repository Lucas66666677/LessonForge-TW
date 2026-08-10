from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from . import models as _models
from .api import router
from .config import get_settings
from .database import create_schema

_ = _models


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    del app
    settings = get_settings()
    settings.ensure_directories()
    if settings.database_url.startswith("sqlite"):
        await create_schema()
    yield


app = FastAPI(
    title="LessonForge TW API",
    version=__version__,
    description="台灣補習班 AI 教材生產系統 API",
    lifespan=lifespan,
)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

request_windows: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def basic_rate_limit(request: Request, call_next: object) -> object:
    settings = get_settings()
    if request.url.path in {"/health", "/docs", "/openapi.json"}:
        return await call_next(request)  # type: ignore[operator]
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = request_windows[key]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_minute:
        return JSONResponse(status_code=429, content={"detail": "請求過於頻繁，請稍後再試"})
    window.append(now)
    return await call_next(request)  # type: ignore[operator]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "lessonforge-api", "version": __version__}


app.include_router(router)
