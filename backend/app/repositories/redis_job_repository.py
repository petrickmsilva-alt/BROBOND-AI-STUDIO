"""RedisJobRepository — the Redis-backed job provider (PR004-prep, opt-in).

The Repository Pattern makes the database swappable without touching the
Core: this provider stores each job as a JSON document in a Redis hash and
keeps one set per workspace for `list_by_workspace`. It is NOT the default
(the default is `PostgresJobRepository`); it exists so a deployment can
point the job flow at Redis — `JobService` cannot tell the difference.

Key layout (namespaced so it can share a Redis with the Celery broker):

    brobond:job:{job_id}              hash — the job document (JSON fields)
    brobond:jobs:workspace:{ws_id}    set  — job ids, for listing

`redis` (pinned in requirements) is a hard dependency of this module, but
the connection itself is lazy: constructing the repository with a URL does
not touch the network until the first operation.
"""
from __future__ import annotations

import json
from datetime import datetime

import redis

from ..core.job_service import Job

_DOC_MIN = datetime.min

_JOB_KEY = "brobond:job:{job_id}"
_WS_KEY = "brobond:jobs:workspace:{workspace_id}"


def _job_to_doc(job: Job) -> dict[str, str]:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "prompt": job.prompt,
        "parameters": json.dumps(job.parameters, ensure_ascii=False),
        "progress": str(job.progress),
        "output_url": job.output_url or "",
        "created_at": job.created_at.isoformat() if job.created_at else "",
        "workspace_id": str(job.parameters.get("workspace_id") or ""),
    }


def _doc_to_job(doc: dict[str, str]) -> Job:
    created_at = doc.get("created_at") or None
    return Job(
        id=doc["id"],
        type=doc["type"],
        status=doc["status"],
        prompt=doc.get("prompt", ""),
        parameters=json.loads(doc.get("parameters") or "{}"),
        progress=int(doc.get("progress") or 0),
        output_url=doc.get("output_url") or None,
        created_at=datetime.fromisoformat(created_at) if created_at else None,
    )


class RedisJobRepository:
    """JobRepository over Redis hashes + per-workspace sets."""

    def __init__(self, client: "redis.Redis | None" = None, url: str | None = None) -> None:
        if client is None and url is None:
            raise ValueError("RedisJobRepository needs a client or a url")
        self._client = client if client is not None else redis.Redis.from_url(url)

    # ------------------------------------------------------------- internal

    def _job_key(self, job_id: str) -> str:
        return _JOB_KEY.format(job_id=job_id)

    def _read(self, job_id: str) -> Job | None:
        doc = self._client.hgetall(self._job_key(job_id))
        if not doc:
            return None
        return _doc_to_job({str(k): str(v) for k, v in doc.items()})

    def _write(self, job: Job) -> None:
        workspace_id = str(job.parameters.get("workspace_id") or "")
        with self._client.pipeline() as pipe:
            pipe.hset(self._job_key(job.id), mapping=_job_to_doc(job))
            if workspace_id:
                pipe.sadd(_WS_KEY.format(workspace_id=workspace_id), job.id)
            pipe.execute()

    def _apply(
        self,
        job_id: str,
        *,
        status: str | None,
        progress: int | None,
        output_url: str | None,
    ) -> Job | None:
        job = self._read(job_id)
        if job is None:
            return None
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = progress
        if output_url is not None:
            job.output_url = output_url
        self._write(job)
        return self._read(job_id)

    # ------------------------------------------------------------- interface

    def create(self, job: Job) -> Job:
        self._write(job)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._read(job_id)

    def update(self, job_id: str, *, progress: int | None = None, output_url: str | None = None) -> Job | None:
        return self._apply(job_id, status=None, progress=progress, output_url=output_url)

    def transition(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        output_url: str | None = None,
    ) -> Job | None:
        return self._apply(job_id, status=status, progress=progress, output_url=output_url)

    def list_by_workspace(self, workspace_id: str) -> list[Job]:
        job_ids = self._client.smembers(_WS_KEY.format(workspace_id=workspace_id))
        jobs = [job for job_id in job_ids if (job := self._read(str(job_id)))]
        jobs.sort(key=lambda job: (job.created_at or _DOC_MIN, job.id), reverse=True)
        return jobs

    def delete(self, job_id: str) -> bool:
        job = self._read(job_id)
        if job is None:
            return False
        workspace_id = str(job.parameters.get("workspace_id") or "")
        with self._client.pipeline() as pipe:
            pipe.delete(self._job_key(job_id))
            if workspace_id:
                pipe.srem(_WS_KEY.format(workspace_id=workspace_id), job_id)
            pipe.execute()
        return True

