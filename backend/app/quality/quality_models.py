"""V3.4 — Quality Engine: persistence models.

One table holds the full history of assessments:

* ``quality_reports`` — one row per engine run over one asset: the overall
  score, the status band, the whole report document (criteria, issues,
  strengths, suggestions, facts) and the engine version that produced it.
  History is append-only: re-assessing an asset writes a new row, it never
  rewrites an old opinion.

The *latest* verdict is also denormalised onto the ``assets`` row itself
(ETAPA 6: ``quality_score``, ``quality_status``, ``quality_report``,
``quality_version``), so the Asset Library can filter and badge without a
join. ``quality_repository`` writes both in one transaction.

Conventions inherited from the codebase (``campaign_models`` V3.3):
``String(36)`` uuid primary keys, ``workspace_id`` as an indexed plain
reference (no DB-level foreign keys), naive-UTC timestamps, JSON documents
in ``Text`` columns — the same SQLite/Postgres-portable convention.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .quality_score import QualityValidationError

#: Bounds of the persisted score column, shared with the score module's
#: contract (0–100). Redeclared as integers because the column is an integer.
SCORE_MIN = 0
SCORE_MAX = 100

#: An asset that was never assessed has no status; the column is nullable and
#: this sentinel never reaches the database.
UNASSESSED = None


def utcnow() -> datetime:
    """Naive UTC timestamp, matching the repository convention."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def dumps_report(report: dict) -> str:
    """Serialise a report document, rejecting non-JSON loudly."""

    if not isinstance(report, dict):
        raise QualityValidationError("report must be an object")
    try:
        return json.dumps(report, ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise QualityValidationError(f"report is not JSON-serialisable: {error}") from error


def loads_report(raw: str | None) -> dict:
    """Parse a stored report, defensively (a corrupt row reads as empty)."""

    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


class QualityReportRow(Base):
    """One engine run over one asset. Append-only by convention."""

    __tablename__ = "quality_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    overall_score: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    retry_recommended: Mapped[int] = mapped_column(Integer, default=0)
    upscale_recommended: Mapped[int] = mapped_column(Integer, default=0)
    report_json: Mapped[str] = mapped_column(Text, default="{}")
    engine_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
