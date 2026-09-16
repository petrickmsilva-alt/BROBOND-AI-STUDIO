"""V3.2: repository over the continuity tables.

The single persistence boundary for the Character Continuity Engine,
following the convention ``graph/graph_repository.py`` (V3.1) established:

* short-lived ``SessionLocal`` sessions per call, detached views before the
  session closes, module-level ``continuity_repo`` singleton for the API;
* every read and write is workspace-scoped — a foreign id behaves as a 404,
  never a 403, so tenant ids are not enumerable;
* lock writes upsert: re-locking the same scope replaces the payload and
  bumps ``version``, so the fingerprint history of an episode lives in the
  episode snapshot, not in the lock row;
* episode creation conflicts (same persona/campaign/episode twice) raise
  ``ContinuityRepositoryError`` (mapped to 409), because an episode number
  is an address, not a draft.

Reads resolve through the fallback chain — the episode's own lock, then the
campaign default, then the persona-global default — so identity and voice
(persona-global, stored under campaign ``"default"``) resolve in every
campaign without being duplicated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from sqlalchemy import func, select

from ..db import SessionLocal
from .continuity_models import (
    DEFAULT_CAMPAIGN,
    DEFAULT_EPISODE,
    ContinuityEpisode,
    ContinuityLock,
    dumps_payload,
    loads_payload,
    normalize_lock_type,
    utcnow,
)
from .identity_lock import (
    ContinuityValidationError,
    normalize_campaign,
    normalize_episode,
    normalize_persona_id,
)


class ContinuityRepositoryError(Exception):
    """Raised when a write cannot proceed (episode number taken)."""


@dataclass(frozen=True)
class ContinuityLockView:
    """A detached lock row: scope, payload and fingerprint."""

    lock_type: str
    persona_id: str
    campaign_id: str
    #: The scope the lock was written under; None means campaign default.
    episode: int | None
    payload: Mapping[str, object] = field(default_factory=dict)
    fingerprint: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "lock_type": self.lock_type,
            "persona_id": self.persona_id,
            "campaign_id": self.campaign_id,
            "episode": self.episode,
            "payload": dict(self.payload),
            "fingerprint": self.fingerprint,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ContinuityEpisodeView:
    """A detached episode row: number, title and frozen snapshot."""

    id: str
    workspace_id: str
    persona_id: str
    campaign_id: str
    episode: int
    title: str = ""
    notes: str = ""
    snapshot: Mapping[str, object] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "persona_id": self.persona_id,
            "campaign_id": self.campaign_id,
            "episode": self.episode,
            "title": self.title,
            "notes": self.notes,
            "snapshot": dict(self.snapshot),
            "created_at": self.created_at,
        }


def lock_view(row: ContinuityLock) -> ContinuityLockView:
    """Map a lock row onto its detached view."""

    return ContinuityLockView(
        lock_type=row.lock_type,
        persona_id=row.persona_id,
        campaign_id=row.campaign_id,
        episode=None if row.episode == DEFAULT_EPISODE else row.episode,
        payload=loads_payload(row.payload_json),
        fingerprint=row.fingerprint,
        version=row.version,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def episode_view(row: ContinuityEpisode) -> ContinuityEpisodeView:
    """Map an episode row onto its detached view."""

    return ContinuityEpisodeView(
        id=row.id,
        workspace_id=row.workspace_id,
        persona_id=row.persona_id,
        campaign_id=row.campaign_id,
        episode=row.episode,
        title=row.title,
        notes=row.notes,
        snapshot=loads_payload(row.snapshot_json),
        created_at=row.created_at.isoformat(),
    )


class ContinuityRepository:
    """Upsert + fallback reads for locks, frozen history for episodes."""

    # ------------------------------------------------------------------ locks

    def upsert_lock(
        self,
        workspace_id: str,
        *,
        lock_type: str,
        persona_id: str,
        campaign_id: str | None = DEFAULT_CAMPAIGN,
        episode: int | None = None,
        payload: dict | None = None,
        fingerprint: str = "",
    ) -> ContinuityLockView:
        """Write a lock, replacing the same scope and bumping ``version``."""

        kind = normalize_lock_type(lock_type)
        cleaned_persona = normalize_persona_id(persona_id)
        cleaned_campaign = normalize_campaign(DEFAULT_CAMPAIGN if campaign_id is None else campaign_id)
        cleaned_episode = normalize_episode(episode)
        stored_episode = DEFAULT_EPISODE if cleaned_episode is None else cleaned_episode
        stored_payload = dumps_payload({} if payload is None else payload)
        cleaned_fingerprint = fingerprint.strip() if isinstance(fingerprint, str) else ""
        if not cleaned_fingerprint:
            raise ContinuityValidationError("fingerprint must not be blank")
        with SessionLocal() as db:
            row = db.scalar(
                select(ContinuityLock).where(
                    ContinuityLock.workspace_id == workspace_id,
                    ContinuityLock.persona_id == cleaned_persona,
                    ContinuityLock.campaign_id == cleaned_campaign,
                    ContinuityLock.episode == stored_episode,
                    ContinuityLock.lock_type == kind,
                )
            )
            if row is None:
                row = ContinuityLock(
                    workspace_id=workspace_id,
                    persona_id=cleaned_persona,
                    campaign_id=cleaned_campaign,
                    episode=stored_episode,
                    lock_type=kind,
                    payload_json=stored_payload,
                    fingerprint=cleaned_fingerprint,
                    version=1,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
                db.add(row)
            else:
                row.payload_json = stored_payload
                row.fingerprint = cleaned_fingerprint
                row.version = row.version + 1
                row.updated_at = utcnow()
            db.commit()
            db.refresh(row)
            view = lock_view(row)
            db.expunge(row)
            return view

    def get_lock(
        self,
        workspace_id: str,
        lock_type: str,
        persona_id: str,
        campaign_id: str | None = DEFAULT_CAMPAIGN,
        episode: int | None = None,
    ) -> ContinuityLockView | None:
        """Return the most specific lock through the fallback chain.

        Episode's own lock first, then the campaign default, then the
        persona-global default — ``None`` when nothing is locked. The chain
        is what lets identity and voice resolve everywhere while wardrobe,
        location and vehicle override per episode.
        """

        kind = normalize_lock_type(lock_type)
        cleaned_persona = normalize_persona_id(persona_id)
        cleaned_campaign = normalize_campaign(DEFAULT_CAMPAIGN if campaign_id is None else campaign_id)
        cleaned_episode = normalize_episode(episode)
        candidates = _fallback_chain(cleaned_campaign, cleaned_episode)
        with SessionLocal() as db:
            for candidate_campaign, candidate_episode in candidates:
                row = db.scalar(
                    select(ContinuityLock).where(
                        ContinuityLock.workspace_id == workspace_id,
                        ContinuityLock.persona_id == cleaned_persona,
                        ContinuityLock.campaign_id == candidate_campaign,
                        ContinuityLock.episode == candidate_episode,
                        ContinuityLock.lock_type == kind,
                    )
                )
                if row is not None:
                    view = lock_view(row)
                    db.expunge(row)
                    return view
            return None

    def list_locks(
        self,
        workspace_id: str,
        *,
        persona_id: str | None = None,
        campaign_id: str | None = None,
    ) -> list[ContinuityLockView]:
        """List the workspace's locks, optionally filtered, stably ordered."""

        with SessionLocal() as db:
            query = select(ContinuityLock).where(ContinuityLock.workspace_id == workspace_id)
            if persona_id:
                query = query.where(ContinuityLock.persona_id == persona_id.strip())
            if campaign_id:
                query = query.where(ContinuityLock.campaign_id == campaign_id.strip())
            query = query.order_by(
                ContinuityLock.persona_id,
                ContinuityLock.campaign_id,
                ContinuityLock.episode,
                ContinuityLock.lock_type,
            )
            rows = list(db.scalars(query))
            views = [lock_view(row) for row in rows]
            for row in rows:
                db.expunge(row)
            return views

    # --------------------------------------------------------------- episodes

    def create_episode(
        self,
        workspace_id: str,
        *,
        persona_id: str,
        campaign_id: str | None = DEFAULT_CAMPAIGN,
        episode: int,
        title: str = "",
        notes: str = "",
        snapshot: dict | None = None,
    ) -> ContinuityEpisodeView:
        """Freeze an episode snapshot. A taken number is a 409, not a draft."""

        cleaned_persona = normalize_persona_id(persona_id)
        cleaned_campaign = normalize_campaign(DEFAULT_CAMPAIGN if campaign_id is None else campaign_id)
        cleaned_episode = normalize_episode(episode)
        if cleaned_episode is None:
            raise ContinuityValidationError("episode number is required to create an episode")
        if not isinstance(title, str) or not isinstance(notes, str):
            raise ContinuityValidationError("title and notes must be strings")
        cleaned_title = title.strip()
        cleaned_notes = notes.strip()
        stored_snapshot = dumps_payload({} if snapshot is None else snapshot)
        with SessionLocal() as db:
            taken = db.scalar(
                select(ContinuityEpisode.id).where(
                    ContinuityEpisode.workspace_id == workspace_id,
                    ContinuityEpisode.persona_id == cleaned_persona,
                    ContinuityEpisode.campaign_id == cleaned_campaign,
                    ContinuityEpisode.episode == cleaned_episode,
                )
            )
            if taken:
                raise ContinuityRepositoryError(
                    f"episode {cleaned_episode} of {cleaned_persona}/{cleaned_campaign} already exists"
                )
            row = ContinuityEpisode(
                workspace_id=workspace_id,
                persona_id=cleaned_persona,
                campaign_id=cleaned_campaign,
                episode=cleaned_episode,
                title=cleaned_title,
                notes=cleaned_notes,
                snapshot_json=stored_snapshot,
                created_at=utcnow(),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            view = episode_view(row)
            db.expunge(row)
            return view

    def next_episode_number(
        self,
        workspace_id: str,
        persona_id: str,
        campaign_id: str | None = DEFAULT_CAMPAIGN,
    ) -> int:
        """Return max + 1 (or 1) for the "new episode" button."""

        cleaned_persona = normalize_persona_id(persona_id)
        cleaned_campaign = normalize_campaign(DEFAULT_CAMPAIGN if campaign_id is None else campaign_id)
        with SessionLocal() as db:
            current = db.scalar(
                select(func.max(ContinuityEpisode.episode)).where(
                    ContinuityEpisode.workspace_id == workspace_id,
                    ContinuityEpisode.persona_id == cleaned_persona,
                    ContinuityEpisode.campaign_id == cleaned_campaign,
                )
            )
            return int(current or 0) + 1

    def get_episode(
        self,
        workspace_id: str,
        persona_id: str,
        campaign_id: str | None,
        episode: int,
    ) -> ContinuityEpisodeView | None:
        """Return one episode, or None (foreign ids read as missing)."""

        cleaned_persona = normalize_persona_id(persona_id)
        cleaned_campaign = normalize_campaign(DEFAULT_CAMPAIGN if campaign_id is None else campaign_id)
        cleaned_episode = normalize_episode(episode)
        if cleaned_episode is None:
            return None
        with SessionLocal() as db:
            row = db.scalar(
                select(ContinuityEpisode).where(
                    ContinuityEpisode.workspace_id == workspace_id,
                    ContinuityEpisode.persona_id == cleaned_persona,
                    ContinuityEpisode.campaign_id == cleaned_campaign,
                    ContinuityEpisode.episode == cleaned_episode,
                )
            )
            if row is None:
                return None
            view = episode_view(row)
            db.expunge(row)
            return view

    def list_episodes(
        self,
        workspace_id: str,
        *,
        persona_id: str | None = None,
        campaign_id: str | None = None,
    ) -> list[ContinuityEpisodeView]:
        """List the workspace's episodes, oldest first."""

        with SessionLocal() as db:
            query = select(ContinuityEpisode).where(ContinuityEpisode.workspace_id == workspace_id)
            if persona_id:
                query = query.where(ContinuityEpisode.persona_id == persona_id.strip())
            if campaign_id:
                query = query.where(ContinuityEpisode.campaign_id == campaign_id.strip())
            query = query.order_by(
                ContinuityEpisode.persona_id,
                ContinuityEpisode.campaign_id,
                ContinuityEpisode.episode,
            )
            rows = list(db.scalars(query))
            views = [episode_view(row) for row in rows]
            for row in rows:
                db.expunge(row)
            return views


def _fallback_chain(campaign_id: str, episode: int | None) -> list[tuple[str, int]]:
    """Campaign/episode scopes from most to least specific, deduplicated."""

    chain: list[tuple[str, int]] = []
    if episode is not None:
        chain.append((campaign_id, episode))
    chain.append((campaign_id, DEFAULT_EPISODE))
    if campaign_id != DEFAULT_CAMPAIGN:
        chain.append((DEFAULT_CAMPAIGN, DEFAULT_EPISODE))
    seen: set[tuple[str, int]] = set()
    ordered: list[tuple[str, int]] = []
    for candidate in chain:
        if candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


class RepositoryContinuityStore:
    """A ``ContinuityStore`` bound to one workspace (the resolver adapter)."""

    def __init__(self, workspace_id: str, repository: ContinuityRepository | None = None) -> None:
        self._workspace_id = workspace_id
        self._repository = repository or continuity_repo

    def get_lock(
        self,
        lock_type: str,
        persona_id: str,
        campaign_id: str,
        episode: int | None,
    ):
        """Most specific lock for the workspace, or None."""

        return self._repository.get_lock(
            self._workspace_id, lock_type, persona_id, campaign_id, episode
        )


def continuity_store_for(workspace_id: str) -> RepositoryContinuityStore:
    """Build the resolver's store for one workspace (routes use this)."""

    return RepositoryContinuityStore(workspace_id)


#: Module-level singleton for the API layer (same pattern as ``graph_repo``).
continuity_repo = ContinuityRepository()
