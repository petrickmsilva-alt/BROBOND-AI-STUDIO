.PHONY: install dev api worker test build infra preflight

install:
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt

infra:
	docker compose up -d postgres redis minio

api:
	PYTHONPATH=backend .venv/bin/uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000

worker:
	PYTHONPATH=backend .venv/bin/celery -A app.queue.celery_app worker --loglevel=info --workdir=backend

test:
	PYTHONPATH=backend .venv/bin/pytest backend/tests -q

build:
	npm run build

preflight:
	curl -fsS http://localhost:8000/api/v1/system/readiness | python -m json.tool

dev:
	npm run dev
