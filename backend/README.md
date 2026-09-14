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

Worker readiness is exposed at `GET /api/v1/system/readiness`; it reports CUDA, FFmpeg, Torch, Diffusers, Redis client and Celery availability before a real render. Copy `.env.example` to `.env` and enable providers only after the readiness response is healthy.

FFmpeg capability is exposed at `GET /api/v1/system/media`. Local video assets can be exported to H.264 MP4 with `POST /api/v1/assets/{asset_id}/export` using `quality` (`720p`, `1080p`, `2k`, `4k`) and `fps` (`24` or `30`). Video model options are exposed at `GET /api/v1/models/video`. For local Wan inference, install `requirements-video-gpu.txt`; the Celery worker will use `BROBOND_VIDEO_MODEL_ID` and persist the resulting MP4 as a workspace Asset.

Conditioning options are exposed at `GET /api/v1/models/conditioning`. Image jobs accept `controlnet`, `controlnet_scale`, `ip_adapter_scale`, and `reference_asset_id`; the worker validates workspace ownership before passing local references to a compatible provider pipeline. Reference preprocessing is available at `POST /api/v1/assets/{asset_id}/conditioning` for `edges`, `depth`, and `tile`; `pose` is reserved for the GPU OpenPose worker. The Celery task `brobond.preprocess_reference` provides the asynchronous provider boundary; install `requirements-preprocess-gpu.txt` for OpenPose and GPU preprocessing dependencies.

Persona training is validated through `POST /api/v1/personas/{persona_id}/train` and requires 20–50 reference asset IDs. Each execution is persisted as a `TrainingRun` and can be read from `GET /api/v1/personas/{persona_id}/training/{run_id}` or streamed through `WS /api/v1/personas/{persona_id}/training/events/{run_id}`. The Celery `train_lora` task prepares `metadata.jsonl`, validates image files, and calls the configured trainer without ever fabricating a model file. For a GPU worker, install `requirements-training-gpu.txt`, set `BROBOND_TRAINING_ENABLED=true`, `BROBOND_QUEUE_ENABLED=true`, and configure `BROBOND_LORA_TRAINER_COMMAND`.

## Test

```bash
PYTHONPATH=backend pytest backend/tests -q
```

The current store is intentionally in-memory. The API boundary is stable so the next infrastructure step can replace it with SQLAlchemy repositories and Celery tasks.
