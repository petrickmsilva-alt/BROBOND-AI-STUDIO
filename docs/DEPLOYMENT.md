# Deployment

BROBOND AI STUDIO ships two web services (Next.js UI + FastAPI API) and one
managed PostgreSQL database, described end to end by [`render.yaml`](../render.yaml).
Every push to `main` auto-deploys both services (`autoDeployTrigger: commit`).

```bash
# One-time blueprint deploy (Render CLI):
render login
render blueprint deploy --path render.yaml
```

## Mandatory Environment Variables

These variables **must** be set on the API service (`brobond-ai-api`) in any
hosted environment. The blueprint wires them automatically; a service created
by hand must set them in the dashboard.

| Variable | Purpose | Notes |
| --- | --- | --- |
| `BROBOND_DATABASE_URL` | PostgreSQL connection string. | Render's `postgres://...` format is accepted and normalized to `postgresql+psycopg://`. Also read from `DATABASE_URL` as a fallback (see priority below). |
| `BROBOND_CORS_ORIGINS` | Comma-separated list of browser origins allowed by the CORS middleware. | Must include the public URL of the web service, e.g. `https://brobond-studio-web.onrender.com`. |
| `BROBOND_JWT_SECRET` | HS256 signing key for access tokens. | Minimum 32 bytes (RFC 7518); the API refuses to boot with a shorter value. Use `generateValue: true` in the blueprint or a strong random string. |

### Database URL read priority (PR009.4)

The API resolves its database connection in strict order:

1. `BROBOND_DATABASE_URL` — the explicit, project-prefixed variable. Always wins.
2. `DATABASE_URL` — the conventional name PaaS providers inject.
3. `sqlite:///./brobond.db` — **local development only.**

### Production never starts on SQLite

On Render (the platform sets `RENDER=true` on every service), the API
**refuses to boot** with a `RuntimeError` if neither `BROBOND_DATABASE_URL`
nor `DATABASE_URL` resolves to PostgreSQL. A SQLite file inside the container
is ephemeral — it would silently wipe all users, personas, jobs and assets on
every deploy or restart, so failing fast is the only safe behavior.

At startup the deploy log always prints one unmissable banner line:

```
[brobond] 🟢 PostgreSQL Connected
```

or, in local development:

```
[brobond] 🔴 SQLite Development Mode
```

If a deploy fails with `Refusing to start on Render with a SQLite database`,
attach the managed Postgres: in the Render dashboard, add
`BROBOND_DATABASE_URL` on `brobond-ai-api` pointing at the
`brobond-studio-db` connection string, or redeploy from the blueprint which
links it via `fromDatabase`.

## Optional / feature-flag variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `BROBOND_QUEUE_ENABLED` | `false` | Celery/Redis queue. Requires `BROBOND_REDIS_URL` when enabled. |
| `BROBOND_STORAGE_ENABLED` | `false` | MinIO/S3 object storage (`BROBOND_MINIO_*`). |
| `BROBOND_INFERENCE_ENABLED` | `false` | Real GPU providers instead of orchestration-only mode. |
| `BROBOND_TRAINING_ENABLED` | `false` | LoRA training pipeline. |

The web service (`brobond-studio-web`) needs only `NEXT_PUBLIC_API_URL`,
baked in at build time and pointing at the API's public URL.

## Migrations

The schema is owned by Alembic (`alembic upgrade head` runs automatically at
API startup — `app.main._bootstrap_database`). Deployments never run
migrations by hand and never modify migration history.
