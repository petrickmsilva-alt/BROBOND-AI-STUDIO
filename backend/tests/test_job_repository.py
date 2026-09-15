"""PR004-prep — Repository Pattern: jobs without a direct PostgreSQL dependency.

The directive: the job flow separates business rules (Core `JobService`),
persistence (the `JobRepository` interface) and the database (provider:
PostgreSQL today, Redis tomorrow, memory in tests). These tests pin that
separation:

* the three providers satisfy the same six-method interface;
* `JobService` is provider-agnostic (the same state machine runs over
  Postgres, Redis and memory);
* the Core module never imports a concrete provider (AST guard) and imports
  no framework (the existing independence probe covers this too);
* the default provider is still the `jobs` table, so the pre-refactor
  behaviour — including cross-process persistence — is unchanged.
"""
from __future__ import annotations

import ast
import pathlib
import sys
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

from app.core.job_service import (  # noqa: E402
    JOB_TRANSITIONS,
    InvalidJobTransition,
    Job as CoreJob,
    JobService,
)
from app.job_service import job_service  # noqa: E402
from app.repositories import (  # noqa: E402
    JobRepository,
    MemoryJobRepository,
    PostgresJobRepository,
    RedisJobRepository,
)
from app.schemas import Job as ApiJob  # noqa: E402
from app.schemas import GenerationType  # noqa: E402


# --------------------------------------------------------------------- fixtures


@pytest.fixture()
def postgres_repository() -> PostgresJobRepository:
    """The real default provider, over the test database (jobs table)."""

    return PostgresJobRepository()


@pytest.fixture()
def memory_repository() -> MemoryJobRepository:
    return MemoryJobRepository()


class _FakeRedis:
    """Just enough of the redis-py surface to exercise the provider offline.

    Hashes are dicts, sets are sets — the same semantics the repository uses
    (hgetall/hset/sadd/srem/smembers/delete/pipeline). No server required.
    """

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, set[str]] = {}

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    def hset(self, key: str, mapping: dict[str, str]) -> int:
        self.hashes.setdefault(key, {}).update(mapping)
        return len(mapping)

    def sadd(self, key: str, *values: str) -> int:
        self.sets.setdefault(key, set()).update(values)
        return len(values)

    def srem(self, key: str, *values: str) -> int:
        current = self.sets.get(key, set())
        removed = current.intersection(values)
        current.difference_update(values)
        return len(removed)

    def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    def delete(self, *keys: str) -> int:
        found = 0
        for key in keys:
            found += self.hashes.pop(key, None) is not None
            found += self.sets.pop(key, None) is not None
        return found

    def pipeline(self):
        outer = self

        class _Pipe:
            def __enter__(self_inner):
                self_inner.ops = []
                return self_inner

            def hset(self_inner, key, mapping=None):
                self_inner.ops.append(lambda: outer.hset(key, mapping))
                return self_inner

            def sadd(self_inner, key, *values):
                self_inner.ops.append(lambda: outer.sadd(key, *values))
                return self_inner

            def srem(self_inner, key, *values):
                self_inner.ops.append(lambda: outer.srem(key, *values))
                return self_inner

            def delete(self_inner, *keys):
                self_inner.ops.append(lambda: outer.delete(*keys))
                return self_inner

            def execute(self_inner):
                return [op() for op in self_inner.ops]

            def __exit__(self_inner, *exc):
                return False

        return _Pipe()


def _core_job(**overrides) -> CoreJob:
    base = dict(
        id=str(uuid4()),
        type="image",
        prompt="a red car",
        parameters={"workspace_id": str(uuid4())},
        created_at=datetime.utcnow(),
    )
    base.update(overrides)
    return CoreJob(**base)


# ----------------------------------------------------------------- interface


def test_all_three_providers_satisfy_the_interface() -> None:
    assert isinstance(PostgresJobRepository(), JobRepository)
    assert isinstance(MemoryJobRepository(), JobRepository)
    assert isinstance(RedisJobRepository(client=_FakeRedis()), JobRepository)


def test_redis_requires_a_client_or_url() -> None:
    with pytest.raises(ValueError):
        RedisJobRepository()


