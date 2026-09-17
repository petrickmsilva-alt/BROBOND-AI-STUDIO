"""V3.4 — QualityRepository: the single persistence boundary of the domain.

Follows the convention ``campaign/campaign_repository.py`` (V3.3) and
``continuity/continuity_repository.py`` (V3.2) established:

* short-lived ``SessionLocal`` sessions per call, detached views before the
  session closes, module-level ``quality_repo`` singleton for the API;
* every read and write is workspace-scoped — a foreign id behaves as a 404,
  never a 403, so tenant ids are not enumerable;
* ``save_assessment`` writes the append-only ``quality_reports`` row **and**
  denormalises the latest verdict onto the ``assets`` row (ETAPA 6:
  ``quality_score``, ``quality_status``, ``quality_report``,
  ``quality_version``) in one transaction: the library badge and the report
  history can never disagree;
* ``record_decision`` stores what the operator chose (regenerar / upscale /
  aprovar) into the latest report's document — a record of a human decision,
  never an execution of it.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Asset
from .quality_engine import QualityAssessment
from .quality_models import (
    QualityReportRow,
    SCORE_MAX,
    SCORE_MIN,
    dumps_report,
    loads_report,
    utcnow,
)
from .quality_rules import QUALITY_STATUSES
from .quality_score import QualityValidationError

#: Operator decisions the domain records (ETAPA 5's three buttons). Recording
#: is all that happens — the sprint forbids executing any of them here.
DECISION_REGENERATE = "regenerate"
DECISION_UPSCALE = "upscale"
DECISION_APPROVE = "approve"
DECISIONS: tuple[str, ...] = (DECISION_REGENERATE, DECISION_UPSCALE, DECISION_APPROVE)


class UnknownAssetError(Exception):
    """The asset does not exist in this workspace (reads as a 404)."""


class UnknownReportError(Exception):
    """No quality report exists for this asset yet (reads as a 404)."""


@dataclass(frozen=True)
class QualityReportView:
    """A detached report row plus its parsed document."""

    id: str
    workspace_id: str
    asset_id: str
    kind: str
    overall_score: int
    status: str
    retry_recommended: bool
    upscale_recommended: bool
    report: dict
    engine_version: int
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "asset_id": self.asset_id,
            "kind": self.kind,
            "overall_score": self.overall_score,
            "status": self.status,
            "retry_recommended": self.retry_recommended,
            "upscale_recommended": self.upscale_recommended,
            "report": dict(self.report),
            "engine_version": self.engine_version,
            "created_at": self.created_at,
        }


def _view(row: QualityReportRow) -> QualityReportView:
    return QualityReportView(
        id=row.id,
        workspace_id=row.workspace_id,
        asset_id=row.asset_id,
        kind=row.kind,
        overall_score=row.overall_score,
        status=row.status,
        retry_recommended=bool(row.retry_recommended),
        upscale_recommended=bool(row.upscale_recommended),
        report=loads_report(row.report_json),
        engine_version=row.engine_version,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


class QualityRepository:
    """Workspace-scoped persistence over ``quality_reports`` and ``assets``."""

    # ----------------------------------------------------------------- lookups

    def asset_for(self, workspace_id: str, asset_id: str) -> Asset:
        """The asset, or UnknownAssetError — foreign tenants read as absent."""

        with SessionLocal() as db:
            asset = db.get(Asset, asset_id)
            if not asset or asset.workspace_id != workspace_id:
                raise UnknownAssetError(f"asset {asset_id!r} not found")
            db.expunge(asset)
            return asset

    # ------------------------------------------------------------------ writes

    def save_assessment(
        self, workspace_id: str, asset_id: str, assessment: QualityAssessment
    ) -> QualityReportView:
        """Persist one engine run: append the report, refresh the asset badge."""

        if not SCORE_MIN <= assessment.overall_score <= SCORE_MAX:
            raise QualityValidationError(
                f"overall score {assessment.overall_score} is outside {SCORE_MIN}–{SCORE_MAX}"
            )
        if assessment.status not in QUALITY_STATUSES:
            raise QualityValidationError(f"unknown quality status {assessment.status!r}")

        document = assessment.to_dict()
        with SessionLocal() as db:
            asset = db.get(Asset, asset_id)
            if not asset or asset.workspace_id != workspace_id:
                raise UnknownAssetError(f"asset {asset_id!r} not found")
            row = QualityReportRow(
                id=str(uuid4()),
                workspace_id=workspace_id,
                asset_id=asset_id,
                kind=assessment.kind,
                overall_score=assessment.overall_score,
                status=assessment.status,
                retry_recommended=int(assessment.retry_recommended),
                upscale_recommended=int(assessment.upscale_recommended),
                report_json=dumps_report(document),
                engine_version=assessment.engine_version,
                created_at=utcnow(),
            )
            db.add(row)
            # ETAPA 6 — the asset carries its latest verdict, denormalised.
            asset.quality_score = assessment.overall_score
            asset.quality_status = assessment.status
            asset.quality_report = row.report_json
            asset.quality_version = assessment.engine_version
            db.commit()
            db.refresh(row)
            return _view(row)

    def record_decision(
        self, workspace_id: str, asset_id: str, decision: str
    ) -> QualityReportView:
        """Store the operator's choice on the latest report. Nothing executes."""

        if decision not in DECISIONS:
            raise QualityValidationError(
                f"unknown decision {decision!r}; expected one of {', '.join(DECISIONS)}"
            )
        with SessionLocal() as db:
            asset = db.get(Asset, asset_id)
            if not asset or asset.workspace_id != workspace_id:
                raise UnknownAssetError(f"asset {asset_id!r} not found")
            row = db.scalars(
                select(QualityReportRow)
                .where(
                    QualityReportRow.workspace_id == workspace_id,
                    QualityReportRow.asset_id == asset_id,
                )
                .order_by(QualityReportRow.created_at.desc(), QualityReportRow.id.desc())
            ).first()
            if row is None:
                raise UnknownReportError(f"asset {asset_id!r} has no quality report")
            document = loads_report(row.report_json)
            document["operator_decision"] = decision
            document["operator_decided_at"] = utcnow().isoformat()
            row.report_json = dumps_report(document)
            asset.quality_report = row.report_json
            db.commit()
            db.refresh(row)
            return _view(row)

    # ------------------------------------------------------------------- reads

    def latest_report(self, workspace_id: str, asset_id: str) -> QualityReportView:
        with SessionLocal() as db:
            asset = db.get(Asset, asset_id)
            if not asset or asset.workspace_id != workspace_id:
                raise UnknownAssetError(f"asset {asset_id!r} not found")
            row = db.scalars(
                select(QualityReportRow)
                .where(
                    QualityReportRow.workspace_id == workspace_id,
                    QualityReportRow.asset_id == asset_id,
                )
                .order_by(QualityReportRow.created_at.desc(), QualityReportRow.id.desc())
            ).first()
            if row is None:
                raise UnknownReportError(f"asset {asset_id!r} has no quality report")
            return _view(row)

    def history(self, workspace_id: str, asset_id: str) -> list[QualityReportView]:
        """Every assessment of one asset, newest first. Absent asset → 404."""

        with SessionLocal() as db:
            asset = db.get(Asset, asset_id)
            if not asset or asset.workspace_id != workspace_id:
                raise UnknownAssetError(f"asset {asset_id!r} not found")
            rows = db.scalars(
                select(QualityReportRow)
                .where(
                    QualityReportRow.workspace_id == workspace_id,
                    QualityReportRow.asset_id == asset_id,
                )
                .order_by(QualityReportRow.created_at.desc(), QualityReportRow.id.desc())
            ).all()
            return [_view(row) for row in rows]


#: Module-level singleton, matching `campaign_repo` and `continuity_repo`.
quality_repo = QualityRepository()
