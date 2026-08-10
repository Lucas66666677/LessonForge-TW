.PHONY: bootstrap dev stop migrate seed lint typecheck test e2e build eval eval-live demo-check

bootstrap:
	npm ci
	python -m pip install -e ".[dev]"

dev:
	docker compose up --build

stop:
	docker compose down

migrate:
	python -m alembic -c services/api/alembic.ini upgrade head

seed:
	python scripts/seed.py

lint:
	npm run lint
	python -m ruff check services scripts evals

typecheck:
	npm run typecheck
	python -m mypy services/api/lessonforge

test:
	npm run test:unit
	python -m pytest

e2e:
	npm run e2e

build:
	npm run build

eval:
	python evals/run_eval.py

eval-live:
	LLM_PROVIDER=ollama python evals/run_eval.py --live

demo-check:
	python scripts/demo_check.py
