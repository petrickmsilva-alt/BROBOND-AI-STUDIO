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

## Test

```bash
PYTHONPATH=backend pytest backend/tests -q
```

The current store is intentionally in-memory. The API boundary is stable so the next infrastructure step can replace it with SQLAlchemy repositories and Celery tasks.