@pytest.mark.parametrize(
    "make_repository",
    [
        lambda: PostgresJobRepository(),
        lambda: MemoryJobRepository(),
        lambda: RedisJobRepository(client=_FakeRedis()),
    ],
    ids=["postgres", "memory", "redis"],
)
def test_every_provider_runs_the_same_lifecycle(make_repository) -> None:
    """create / get / update / transition / list_by_workspace / delete."""

    repo = make_repository()
    job = _core_job()
    workspace = job.parameters["workspace_id"]

    created = repo.create(job)
    assert created.id == job.id
    assert repo.get(job.id) is not None

    updated = repo.update(job.id, output_url="s3://out.png")
    assert updated is not None and updated.output_url == "s3://out.png"
    assert updated.status == "queued"  # update never touches the status

    moved = repo.transition(job.id, status="running", progress=42)
    assert moved is not None
    assert moved.status == "running" and moved.progress == 42

    others = _core_job(parameters={"workspace_id": str(uuid4())})
    repo.create(others)
    listed = repo.list_by_workspace(workspace)
    assert [j.id for j in listed] == [job.id]

    assert repo.delete(job.id) is True
    assert repo.delete(job.id) is False
    assert repo.get(job.id) is None
    assert repo.transition(job.id, status="running") is None  # vanished job: no-op


def test_parameters_survive_the_boundary_as_a_document() -> None:
    """The spec adapter reads parameters field by field — they must round-trip exactly."""

    repo = PostgresJobRepository()
    job = _core_job(parameters={"workspace_id": "w", "model": "flux-1.1-pro-ultra", "seed": 7, "nested": {"a": 1}})
    repo.create(job)
    fetched = repo.get(job.id)
    assert fetched is not None
    assert fetched.parameters == job.parameters
    repo.delete(job.id)


# ------------------------------------------------------------------ JobService


def test_the_state_machine_is_the_single_source_of_truth() -> None:
    assert set(JOB_TRANSITIONS) == {"queued", "running", "complete", "failed", "cancelled"}
    assert JOB_TRANSITIONS["queued"] == frozenset({"running", "complete", "failed", "cancelled"})
    assert JOB_TRANSITIONS["running"] == frozenset({"complete", "failed", "cancelled"})
    for terminal in ("complete", "failed", "cancelled"):
        assert JOB_TRANSITIONS[terminal] == frozenset()


@pytest.mark.parametrize(
    "make_repository",
    [
        lambda: PostgresJobRepository(),
        lambda: MemoryJobRepository(),
        lambda: RedisJobRepository(client=_FakeRedis()),
    ],
    ids=["postgres", "memory", "redis"],
)
def test_service_transitions_are_identical_on_every_provider(make_repository) -> None:
    service = JobService(make_repository())
    job = _core_job()
    service.create(job)

    assert service.transition(job.id, status="running", progress=10).status == "running"
    assert service.transition(job.id, status="complete", progress=100).status == "complete"
    # Progress-only tick after a terminal state: allowed, status untouched.
    assert service.transition(job.id, progress=100).status == "complete"

    # The other happy paths.
    for target in ("failed", "cancelled"):
        other = _core_job()
        service.create(other)
        assert service.transition(other.id, status=target).status == target
        # Terminal: no further status change is possible.
        with pytest.raises(InvalidJobTransition):
            service.transition(other.id, status="running")


def test_a_forbidden_transition_cannot_be_persisted() -> None:
    service = JobService(MemoryJobRepository())
    job = _core_job()
    service.create(job)
    # queued -> complete is legal (the orchestration-only worker path).
    assert service.transition(job.id, status="complete").status == "complete"
    # ...but a terminal job can never move again.
    with pytest.raises(InvalidJobTransition):
        service.transition(job.id, status="running")
    # queued -> queued is a no-op (same status is always tolerated).
    other = _core_job()
    service.create(other)
    assert service.transition(other.id, status="queued").status == "queued"
    # The job still holds its legal state.
    assert service.get(job.id).status == "complete"


def test_create_rejects_unknown_statuses() -> None:
    service = JobService(MemoryJobRepository())
    with pytest.raises(ValueError):
        service.create(_core_job(status="finished"))
    job = _core_job()
    service.create(job)
    with pytest.raises(ValueError):
        service.transition(job.id, status="finished")


def test_delete_returns_false_for_unknown_jobs() -> None:
    service = JobService(MemoryJobRepository())
    assert service.delete(str(uuid4())) is False


# ---------------------------------------------------------------- DI purity


