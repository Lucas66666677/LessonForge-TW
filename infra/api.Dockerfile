FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk chromium && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY services ./services
RUN pip install --no-cache-dir .
COPY . .
CMD ["sh", "-c", "python -m alembic -c services/api/alembic.ini upgrade head && python scripts/seed.py && uvicorn lessonforge.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
