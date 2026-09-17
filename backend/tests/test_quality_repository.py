"""V3.4 ETAPA 7 — QualityRepository (Persistence).

Every test owns a fresh workspace against the shared test database (the same
isolation the campaign and continuity suites use). Pinned here: the report
and the asset badge commit together, history is append-only, decisions are
recorded onto the latest report without executing anything, and foreign
tenants read as absent (404 semantics), never as forbidden.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

# The quality tables come from the Alembic bootstrap that runs at app import.
from app.main import app  # noqa: F401
from app.db import SessionLocal
from app.models import Asset
from app.quality.quality_engine import MediaFacts, QUALITY_ENGINE_VERSION, QualityEngine
from app.quality.quality_models import QualityReportRow, dumps_report, loads_report
from app.quality.quality_repository import (
    DECISION_APPROVE,
    DECISION_REGENERATE,
    DECISION_UPSCALE,
    DECISIONS,
    QualityRepository,
    UnknownAssetError,
    UnknownReportError,
)
from app.quality.quality_score import (
    CRITERION_EYES,
    CRITERION_FACE,
    CRITERION_HANDS,
    KIND_IMAGE,
    QualityValidationError,
)


@pytest.fixture()
def ws() -> str:
    return f"ws-{uuid4().hex}"


@pytest.fixture()
def repo() -> QualityRepository:
    return QualityRepository()


@pytest.fixture()
def asset_id(ws: str) -> str:
    with SessionLocal() as db:
        asset = Asset(workspace_id=ws, name="render.png", kind="image", object_key=f"{ws}/render.png")
        db.add(asset)
        db.commit()
        return asset.id


def _assessment(*, face: float = 90.0, hands: float = 88.0, eyes: float = 92.0):
    engine = QualityEngine()
    facts = MediaFacts(kind=KIND_IMAGE, width=1920, height=1080, aspect_ratio_expected=16 / 9)
    return engine.assess(
        facts, signals={CRITERION_FACE: face, CRITERION_HANDS: hands, CRITERION_EYES: eyes}
    )


# ------------------------------------------------------------------ save + read


def test_saving_persists_the_report_and_badges_the_asset_together(repo, ws, asset_id) -> None:
    assessment = _assessment()
    view = repo.save_assessment(ws, asset_id, assessment)

    assert view.asset_id == asset_id
    assert view.overall_score == assessment.overall_score
    assert view.status == assessment.status
    assert view.engine_version == QUALITY_ENGINE_VERSION
    assert view.report["criteria"]  # the full document rode along

    with SessionLocal() as db:
        asset = db.get(Asset, asset_id)
        assert asset.quality_score == assessment.overall_score
        assert asset.quality_status == assessment.status
        assert asset.quality_version == QUALITY_ENGINE_VERSION
        assert loads_report(asset.quality_report)["overall_score"] == assessment.overall_score


def test_latest_report_returns_what_was_saved(repo, ws, asset_id) -> None:
    saved = repo.save_assessment(ws, asset_id, _assessment())
    read = repo.latest_report(ws, asset_id)
    assert read.id == saved.id
    assert read.to_dict()["overall_score"] == saved.overall_score


def test_reassessing_appends_history_and_updates_the_badge(repo, ws, asset_id) -> None:
    repo.save_assessment(ws, asset_id, _assessment(face=20.0, hands=15.0, eyes=20.0))
    second = repo.save_assessment(ws, asset_id, _assessment(face=97.0, hands=96.0, eyes=98.0))

    history = repo.history(ws, asset_id)
    assert len(history) == 2
    assert history[0].id == second.id  # newest first
    assert repo.latest_report(ws, asset_id).id == second.id

    with SessionLocal() as db:
        asset = db.get(Asset, asset_id)
        assert asset.quality_score == second.overall_score  # badge follows the latest


def test_history_is_append_only_nothing_is_rewritten(repo, ws, asset_id) -> None:
    first = repo.save_assessment(ws, asset_id, _assessment(face=20.0, hands=15.0, eyes=20.0))
    repo.save_assessment(ws, asset_id, _assessment(face=97.0, hands=96.0, eyes=98.0))
    with SessionLocal() as db:
        row = db.get(QualityReportRow, first.id)
        assert row is not None
        assert row.overall_score == first.overall_score  # the old opinion survives


# -------------------------------------------------------------------- decisions


def test_the_three_operator_decisions_are_the_etapa_5_buttons() -> None:
    assert DECISIONS == (DECISION_REGENERATE, DECISION_UPSCALE, DECISION_APPROVE)


def test_recording_a_decision_stamps_the_latest_report(repo, ws, asset_id) -> None:
    repo.save_assessment(ws, asset_id, _assessment())
    view = repo.record_decision(ws, asset_id, DECISION_APPROVE)
    assert view.report["operator_decision"] == DECISION_APPROVE
    assert view.report["operator_decided_at"]
    # The asset's denormalised report carries the stamp too.
    with SessionLocal() as db:
        asset = db.get(Asset, asset_id)
        assert loads_report(asset.quality_report)["operator_decision"] == DECISION_APPROVE


def test_recording_a_decision_executes_nothing(repo, ws, asset_id) -> None:
    """The sprint's rule: recommend, never act. A regenerate decision must not
    change the score, the status, or the number of reports."""

    saved = repo.save_assessment(ws, asset_id, _assessment())
    view = repo.record_decision(ws, asset_id, DECISION_REGENERATE)
    assert view.id == saved.id  # same report, only annotated
    assert view.overall_score == saved.overall_score
    assert view.status == saved.status
    assert len(repo.history(ws, asset_id)) == 1


def test_an_unknown_decision_is_refused(repo, ws, asset_id) -> None:
    repo.save_assessment(ws, asset_id, _assessment())
    with pytest.raises(QualityValidationError, match="unknown decision"):
        repo.record_decision(ws, asset_id, "ship-it")


def test_a_decision_without_a_report_is_a_missing_report(repo, ws, asset_id) -> None:
    with pytest.raises(UnknownReportError):
        repo.record_decision(ws, asset_id, DECISION_UPSCALE)


# ----------------------------------------------------------------- tenant rules


def test_a_foreign_workspace_reads_the_asset_as_absent(repo, ws, asset_id) -> None:
    foreign = f"ws-{uuid4().hex}"
    repo.save_assessment(ws, asset_id, _assessment())
    for call in (
        lambda: repo.asset_for(foreign, asset_id),
        lambda: repo.save_assessment(foreign, asset_id, _assessment()),
        lambda: repo.latest_report(foreign, asset_id),
        lambda: repo.history(foreign, asset_id),
        lambda: repo.record_decision(foreign, asset_id, DECISION_APPROVE),
    ):
        with pytest.raises(UnknownAssetError):
            call()


def test_a_nonexistent_asset_reads_as_absent(repo, ws) -> None:
    with pytest.raises(UnknownAssetError):
        repo.latest_report(ws, "no-such-asset")


def test_an_unassessed_asset_has_a_missing_report_not_an_empty_one(repo, ws, asset_id) -> None:
    with pytest.raises(UnknownReportError):
        repo.latest_report(ws, asset_id)
    assert repo.history(ws, asset_id) == []


def test_asset_for_returns_the_detached_row(repo, ws, asset_id) -> None:
    asset = repo.asset_for(ws, asset_id)
    assert asset.id == asset_id
    assert asset.workspace_id == ws


# ------------------------------------------------------------------- documents


def test_reports_round_trip_and_corrupt_rows_read_as_empty() -> None:
    assert loads_report(dumps_report({"a": 1})) == {"a": 1}
    assert loads_report(None) == {}
    assert loads_report("not-json{") == {}
    assert loads_report("[1,2]") == {}  # a list is not a report


def test_dumps_report_refuses_non_documents() -> None:
    with pytest.raises(QualityValidationError, match="must be an object"):
        dumps_report(["not", "a", "dict"])  # type: ignore[arg-type]
    with pytest.raises(QualityValidationError, match="not JSON-serialisable"):
        dumps_report({"bad": object()})


def test_saving_an_out_of_contract_assessment_is_refused(repo, ws, asset_id) -> None:
    from dataclasses import replace

    good = _assessment()
    with pytest.raises(QualityValidationError, match="outside"):
        repo.save_assessment(ws, asset_id, replace(good, overall_score=101))
    with pytest.raises(QualityValidationError, match="unknown quality status"):
        repo.save_assessment(ws, asset_id, replace(good, status="stellar"))
