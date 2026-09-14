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

Storage mode is local by default: uploaded files are written to `media/` and exposed through the API. For MinIO, set `BROBOND_STORAGE_ENABLED=true`, configure `BROBOND_MINIO_ENDPOINT`, `BROBOND_MINIO_ACCESS_KEY`, `BROBOND_MINIO_SECRET_KEY`, and create the configured bucket before uploading. Asset endpoints are `POST /api/v1/assets/upload` and `GET /api/v1/assets`.

Image inference is orchestration-only by default. On a CUDA worker, install `requirements-gpu.txt`, set `BROBOND_INFERENCE_ENABLED=true`, and use the Celery worker. The FLUX provider then loads weights from `BROBOND_WEIGHTS_DIR`, uploads generated output through the active storage adapter, creates an `Asset` record, and exposes the final URL on the job. Authenticated generation requests carry the user's workspace into this output pipeline.

FFmpeg capability is exposed at `GET /api/v1/system/media`. Local video assets can be exported to H.264 MP4 with `POST /api/v1/assets/{asset_id}/export` using `quality` (`720p`, `1080p`, `2k`, `4k`) and `fps` (`24` or `30`).

## Test

```bash
PYTHONPATH=backend pytest backend/tests -q
```

The current store is intentionally in-memory. The API boundary is stable so the next infrastructure step can replace it with SQLAlchemy repositories and Celery tasks.
