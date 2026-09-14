# BROBOND API

## Run

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

Open the interactive contract at `http://localhost:8000/docs`.

The default database is local SQLite (`brobond.db`). Set `BROBOND_DATABASE_URL` to a PostgreSQL URL and `BROBOND_JWT_SECRET` in `.env` for a hosted environment. Authentication endpoints are `/api/v1/auth/register`, `/api/v1/auth/login`, and `/api/v1/auth/me`.

Queue mode is disabled by default for offline development. Start Redis and set `BROBOND_QUEUE_ENABLED=true` to send tasks through Celery. Queue observability is available through `POST /api/v1/jobs/{job_id}/cancel` and `WS /api/v1/queue/events/{job_id}`.

## Test

```bash
PYTHONPATH=backend pytest backend/tests -q
```

The current store is intentionally in-memory. The API boundary is stable so the next infrastructure step can replace it with SQLAlchemy repositories and Celery tasks.
