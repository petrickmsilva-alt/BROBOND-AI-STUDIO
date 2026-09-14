from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.schemas.generation import (
    GenerationJob,
    ImageGenerationRequest,
    VideoGenerationRequest,
)


class GenerationService:
    """Application boundary for image and video jobs.

    The service intentionally does not import Diffusers or Torch. Provider-specific
    engines can be attached behind this boundary without coupling HTTP routes to
    GPU code. A worker can persist the returned job in Redis/PostgreSQL later.
    """

    def submit_image(self, payload: ImageGenerationRequest) -> GenerationJob:
        return self._new_job("image", payload.prompt)

    def submit_video(self, payload: VideoGenerationRequest) -> GenerationJob:
        return self._new_job("video", payload.prompt)

    @staticmethod
    def _new_job(kind: str, prompt: str) -> GenerationJob:
        return GenerationJob(
            id=uuid4(),
            kind=kind,  # type: ignore[arg-type]
            status="queued",
            prompt=prompt,
            progress=0,
            created_at=datetime.now(UTC),
        )


class QueueService:
    """Small in-memory adapter used by local development and API docs."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, GenerationJob] = {}

    def enqueue(self, job: GenerationJob) -> GenerationJob:
        self._jobs[job.id] = job
        return job

    def list_jobs(self) -> list[GenerationJob]:
        return list(self._jobs.values())

    def depth(self) -> int:
        return sum(job.status in {"queued", "running"} for job in self._jobs.values())


generation_service = GenerationService()
queue_service = QueueService()