def test_the_core_never_imports_a_concrete_provider() -> None:
    """The directive, as a static guard: no Postgres/Redis/memory import in core."""

    source = (ROOT / "backend" / "app" / "core" / "job_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for banned in (
        "sqlalchemy",
        "redis",
        "app.repositories",
        "app.repositories.postgres_job_repository",
        "app.repositories.redis_job_repository",
        "app.repositories.memory_job_repository",
        "..repositories.postgres_job_repository",
        "..repositories.redis_job_repository",
        "..repositories.memory_job_repository",
    ):
        assert banned not in imported, f"core/job_service.py imports {banned}"


def test_postgres_is_the_only_job_module_with_sqlalchemy() -> None:
    """The PostgreSQL dependency lives in exactly one job module.

    (The persona repository also imports SQLAlchemy — legitimately: it is the
    persona layer's own SQL boundary, the same principle, established in
    PR003. This guard is about the job flow.)
    """

    job_modules = (
        "job_repository.py",
        "postgres_job_repository.py",
        "redis_job_repository.py",
        "memory_job_repository.py",
    )
    repo_dir = ROOT / "backend" / "app" / "repositories"
    with_sqlalchemy = []
    for name in job_modules:
        path = repo_dir / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            if any(m.split(".")[0] == "sqlalchemy" for m in modules):
                with_sqlalchemy.append(name)
                break
    assert with_sqlalchemy == ["postgres_job_repository.py"], with_sqlalchemy


def test_store_no_longer_depends_on_postgres() -> None:
    """The directive's headline rule: `app/store.py` has no SQLAlchemy import."""

    source = (ROOT / "backend" / "app" / "store.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "sqlalchemy" not in imported, sorted(imported)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.asname or alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {alias.name for alias in node.names}
    assert "JobRow" not in names, sorted(names)
    # ...and the legacy surface still works through the new architecture.
    from app.store import store

    job = ApiJob(type=GenerationType.IMAGE, prompt="legacy facade", parameters={"workspace_id": str(uuid4())})
    store.add_job(job)
    fetched = store.get_job(job.id)
    assert fetched is not None and fetched.id == job.id
    store.set_job_state(job.id, progress=5)
    assert store.get_job(job.id).progress == 5
    assert job_service.delete(job.id) is True  # clean up via the Core


def test_the_wired_service_uses_the_postgres_provider_by_default() -> None:
    """PostgreSQL is the default — the external behaviour is the PR002 one."""

    assert isinstance(job_service, JobService)
    assert type(job_service._repository).__name__ == "PostgresJobRepository"
    # And it reaches the same table the pre-refactor code used.
    from app.models import JobRow

    assert JobRow.__tablename__ == "jobs"


def test_api_and_core_jobs_map_back_and_forth() -> None:
    from app.jobs import to_api_job, to_core_job

    created_at = datetime.utcnow()
    api = ApiJob(
        type=GenerationType.VIDEO,
        prompt="round trip",
        parameters={"workspace_id": "w", "seed": 3},
        progress=7,
        output_url="http://x/out.mp4",
        created_at=created_at,
    )
    core = to_core_job(api)
    assert core.id == str(api.id) and core.type == "video" and core.status == "queued"
    assert core.parameters == api.parameters and core.created_at == created_at

    back = to_api_job(core)
    assert back.id == api.id and back.type is GenerationType.VIDEO
    assert back.status.value == "queued" and back.progress == 7 and back.output_url == api.output_url


def test_memory_repository_instances_are_isolated() -> None:
    """One instance = one database: no shared state between 'tenants' of the test."""

    first, second = MemoryJobRepository(), MemoryJobRepository()
    job = _core_job()
    first.create(job)
    assert first.get(job.id) is not None
    assert second.get(job.id) is None


def test_redis_provider_round_trips_a_full_lifecycle() -> None:
    repo = RedisJobRepository(client=_FakeRedis())
    job = _core_job(created_at=datetime.utcnow())
    workspace = job.parameters["workspace_id"]
    repo.create(job)

    fetched = repo.get(job.id)
    assert fetched is not None
    assert fetched.parameters == job.parameters
    assert abs((fetched.created_at - job.created_at).total_seconds()) < 1

    repo.transition(job.id, status="running", progress=50)
    assert repo.get(job.id).status == "running"

    # Workspace listing sees it, another workspace does not.
    assert [j.id for j in repo.list_by_workspace(workspace)] == [job.id]
    assert repo.list_by_workspace(str(uuid4())) == []

    assert repo.delete(job.id) is True
    assert repo.list_by_workspace(workspace) == []
